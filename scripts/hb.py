#!/usr/bin/env python3
"""Hivey Browser build orchestrator.

Builds Hivey Browser on top of ungoogled-chromium, from a Linux host:
Windows x64 (cross-compiled, HB_TARGET=win, the default) or Linux x64
(HB_TARGET=linux), both from the same patched tree. Every step is idempotent
and records a stamp, so an interrupted run can be resumed with `hb.py all`.

    hb.py fetch       download + verify the Chromium source tarball
    hb.py unpack      extract it into $HB_BUILD_DIR/src
    hb.py prune       remove prebuilt binaries (ungoogled pruning list)
    hb.py toolchain   fetch build-only host tools + MSVC CRT/Windows SDK (xwin)
    hb.py patch       ungoogled + ungoogled-windows (selected) + Hivey patches
    hb.py brand       apply brand/brand.json, write the Hivey version
    hb.py bundle      bundled extensions (signed .crx) + update public key
    hb.py domsub      ungoogled domain substitution
    hb.py configure   write args.gn and run `gn gen` (per target)
    hb.py build       ninja (low CPU/IO priority, per target)
    hb.py package     installer or portable archive in $HB_BUILD_DIR/dist
    hb.py all         every step above, in order, skipping finished ones
    hb.py status      show which steps are done

The build runs at the lowest CPU and I/O priority by default, because the
build host also serves production traffic.
"""

import argparse
import base64
import configparser
import gzip
import re
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UG = ROOT / 'third_party' / 'ungoogled-chromium'
UGW = ROOT / 'third_party' / 'ungoogled-chromium-windows'
BUILD = Path(os.environ.get('HB_BUILD_DIR', ROOT.parent / 'hivey-browser-build')).resolve()
SRC = BUILD / 'src'
# Target OS: Windows x64 (cross-compiled, out/Default) or Linux x64 (out/Linux).
# Both are built from the same patched source tree.
TARGET = os.environ.get('HB_TARGET', 'win')
if TARGET not in ('win', 'linux'):
    raise SystemExit(f'HB_TARGET must be win or linux, not {TARGET!r}')
OUT = SRC / 'out' / ('Default' if TARGET == 'win' else 'Linux')
DIST = BUILD / 'dist'
TOOLS = BUILD / 'tools'
STATE = BUILD / '.hb-state.json'

sys.path.insert(0, str(UG / 'utils'))
import downloads  # noqa: E402
import domain_substitution  # noqa: E402
import patches  # noqa: E402
import prune_binaries  # noqa: E402
sys.path.pop(0)
sys.path.insert(0, str(ROOT / 'scripts'))
import crx3  # noqa: E402
import geoip  # noqa: E402
sys.path.pop(0)

STEPS = ['fetch', 'unpack', 'prune', 'toolchain', 'patch', 'brand', 'bundle', 'domsub', 'configure', 'build',
         'package']
# Steps done once per output directory (one per target OS); the others
# prepare the shared source tree.
PER_TARGET_STEPS = {'configure', 'build', 'package'}

# Windows patches from ungoogled-chromium-windows that only make sense when the
# build host is Windows with upstream LLVM (Microsoft rc.exe, gn.exe, python.exe,
# clang version checks...). We cross-compile with Chromium's own pinned clang and
# Rust, which is the officially supported cross-build setup, so we skip them.
WINDOWS_HOST_ONLY_PATCHES = {
    'ungoogled-chromium/windows/windows-disable-rcpy.patch',
    'ungoogled-chromium/windows/windows-fix-rc.patch',
    'ungoogled-chromium/windows/windows-fix-rc-terminating-error.patch',
    'ungoogled-chromium/windows/windows-fix-building-gn.patch',
    'ungoogled-chromium/windows/windows-fix-python.patch',
    'ungoogled-chromium/windows/windows-fix-clang-format-exe.patch',
    'ungoogled-chromium/windows/windows-fix-licenses-gn-path.patch',
    'ungoogled-chromium/windows/windows-fix-typescript-lib-dom.patch',
    'ungoogled-chromium/windows/windows-disable-clang-version-check.patch',
    'ungoogled-chromium/windows/windows-fix-unsupported-llvm-flags.patch',
    'ungoogled-chromium/windows/windows-fix-building-with-rust.patch',
    'ungoogled-chromium/windows/windows-no-unknown-warnings.patch',
}

# GN args from ungoogled-chromium-windows that assume upstream LLVM/Rust
# (clang_version: upstream's major version, not the pinned clang's).
WINDOWS_HOST_ONLY_FLAGS = {'use_sysroot', 'clang_version'}


def log(msg):
    print(f'\033[1;33m[hb]\033[0m {msg}', flush=True)


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _state_key(step):
    return f'{step}:{TARGET}' if step in PER_TARGET_STEPS else step


def mark_done(step, **info):
    state = load_state()
    state[_state_key(step)] = {'done': True, **info}
    STATE.write_text(json.dumps(state, indent=2))


def is_done(step):
    return load_state().get(_state_key(step), {}).get('done', False)


def run(cmd, **kw):
    log('$ ' + ' '.join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def lower_priority():
    """Lowest CPU + idle I/O priority for this process and its children."""
    os.nice(19 - os.nice(0))
    if shutil.which('ionice'):
        subprocess.run(['ionice', '-c3', '-p', str(os.getpid())], check=False)


def chromium_version():
    return (UG / 'chromium_version.txt').read_text().strip()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest, sha256=None):
    dest = Path(dest)
    if dest.exists() and (sha256 is None or sha256_file(dest) == sha256):
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    log(f'download {url}')
    tmp = dest.with_suffix(dest.suffix + '.part')
    with urllib.request.urlopen(url) as r, open(tmp, 'wb') as f:
        shutil.copyfileobj(r, f, 1 << 20)
    if sha256 and sha256_file(tmp) != sha256:
        tmp.unlink()
        raise SystemExit(f'checksum mismatch for {url}')
    tmp.rename(dest)
    return dest


# --------------------------------------------------------------------- steps

def step_fetch(args):
    info = downloads.DownloadInfo([UG / 'downloads.ini'])
    cache = BUILD / 'download_cache'
    cache.mkdir(parents=True, exist_ok=True)
    downloads.retrieve_downloads(info, cache, None, True, False)
    downloads.check_downloads(info, cache, None)
    mark_done('fetch', version=chromium_version())


def step_unpack(args):
    tarball = BUILD / 'download_cache' / f'chromium-{chromium_version()}-lite.tar.xz'
    if (SRC / 'BUILD.gn').exists():
        log('source tree already present, not re-extracting')
    else:
        SRC.mkdir(parents=True, exist_ok=True)
        run(['tar', '-xJf', tarball, '-C', SRC, '--strip-components=1'])
    mark_done('unpack')


# Pruned by ungoogled, needed by a cross-build: Linux has no midl.exe/mc.exe,
# so Chromium copies their precompiled outputs (type libraries, message
# tables: data generated from the .idl/.mc files in the tree, not code).
PRUNE_KEEP = ('third_party/win_build_output/',
              'third_party/dawn/third_party/directx-shader-compiler/win_build_output/')


def step_prune(args):
    pruning = [f for f in (UG / 'pruning.list').read_text().splitlines() if not f.startswith(PRUNE_KEEP)]
    leftover = prune_binaries.prune_files(SRC, pruning)
    if leftover:
        log(f'{len(leftover)} listed files were already absent (expected with the lite tarball)')
    mark_done('prune')


def _gcs(bucket, obj):
    return f'https://storage.googleapis.com/{bucket}/{obj}'


def _toolchain_clang():
    # update.py reads target_os from a .gclient next to src/: ask for the
    # Windows runtime libraries (needed to link Windows binaries).
    (BUILD / '.gclient').write_text("solutions = []\ntarget_os = ['win']\n")
    run([sys.executable, SRC / 'tools/clang/scripts/update.py'])


def _toolchain_rust():
    run([sys.executable, SRC / 'tools/rust/update_rust.py'])


def _toolchain_sysroot():
    # Debian sysroot for the Linux host tools (protoc, ...), sha256-pinned.
    run([sys.executable, SRC / 'build/linux/sysroot_scripts/install-sysroot.py', '--arch=amd64'])


def _toolchain_rc():
    sha1 = (SRC / 'build/toolchain/win/rc/linux64/rc.sha1').read_text().strip()
    dest = SRC / 'build/toolchain/win/rc/linux64/rc'
    if not dest.exists():
        download(_gcs('chromium-browser-clang/rc', sha1), dest)
    if hashlib.sha1(dest.read_bytes()).hexdigest() != sha1:
        raise SystemExit('rc: sha1 mismatch')
    dest.chmod(0o755)


def _toolchain_pgo():
    """PGO profiles of both targets (execution counters, no code), normally
    fetched by a gclient hook; checked against the md5 GCS reports for each
    object."""
    for profile in ('win64', 'linux'):
        name = (SRC / f'chrome/build/{profile}.pgo.txt').read_text().strip()
        dest = SRC / 'chrome/build/pgo_profiles' / name
        if dest.exists():
            continue
        url = _gcs('chromium-optimization-profiles/pgo_profiles', name)
        # The object is stored gzip-compressed and GCS decompresses it on the
        # fly; the md5 it publishes is the one of the stored (compressed) bytes.
        req = urllib.request.Request(url, headers={'Accept-Encoding': 'gzip'})
        with urllib.request.urlopen(req) as r:
            md5 = [h.split('=', 1)[1] for h in r.headers.get_all('x-goog-hash') if h.startswith('md5=')][0]
            raw = r.read()
        if base64.b64encode(hashlib.md5(raw).digest()).decode() != md5:
            raise SystemExit(f'PGO profile {name}: md5 mismatch')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)


def _toolchain_windows_sources():
    """Windows-only sources missing from the (Linux-oriented) lite tarball.

    Versions and hashes come from ungoogled-chromium-windows' downloads.ini so
    we stay in sync with them:
      * DirectX-Headers, webauthn and multimedia-redirection headers
        (Microsoft, pinned commits);
      * windows.0.52.0.lib import libraries of the vendored windows_*_msvc
        crates: ungoogled prunes them as binaries, we restore them from the
        windows-rs 0.52.0 release (sha512-pinned), where they come from.
    """
    ini = configparser.ConfigParser()
    ini.read(UGW / 'downloads.ini')

    def fetch(section):
        sec = ini[section]
        url = sec.get('url', raw=True).replace('%(version)s', sec['version']).strip()
        dest = BUILD / 'download_cache' / sec.get('download_filename', raw=True).replace('%(version)s', sec['version'])
        download(url, dest)
        if 'sha512' in sec and hashlib.sha512(dest.read_bytes()).hexdigest() != sec['sha512']:
            raise SystemExit(f'{section}: sha512 mismatch')
        return sec, zipfile.ZipFile(dest)

    for section, target in (('directx-headers', 'third_party/microsoft_dxheaders/src'),
                            ('webauthn', 'third_party/microsoft_webauthn/src'),
                            ('multimedia-redirection', 'third_party/microsoft_multimedia_redirection/src')):
        out = SRC / target
        if out.exists() and any(out.iterdir()):
            continue
        sec, zf = fetch(section)
        strip = sec.get('strip_leading_dirs', raw=True).replace('%(version)s', sec['version']) + '/'
        for info in zf.infolist():
            if info.filename.startswith(strip) and not info.is_dir():
                dest = out / info.filename[len(strip):]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(info))

    vendor = SRC / 'third_party/rust/chromium_crates_io/vendor'
    _, zf = fetch('rust-windows-create')
    for arch in ('x86_64', 'i686', 'aarch64'):
        lib = vendor / f'windows_{arch}_msvc-v0_52' / 'lib' / 'windows.0.52.0.lib'
        if not lib.exists():
            lib.parent.mkdir(parents=True, exist_ok=True)
            lib.write_bytes(zf.read(f'windows-rs-0.52.0/crates/targets/{arch}_msvc/lib/windows.0.52.0.lib'))


def _toolchain_go():
    """Go for the Linux host: Dawn generates WebGPU sources with `go run`.

    The version follows the `go` directive of Dawn's go.mod (newest stable
    patch release, sha256 from go.dev's index). The build runs with
    GOTOOLCHAIN=local and GOPROXY=off, so Go never downloads anything itself.
    """
    gomod = (SRC / 'third_party/dawn/go.mod').read_text()
    minor = re.search(r'^go (\d+\.\d+)', gomod, re.M).group(1)
    target = SRC / 'third_party/dawn/tools/golang/linux-amd64'
    gobin = target / 'bin' / 'go'
    if gobin.exists() and f'go{minor}' in subprocess.run([gobin, 'version'], capture_output=True,
                                                        text=True).stdout:
        return
    shutil.rmtree(target, ignore_errors=True)
    with urllib.request.urlopen('https://go.dev/dl/?mode=json&include=all') as r:
        releases = json.load(r)
    rel = next(r for r in releases if r['stable'] and re.fullmatch(rf'go{re.escape(minor)}(\.\d+)?', r['version']))
    name = f"{rel['version']}.linux-amd64.tar.gz"
    sha = next(f['sha256'] for f in rel['files'] if f['filename'] == name)
    archive = download(f'https://go.dev/dl/{name}', BUILD / 'download_cache' / name, sha)
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as t:
        for m in t.getmembers():
            if m.name.startswith('go/'):
                m.name = m.name[3:]
                t.extract(m, target, filter='data')


def _toolchain_node():
    # The Linux node binary is pinned (object + sha256) in DEPS.
    deps = (SRC / 'DEPS').read_text()
    block = deps[deps.index("'src/third_party/node/linux'"):]
    obj = block.split("'object_name': '")[1].split("'")[0]
    sha = block.split("'sha256sum': '")[1].split("'")[0]
    archive = download(_gcs('chromium-nodejs', obj), BUILD / 'download_cache' / f'node-{obj}.tar.gz', sha)
    target = SRC / 'third_party/node/linux'
    if not (target / 'node-linux-x64/bin/node').exists():
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as t:
            t.extractall(target, filter='data')
    # The lite tarball already ships node_modules extracted; if it is missing,
    # fetch the archive pinned by node_modules.tar.gz.sha1.
    nm = SRC / 'third_party/node/node_modules'
    if not nm.exists() or not any(nm.iterdir()):
        sha1 = (SRC / 'third_party/node/node_modules.tar.gz.sha1').read_text().strip()
        archive = download(_gcs('chromium-nodejs', sha1), BUILD / 'download_cache' / f'node_modules-{sha1}.tar.gz')
        if hashlib.sha1(archive.read_bytes()).hexdigest() != sha1:
            raise SystemExit('node_modules: sha1 mismatch')
        with tarfile.open(archive) as t:
            t.extractall(SRC / 'third_party/node', filter='data')


def _toolchain_ninja():
    version = '1.13.1'
    ninja = TOOLS / 'ninja'
    if not ninja.exists():
        z = download(f'https://github.com/ninja-build/ninja/releases/download/v{version}/ninja-linux.zip',
                     BUILD / 'download_cache' / f'ninja-{version}-linux.zip')
        TOOLS.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(TOOLS)
        ninja.chmod(0o755)


def _toolchain_gn():
    gn = TOOLS / 'gn'
    if not gn.exists():
        clang_bin = SRC / 'third_party/llvm-build/Release+Asserts/bin'
        env = {**os.environ, 'CC': str(clang_bin / 'clang'), 'CXX': str(clang_bin / 'clang++'),
               'AR': str(clang_bin / 'llvm-ar'), 'CFLAGS': '', 'CXXFLAGS': '', 'LDFLAGS': '-fuse-ld=lld'}
        out = BUILD / 'gn-bootstrap'
        out.mkdir(parents=True, exist_ok=True)
        run([sys.executable, SRC / 'tools/gn/bootstrap/bootstrap.py', '-o', out / 'gn',
             '--skip-generate-buildfiles', '-j', str(args_jobs())], env=env)
        TOOLS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out / 'gn', gn)


WINSYSROOT = BUILD / 'winsysroot'
WINSYSROOT_STORE = BUILD / 'winsysroot.ciopfs'


def ensure_winsysroot():
    """Mount the Windows toolchain on a case-insensitive file system.

    Windows headers are included with arbitrary casing (`ObjBase.h` for
    `objbase.h`...), which only works on a case-insensitive file system.
    Like Chromium's own cross-build, we use ciopfs (FUSE): files live
    lower-cased in winsysroot.ciopfs and are served at winsysroot. A FUSE mount
    does not survive a reboot, so every step that needs it calls this.
    """
    if os.path.ismount(WINSYSROOT):
        return
    ciopfs = TOOLS / 'ciopfs'
    if not ciopfs.exists():
        sha1 = (SRC / 'build/ciopfs.sha1').read_text().strip()
        download(_gcs('chromium-browser-clang/ciopfs', sha1), ciopfs)
        if hashlib.sha1(ciopfs.read_bytes()).hexdigest() != sha1:
            ciopfs.unlink()
            raise SystemExit('ciopfs: sha1 mismatch')
        ciopfs.chmod(0o755)
    WINSYSROOT.mkdir(parents=True, exist_ok=True)
    WINSYSROOT_STORE.mkdir(parents=True, exist_ok=True)
    # Needs libfuse2 (Ubuntu: libfuse2t64).
    run([ciopfs, '-o', 'use_ino', WINSYSROOT_STORE, WINSYSROOT])


def _toolchain_msvc():
    """MSVC CRT + Windows SDK via xwin, laid out the way vs_toolchain.py expects.

    Chromium normally gets this from a zip packaged on a Windows machine. xwin
    downloads the same packages straight from Microsoft's VS manifests, so the
    whole build stays reproducible from Linux. Requires `cargo install xwin`
    and accepting the Microsoft license (XWIN_ACCEPT_LICENSE=1).
    """
    vs = (SRC / 'build/vs_toolchain.py').read_text()
    sdk_version = vs.split("SDK_VERSION = '")[1].split("'")[0]          # e.g. 10.0.28000.0
    short_sdk = '.'.join(sdk_version.split('.')[:3])                    # xwin drops the last .0
    ensure_winsysroot()
    root = WINSYSROOT
    kits = root / 'Windows Kits' / '10'
    msvc_root = root / 'VC/Tools/MSVC'
    complete = (kits / 'Include' / sdk_version).exists() and msvc_root.exists() and all(
        (d / 'lib' / cpu).exists() for d in msvc_root.iterdir() for cpu in ('x64', 'x86', 'arm64'))
    if not complete:
        for child in root.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        if os.environ.get('XWIN_ACCEPT_LICENSE') != '1':
            raise SystemExit('The MSVC CRT and Windows SDK are covered by the Microsoft Visual Studio license '
                             '(https://visualstudio.microsoft.com/license-terms/). Set XWIN_ACCEPT_LICENSE=1 to '
                             'accept it and download them.')
        cache = BUILD / 'xwin-cache'
        cmd = ['xwin', '--accept-license', '--cache-dir', cache, '--manifest-version', '18',
               '--sdk-version', short_sdk, '--arch', 'x86_64,x86,aarch64']
        # Microsoft's July 2026 SDK manifest contains a raw space in a URL path
        # ("w kits2"), which xwin rejects: list once to cache the manifest,
        # percent-encode it, then splat from the fixed cache.
        run(cmd + ['list'], stdout=subprocess.DEVNULL)
        for vsman in (cache / 'dl').glob('*.vsman'):
            text = vsman.read_text()
            if '/w kits2/' in text:
                vsman.write_text(text.replace('/w kits2/', '/w%20kits2/'))
        # No casing symlinks: the case-insensitive mount makes them useless
        # (and a symlink to its own lower-case name would loop). CRT PDBs are
        # needed: libcmt.lib objects reference them and lld-link errors out
        # (LNK4099) when they are missing. --copy: xwin >= 0.9 moves files out
        # of its cache, which fails across file systems (the FUSE mount).
        run(cmd + ['splat', '--use-winsysroot-style', '--preserve-ms-arch-notation', '--disable-symlinks',
                   '--include-debug-symbols', '--copy',
                   '--output', root])
        for sub in ('Include', 'Lib'):
            src_dir = kits / sub / short_sdk
            if src_dir.exists():
                src_dir.rename(kits / sub / sdk_version)
    # bin/SetEnv.x64.json, paths relative to the toolchain root.
    msvc = sorted((root / 'VC/Tools/MSVC').iterdir())[-1].name
    sdk_inc = ['Windows Kits', '10', 'Include', sdk_version]
    sdk_lib = ['Windows Kits', '10', 'Lib', sdk_version]
    (kits / 'bin').mkdir(parents=True, exist_ok=True)
    # gn loads the toolchain description of every Windows CPU, even for an x64
    # target, and checks that every library directory exists.
    for cpu in ('x64', 'x86', 'arm64'):
        env = {
            'VSINSTALLDIR': [['.\\']],
            'VCINSTALLDIR': [['VC\\']],
            'INCLUDE': [['VC', 'Tools', 'MSVC', msvc, 'include'], ['VC', 'Tools', 'MSVC', msvc, 'atlmfc', 'include']] + [sdk_inc + [d] for d in
                                                                       ('um', 'shared', 'winrt', 'ucrt', 'cppwinrt')],
            'LIB': [['VC', 'Tools', 'MSVC', msvc, 'lib', cpu], ['VC', 'Tools', 'MSVC', msvc, 'atlmfc', 'lib', cpu], sdk_lib + ['um', cpu], sdk_lib + ['ucrt', cpu]],
            'LIBPATH': [['VC', 'Tools', 'MSVC', msvc, 'lib', cpu]],
            'PATH': [['VC', 'Tools', 'MSVC', msvc, 'bin', 'HostX64', cpu]],
        }
        (kits / 'bin' / f'SetEnv.{cpu}.json').write_text(json.dumps({'env': env}, indent=2))
        # setup_toolchain.py locates the VC bin dir by looking for cl.exe. We
        # build with clang-cl and never run it: an empty marker is enough, and
        # anything that did try to execute it would fail loudly.
        vc_bin = root / 'VC/Tools/MSVC' / msvc / 'bin/HostX64' / cpu
        vc_bin.mkdir(parents=True, exist_ok=True)
        (vc_bin / 'cl.exe').touch()
    _toolchain_msvc_redist(root, msvc)
    _toolchain_msvc_atl(root, msvc)
    _toolchain_dia_sdk(root)
    _toolchain_debuggers(kits)
    _toolchain_d3dcompiler(kits, sdk_version)
    (SRC / 'build/win_toolchain.json').write_text(json.dumps({
        'path': str(root), 'version': '2026', 'win_sdk': str(kits), 'wdk': '',
        'runtime_dirs': [str(root / 'sys64'), str(root / 'sys32'), 'Arm64Unused'],
    }, indent=2))


def _vs_payload(pkg_id):
    """Payload of a VS manifest package (newest version if several manifests
    list it)."""
    found = []
    for vsman in (BUILD / 'xwin-cache' / 'dl').glob('*.vsman'):
        for pkg in json.loads(vsman.read_text()).get('packages', []):
            if pkg['id'] == pkg_id:
                found.append((tuple(int(x) for x in pkg['version'].split('.')), pkg['payloads'][0]))
    if not found:
        raise SystemExit(f'{pkg_id} not found in the VS manifest')
    return max(found, key=lambda f: f[0])[1]


def _toolchain_dia_sdk(root):
    """DIA SDK (dia2.h, diaguids.lib, msdia140.dll), used by Dawn's DirectX
    shader compiler and copied next to the binaries by vs_toolchain.py."""
    dia = root / 'DIA SDK'
    if (dia / 'include' / 'dia2.h').exists():
        return
    payload = _vs_payload('Microsoft.VisualCpp.DIA.SDK')
    vsix = download(payload['url'].replace(' ', '%20'), BUILD / 'download_cache' / payload['fileName'],
                    payload['sha256'].lower())
    with zipfile.ZipFile(vsix) as zf:
        for info in zf.infolist():
            name = urllib.parse.unquote(info.filename)  # VSIX paths are URL-encoded ("DIA%20SDK")
            marker = 'DIA SDK/'
            if marker in name and not info.is_dir():
                dest = dia / name.split(marker, 1)[1]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(info))


def _toolchain_msvc_atl(root, msvc):
    """ATL headers and libraries (Chromium's Windows code uses ATL), which
    xwin does not fetch. Unpacked to VC/Tools/MSVC/<ver>/atlmfc, where
    clang-cl and lld-link look on their own with /winsysroot."""
    atl = root / 'VC/Tools/MSVC' / msvc / 'atlmfc'
    if (atl / 'include' / 'atldef.h').exists():
        return
    for part in ('Headers', 'X64', 'X86', 'ARM64'):
        payload = _vs_payload(f'Microsoft.VC.{msvc}.ATL.{part}.base')
        vsix = download(payload['url'].replace(' ', '%20'), BUILD / 'download_cache' / payload['fileName'],
                        payload['sha256'].lower())
        with zipfile.ZipFile(vsix) as zf:
            for info in zf.infolist():
                marker = '/atlmfc/'
                if marker in info.filename and not info.is_dir():
                    dest = atl / info.filename.split(marker, 1)[1]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(info))


def _toolchain_msvc_redist(root, msvc):
    """VC runtime DLLs (sys64/sys32) that gn copies next to the binaries.

    The official build links the CRT statically, but vs_toolchain.py copies
    the redistributable DLLs anyway. xwin does not fetch them, so take the
    Redist packages matching our CRT version from the VS manifest xwin cached,
    verifying the sha256 Microsoft publishes there.
    """
    for arch, dest in (('X64', 'sys64'), ('X86', 'sys32')):
        out = root / dest
        if (out / 'vcruntime140.dll').exists():
            continue
        pkg_id = f'Microsoft.VC.{msvc}.CRT.Redist.{arch}.base'
        payload = None
        for vsman in (BUILD / 'xwin-cache' / 'dl').glob('*.vsman'):
            for pkg in json.loads(vsman.read_text()).get('packages', []):
                if pkg['id'] == pkg_id:
                    payload = pkg['payloads'][0]
        if payload is None:
            raise SystemExit(f'{pkg_id} not found in the VS manifest')
        vsix = download(payload['url'].replace(' ', '%20'), BUILD / 'download_cache' / payload['fileName'],
                        payload['sha256'].lower())
        out.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(vsix) as zf:
            for name in zf.namelist():
                if name.lower().endswith('.dll') and '/redist/' in name.lower():
                    (out / Path(name).name).write_bytes(zf.read(name))


def _sdk_package(sdk_version):
    short = '.'.join(sdk_version.split('.')[:3])
    for vsman in (BUILD / 'xwin-cache' / 'dl').glob('*.vsman'):
        for pkg in json.loads(vsman.read_text()).get('packages', []):
            if pkg['id'] == f'Win11SDK_{short}':
                return {p['fileName'].replace('\\', '/'): p for p in pkg['payloads']}
    raise SystemExit(f'Win11SDK_{short} not found in the VS manifest')


def _sdk_msi_extract(sdk_version, msi, dest):
    """Extract one Windows SDK MSI (plus the external .cab files its Media
    table lists) with msitools; every file is checked against the manifest's
    sha256."""
    payloads = _sdk_package(sdk_version)
    cache = BUILD / 'download_cache' / 'sdk-msi'

    def fetch(name):
        p = payloads[name]
        return download(p['url'].replace(' ', '%20'), cache / Path(name).name, p['sha256'].lower())
    msi_path = fetch(f'Installers/{msi}')
    media = subprocess.run(['msiinfo', 'export', msi_path, 'Media'], capture_output=True, text=True,
                           check=True).stdout.splitlines()[3:]
    for row in media:
        cols = row.split('\t')
        if len(cols) > 3 and cols[3]:
            fetch(f'Installers/{cols[3]}')
    dest.mkdir(parents=True, exist_ok=True)
    run(['msiextract', msi_path, '-C', dest], stdout=subprocess.DEVNULL)


def _toolchain_d3dcompiler(kits, sdk_version):
    """d3dcompiler_47.dll (Windows Kits/10/Redist/D3D) and the DXC DLLs, shipped with the
    browser for ANGLE. It lives in the SDK's "Windows Store Apps Tools" MSI,
    which is not part of what xwin unpacks."""
    if (kits / 'Redist' / 'D3D' / 'x64' / 'd3dcompiler_47.dll').exists() and \
            (kits / 'bin' / sdk_version / 'x64' / 'dxil.dll').exists():
        return
    tmp = BUILD / 'sdk-msi-extract'
    shutil.rmtree(tmp, ignore_errors=True)
    _sdk_msi_extract(sdk_version, 'Windows SDK for Windows Store Apps Tools-x86_en-us.msi', tmp)
    redist = next(tmp.rglob('Redist/D3D'))
    shutil.copytree(redist, kits / 'Redist' / 'D3D', dirs_exist_ok=True)
    # gn also copies dxil.dll/dxcompiler.dll from bin/<sdk version>/<cpu>.
    shutil.copytree(next(tmp.rglob(f'bin/{sdk_version}')), kits / 'bin' / sdk_version, dirs_exist_ok=True)
    shutil.rmtree(tmp)


DBGENG_VERSION = '20260319.1511.0'
DBGENG_SHA256 = '875678516f9ceed4a1c8b9b106d165106fcaa38723ad7c584c47b95b231600de'


def _toolchain_debuggers(kits):
    """dbghelp.dll/dbgcore.dll, which gn copies into the output directory.

    They normally come with the SDK's "Debugging Tools for Windows" feature,
    which is not in the VS manifest. Microsoft publishes the same DLLs on NuGet
    (Microsoft.Debugging.Platform.DbgEng); the pinned sha256 was checked
    against the NuGet catalog's SHA512 package hash.
    """
    if (kits / 'Debuggers' / 'x64' / 'dbghelp.dll').exists():
        return
    name = 'microsoft.debugging.platform.dbgeng'
    pkg = download(f'https://api.nuget.org/v3-flatcontainer/{name}/{DBGENG_VERSION}/{name}.{DBGENG_VERSION}.nupkg',
                   BUILD / 'download_cache' / f'dbgeng-{DBGENG_VERSION}.nupkg', DBGENG_SHA256)
    with zipfile.ZipFile(pkg) as zf:
        for nuget_arch, arch in (('amd64', 'x64'), ('x86', 'x86'), ('arm64', 'arm64')):
            out = kits / 'Debuggers' / arch
            out.mkdir(parents=True, exist_ok=True)
            for dll in ('dbghelp.dll', 'dbgcore.dll'):
                (out / dll).write_bytes(zf.read(f'content/{nuget_arch}/{dll}'))


def step_toolchain(args):
    if is_done('domsub'):
        raise SystemExit('domain substitution already applied: toolchain scripts no longer point at real hosts')
    for name, fn in [('clang', _toolchain_clang), ('rust', _toolchain_rust), ('sysroot', _toolchain_sysroot), ('rc', _toolchain_rc), ('pgo', _toolchain_pgo), ('windows-sources', _toolchain_windows_sources),
                     ('node', _toolchain_node), ('go', _toolchain_go), ('ninja', _toolchain_ninja), ('gn', _toolchain_gn),
                     ('msvc', _toolchain_msvc)]:
        log(f'toolchain: {name}')
        fn()
    mark_done('toolchain')


def _series(patch_dir, skip=frozenset()):
    for line in (patch_dir / 'series').read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and line not in skip:
            yield patch_dir / line


def _apply_hivey_patches(state_patches):
    """Apply the Hivey patches of patches/series not applied yet, in order.

    The tree remembers each applied patch with its sha256, so new patches can
    be added to an existing tree. A patch edited after being applied cannot be
    re-applied on top of itself: that needs a fresh tree (see BUILDING.md).
    """
    applied = dict(state_patches)
    todo = []
    for path in _series(ROOT / 'patches'):
        rel = path.relative_to(ROOT / 'patches').as_posix()
        digest = sha256_file(path)
        if rel in applied:
            if applied[rel] != digest:
                raise SystemExit(f'{rel} changed since it was applied: start from a fresh tree')
            continue
        todo.append((rel, path, digest))
    for rel, path, digest in todo:
        log(f'patch: {rel}')
        patches.apply_patches([path], SRC, patch_bin_path=Path(shutil.which('patch')))
        applied[rel] = digest
        state = load_state()
        state.setdefault('patch', {})['hivey'] = applied
        STATE.write_text(json.dumps(state, indent=2))
    return applied


def step_patch(args):
    state = load_state().get('patch', {})
    if not state.get('done'):
        groups = [
            ('ungoogled-chromium', list(_series(UG / 'patches'))),
            ('ungoogled-chromium-windows', list(_series(UGW / 'patches', WINDOWS_HOST_ONLY_PATCHES))),
        ]
        for name, plist in groups:
            log(f'patches: {name} ({len(plist)})')
            patches.apply_patches(plist, SRC, patch_bin_path=Path(shutil.which('patch')))
    applied = _apply_hivey_patches(state.get('hivey', {}))
    mark_done('patch', hivey=applied)


def hivey_version():
    """Chromium's version with the Hivey revision (HIVEY_REVISION, 1-99) in
    the last field: PATCH = upstream PATCH * 100 + revision. A Hivey-only
    release then installs as an update; web pages still see the upstream
    version (patches/hivey/build/hivey-updater.patch)."""
    major, minor, build, patch = (int(x) for x in chromium_version().split('.'))
    revision = int((ROOT / 'HIVEY_REVISION').read_text().strip())
    if not 1 <= revision <= 99 or patch * 100 + revision > 65535:
        raise SystemExit(f'HIVEY_REVISION {revision} out of range for Chromium {chromium_version()}')
    return major, minor, build, patch * 100 + revision


def _write_hivey_version():
    major, minor, build, patch = hivey_version()
    path = SRC / 'chrome/VERSION'
    path.write_text(f'MAJOR={major}\nMINOR={minor}\nBUILD={build}\nPATCH={patch}\n')
    return f'{major}.{minor}.{build}.{patch}'


def step_brand(args):
    run([sys.executable, ROOT / 'scripts' / 'branding.py', SRC])
    version = _write_hivey_version()
    log(f'version {version}')
    mark_done('brand', version=version)


# Extensions that ship with the browser (extensions/bundled.json), packed as
# signed .crx files. Each has its own key, which decides its extension ID: keep
# the keys private and stable (a new key means a new ID, so existing installs
# would get a second copy). uBlock Origin Lite keeps bundled-extensions.pem
# (HB_EXTENSION_KEY); the others use <name>.pem in HB_KEY_DIR.
BUNDLED = BUILD / 'bundled-extensions'
KEY_DIR = Path(os.environ.get('HB_KEY_DIR', Path.home() / '.config' / 'hivey'))
EXTENSION_KEY = Path(os.environ.get('HB_EXTENSION_KEY', KEY_DIR / 'bundled-extensions.pem'))
# Ed25519 key that signs the update manifest (scripts/release.py). The browser
# embeds its public key and refuses any update not signed with it. Keep it
# private; HB_UPDATE_KEY overrides its location.
UPDATE_KEY = Path(os.environ.get('HB_UPDATE_KEY', Path.home() / '.config' / 'hivey' / 'update-signing.pem'))


def ensure_update_key():
    if not UPDATE_KEY.exists():
        UPDATE_KEY.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'ed25519', '-out', UPDATE_KEY], check=True,
                       capture_output=True)
        UPDATE_KEY.chmod(0o600)
    der = subprocess.run(['openssl', 'pkey', '-in', UPDATE_KEY, '-pubout', '-outform', 'DER'], check=True,
                         capture_output=True).stdout
    return der[-32:]  # SubjectPublicKeyInfo of Ed25519: the raw key is the last 32 bytes


def _write_update_key_header():
    raw = ensure_update_key()
    header = SRC / 'chrome/browser/hivey/update_public_key.h'
    header.parent.mkdir(parents=True, exist_ok=True)
    rows = ',\n'.join('    ' + ', '.join(f'0x{b:02x}' for b in raw[i:i + 8]) for i in range(0, 32, 8))
    header.write_text(
        '// Generated by scripts/hb.py (step "bundle"). Do not edit.\n'
        '#ifndef CHROME_BROWSER_HIVEY_UPDATE_PUBLIC_KEY_H_\n'
        '#define CHROME_BROWSER_HIVEY_UPDATE_PUBLIC_KEY_H_\n\n'
        '#include <stdint.h>\n\n'
        '// Ed25519 public key of the Hivey Browser update manifest signature.\n'
        f'inline constexpr uint8_t kHiveyUpdatePublicKey[32] = {{\n{rows}}};\n\n'
        '#endif  // CHROME_BROWSER_HIVEY_UPDATE_PUBLIC_KEY_H_\n')
    return raw.hex()


def _apply_shield_defaults(unpacked, enable):
    """Hivey defaults for uBlock Origin Lite: extra rulesets on at first run
    (tracking parameters removal, cookie banners)."""
    details_path = unpacked / 'rulesets' / 'ruleset-details.json'
    details = json.loads(details_path.read_text())
    known = {d['id'] for d in details}
    missing = set(enable) - known
    if missing:
        raise SystemExit(f'unknown uBlock Origin Lite rulesets: {sorted(missing)}')
    for d in details:
        if d['id'] in enable:
            d['enabled'] = True
    details_path.write_text(json.dumps(details, indent=1))
    manifest_path = unpacked / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    for r in manifest['declarative_net_request']['rule_resources']:
        if r['id'] in enable:
            r['enabled'] = True
    manifest_path.write_text(json.dumps(manifest, indent=2))


def _extension_key(name):
    return EXTENSION_KEY if name == 'hivey-shield' else KEY_DIR / f'{name}.pem'


def _unpack_release_zip(name, spec, unpacked):
    """A published .zip, sha256-pinned (uBlock Origin Lite)."""
    archive = download(spec['url'], BUILD / 'download_cache' / Path(spec['url']).name, spec['sha256'])
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(unpacked)
    version = json.loads((unpacked / 'manifest.json').read_text())['version']
    if version != spec['version']:
        raise SystemExit(f"{spec['name']} archive is {version}, expected {spec['version']}")
    if name == 'hivey-shield':
        _apply_shield_defaults(unpacked, spec.get('enable_rulesets', []))
    return version


def _unpack_submodule(name, spec, unpacked):
    """A pinned git submodule (the Hivey AI sidebar): its files plus its
    Chromium manifest. The version is major.minor from the manifest and the
    submodule's commit count, so each update installs as a newer version;
    "display_name" renames it in the browser."""
    src = ROOT / spec['path']
    for item in spec['files']:
        path = src / item
        if path.is_dir():
            shutil.copytree(path, unpacked / item)
        else:
            shutil.copy2(path, unpacked / item)
    manifest = json.loads((src / spec['manifest']).read_text())
    count = subprocess.run(['git', '-C', src, 'rev-list', '--count', 'HEAD'], check=True, capture_output=True,
                           text=True).stdout.strip()
    major_minor = '.'.join(manifest['version'].split('.')[:2])
    manifest['version'] = f'{major_minor}.{count}'
    if spec.get('display_name'):
        # The name the browser shows (side panel header, menus, tooltips).
        manifest['name'] = spec['display_name']
        manifest.pop('short_name', None)
        if 'action' in manifest:
            manifest['action']['default_title'] = spec['display_name']
    (unpacked / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest['version']


# The Hivey bar's icons: Phosphor Icons (MIT, https://phosphoricons.com),
# duotone style, drawn in white at build time and tinted by the browser.
PHOSPHOR_VERSION = '2.1.1'
PHOSPHOR_URL = f'https://registry.npmjs.org/@phosphor-icons/core/-/core-{PHOSPHOR_VERSION}.tgz'
PHOSPHOR_SHA512 = ('v4ARvrip4qBCImOE5rmPUylOEK4iiED9ZyKjcvzuezqMaiRASCHKcRIuvvxL/'
                   'twvLpkfnEODCOJp5dM4eZilxQ==')  # npm "integrity", base64
# Sidebar workspace (data-mode) -> icon. A workspace not listed here keeps the
# sidebar's own icon.
WORKSPACE_ICONS = {
    'chat': 'chat-circle-dots', 'web': 'globe-hemisphere-west', 'agent': 'robot',
    'translate': 'translate', 'improve': 'magic-wand', 'image': 'image', 'pdf': 'file-pdf',
    'security': 'shield-check', 'wisebase': 'books', 'benchmark': 'chart-bar', 'mcp': 'plugs-connected',
}
TOOL_ICONS = {
    'Cyber': 'fingerprint', 'Performance': 'gauge', 'History': 'clock-counter-clockwise',
    'Bookmarks': 'bookmark-simple', 'Settings': 'gear-six', 'App': 'app-window',
}
# The bar's default order (the sidebar's own order for the others, after).
WORKSPACE_ORDER = ['chat', 'web', 'agent', 'mcp', 'translate', 'improve', 'image', 'pdf', 'security',
                   'wisebase', 'benchmark']
# "Multicolor" icons: a color that means something for each item, as
# (on a dark toolbar, on a light toolbar). Unlisted workspaces use the accent.
ICON_COLORS = {
    'chat': ('#a5b4fc', '#4f46e5'),       # indigo: conversation
    'web': ('#7dd3fc', '#0284c7'),        # sky: the web
    'agent': ('#c4b5fd', '#7c3aed'),      # violet: autonomous AI
    'mcp': ('#5eead4', '#0d9488'),        # teal: connected services
    'translate': ('#fcd34d', '#b45309'),  # amber: languages
    'improve': ('#f9a8d4', '#db2777'),    # pink: magic wand
    'image': ('#fdba74', '#ea580c'),      # orange: pictures
    'pdf': ('#fca5a5', '#dc2626'),        # red: PDF documents
    'security': ('#86efac', '#16a34a'),   # green: protection
    'wisebase': ('#fde68a', '#a16207'),   # gold: knowledge
    'benchmark': ('#a5f3fc', '#0891b2'),  # cyan: measures
    'Cyber': ('#6ee7b7', '#059669'),      # emerald: investigation
    'Performance': ('#bef264', '#65a30d'),  # lime: speed
    'History': ('#93c5fd', '#2563eb'),    # blue: time
    'Bookmarks': ('#fda4af', '#e11d48'),  # rose: favorites
    'Settings': ('#cbd5e1', '#475569'),   # slate: neutral
    'App': ('#e2e8f0', '#334155'),        # neutral: user sites
}


def _c_color(hex_color):
    return f'0x{hex_color[1:].upper()}'


def _icon_colors(key):
    dark, light = ICON_COLORS.get(key, ('#000000', '#000000'))
    has = 'true' if key in ICON_COLORS else 'false'
    return f'{_c_color(dark)}, {_c_color(light)}, {has}'
ICON_PX = 40  # drawn for 20 DIP at 2x


FLAG_ICONS_VERSION = '7.6.0'
FLAG_ICONS_URL = f'https://registry.npmjs.org/flag-icons/-/flag-icons-{FLAG_ICONS_VERSION}.tgz'
FLAG_ICONS_SHA512 = 'hir/PsXwr0EESyizKrXJzmkzpLIMf+1vlNKLqAfvdh+bsU94a7LYWTiubkHKqptGoCPzOUGcm6c4PfC9/BaGSQ=='
FLAG_PX = (32, 24)  # 16 x 12 DIP at 2x


def _flag_icons_dir():
    """flag-icons (MIT), its 4:3 SVG flags, downloaded once and checked."""
    cache = BUILD / 'downloads' / f'flag-icons-{FLAG_ICONS_VERSION}'
    flags = cache / 'package' / 'flags' / '4x3'
    if flags.is_dir():
        return flags
    cache.mkdir(parents=True, exist_ok=True)
    tgz = cache / 'flag-icons.tgz'
    with urllib.request.urlopen(FLAG_ICONS_URL, timeout=120) as r:
        tgz.write_bytes(r.read())
    digest = base64.b64encode(hashlib.sha512(tgz.read_bytes()).digest()).decode()
    if digest != FLAG_ICONS_SHA512:
        raise SystemExit(f'flag-icons {FLAG_ICONS_VERSION}: checksum mismatch')
    with tarfile.open(tgz) as t:
        t.extractall(cache, filter='data')
    return flags


def _write_flags():
    """chrome/browser/hivey/hivey_flags.h: every country's flag (ISO 3166
    code) as a small PNG with rounded corners, for the location bar's server
    chip (Windows' emoji font has no flags)."""
    import io
    import cairosvg
    from PIL import Image, ImageDraw
    w, h = FLAG_PX
    rounded = Image.new('L', (w, h), 0)
    ImageDraw.Draw(rounded).rounded_rectangle((0, 0, w - 1, h - 1), radius=4, fill=255)
    arrays, entries = [], []
    for svg in sorted(_flag_icons_dir().glob('*.svg')):
        code = svg.stem.upper()
        if len(code) != 2 or not code.isalpha():
            continue
        png = cairosvg.svg2png(bytestring=svg.read_bytes(), output_width=w, output_height=h)
        image = Image.open(io.BytesIO(png)).convert('RGBA')
        alpha = image.getchannel('A')
        image.putalpha(Image.composite(alpha, Image.new('L', (w, h), 0), rounded))
        out = io.BytesIO()
        image.save(out, 'PNG', optimize=True)
        name = f'kHiveyFlag{code}'
        arrays.append(_c_bytes(name, out.getvalue()))
        entries.append(f'    {{"{code}", {name}, sizeof({name})}},')
    (SRC / 'chrome/browser/hivey/hivey_flags.h').write_text(
        '// Generated by scripts/hb.py (step "bundle"). Do not edit.\n'
        f'// Flags: flag-icons {FLAG_ICONS_VERSION} (MIT, https://flagicons.lipis.dev), 4:3,\n'
        f'// {w} x {h} px with rounded corners.\n'
        '#ifndef CHROME_BROWSER_HIVEY_HIVEY_FLAGS_H_\n#define CHROME_BROWSER_HIVEY_HIVEY_FLAGS_H_\n\n'
        '#include <stddef.h>\n\n' + ''.join(arrays) + '\n'
        '// Sorted by code.\nstruct HiveyFlag {\n  const char code[3];\n  const unsigned char* png;\n'
        '  size_t size;\n};\ninline constexpr HiveyFlag kHiveyFlags[] = {\n' + '\n'.join(entries) + '\n};\n\n'
        '#endif  // CHROME_BROWSER_HIVEY_HIVEY_FLAGS_H_\n')
    log(f'flags: {len(entries)} countries (flag-icons {FLAG_ICONS_VERSION})')


def _phosphor_duotone_dir():
    cache = BUILD / 'downloads' / f'phosphor-{PHOSPHOR_VERSION}'
    icons = cache / 'package' / 'assets' / 'duotone'
    if icons.is_dir():
        return icons
    cache.mkdir(parents=True, exist_ok=True)
    tgz = cache / 'core.tgz'
    with urllib.request.urlopen(PHOSPHOR_URL, timeout=120) as r:
        tgz.write_bytes(r.read())
    digest = base64.b64encode(hashlib.sha512(tgz.read_bytes()).digest()).decode()
    if digest != PHOSPHOR_SHA512:
        raise SystemExit(f'Phosphor Icons {PHOSPHOR_VERSION}: checksum mismatch')
    with tarfile.open(tgz) as t:
        t.extractall(cache, filter='data')
    return icons


def _white_png(svg):
    import cairosvg
    if 'xmlns=' not in svg:
        svg = svg.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    return cairosvg.svg2png(bytestring=svg.replace('currentColor', '#ffffff').encode(),
                            output_width=ICON_PX, output_height=ICON_PX)


def _sidebar_workspaces(src):
    """The sidebar's workspaces (the rail tabs of sidebar.html): mode, English
    and French titles (from the sidebar's own strings) and its SVG icon."""
    html = (src / 'src/sidebar/sidebar.html').read_text()
    i18n = (src / 'src/lib/i18n.js').read_text()

    def strings(lang):
        start = i18n.index(f'const {lang} = {{')
        block = i18n[start:i18n.index('\n};', start)]
        return dict(re.findall(r'^\s*"([\w.]+)":\s*"((?:[^"\\]|\\.)*)",?$', block, re.M))

    titles = {'en': strings('EN'), 'fr': strings('FR')}
    tabs = []
    for button in re.finditer(r'<button class="railtab[^"]*"([^>]*)>(<svg.*?</svg>)</button>', html, re.S):
        attrs, svg = button.groups()
        mode = re.search(r'data-mode="([\w-]+)"', attrs)
        if not mode:
            continue  # links and the "+" button, not workspaces
        key = re.search(r'data-i18n-title="([\w.]+)"', attrs)
        fallback = re.search(r'title="([^"]*)"', attrs)
        tab = {'mode': mode.group(1), 'svg': svg, 'title': {}}
        for lang, table in titles.items():
            tab['title'][lang] = (key and table.get(key.group(1))) or (fallback and fallback.group(1)) \
                or mode.group(1)
        tabs.append(tab)
    if not tabs:
        raise SystemExit('no workspace found in the sidebar\'s rail (sidebar.html changed?)')
    return tabs


def _sidebar_frame_hosts(src):
    """Domains whose pages the sidebar shows in frames (its web chats): the
    request domains of its header-rewriting rules."""
    hosts = []
    for rules in sorted((src / 'rules').glob('*.json')):
        for rule in json.loads(rules.read_text()):
            if rule.get('action', {}).get('type') == 'modifyHeaders':
                hosts += rule.get('condition', {}).get('requestDomains', [])
    return sorted(set(hosts))


def _c_string(text):
    out = []
    for byte in text.encode():
        ch = chr(byte)
        out.append(ch if 32 <= byte < 127 and ch not in '"\\?' else f'\\{byte:03o}')
    return '"' + ''.join(out) + '"'


def _c_bytes(name, data):
    rows = [', '.join(f'0x{b:02x}' for b in data[i:i + 16]) for i in range(0, len(data), 16)]
    return f'inline constexpr unsigned char {name}[] = {{\n    ' + ',\n    '.join(rows) + '};\n'


def _write_bar_assets(src):
    """chrome/browser/hivey/hivey_bar_assets.h: the Hivey bar's workspaces and
    icons, and the web chat hosts Hivey Tools keeps when its site access is
    withheld. Built into the browser, so the bar is complete at once."""
    phosphor = _phosphor_duotone_dir()
    tabs = _sidebar_workspaces(src)
    order = {mode: i for i, mode in enumerate(WORKSPACE_ORDER)}
    tabs.sort(key=lambda t: order.get(t['mode'], len(order)))
    arrays, workspaces, tools = [], [], []
    for i, tab in enumerate(tabs):
        name = WORKSPACE_ICONS.get(tab['mode'])
        svg = (phosphor / f'{name}-duotone.svg').read_text() if name else tab['svg']
        arrays.append(_c_bytes(f'kHiveyBarWorkspacePng{i}', _white_png(svg)))
        workspaces.append(f'    {{{_c_string(tab["mode"])}, {_c_string(tab["title"]["en"])}, '
                          f'{_c_string(tab["title"]["fr"])}, kHiveyBarWorkspacePng{i}, '
                          f'sizeof(kHiveyBarWorkspacePng{i}), {_icon_colors(tab["mode"])}}},')
    for tool, name in TOOL_ICONS.items():
        arrays.append(_c_bytes(f'kHiveyBar{tool}Png', _white_png((phosphor / f'{name}-duotone.svg').read_text())))
        tools.append(f'inline constexpr HiveyBarIcon kHiveyBar{tool}Icon = {{kHiveyBar{tool}Png, '
                     f'sizeof(kHiveyBar{tool}Png), {_icon_colors(tool)}}};')
    hosts = _sidebar_frame_hosts(src)
    header = SRC / 'chrome/browser/hivey/hivey_bar_assets.h'
    header.write_text(
        '// Generated by scripts/hb.py (step "bundle"). Do not edit.\n'
        '// Icons: Phosphor Icons (MIT), duotone, white; the browser tints them\n'
        '// (classic) or fills them with a gradient (modern).\n'
        '#ifndef CHROME_BROWSER_HIVEY_HIVEY_BAR_ASSETS_H_\n'
        '#define CHROME_BROWSER_HIVEY_HIVEY_BAR_ASSETS_H_\n\n'
        '#include <stddef.h>\n\n'
        + ''.join(arrays) + '\n'
        '// Multicolor icons: 0xRRGGBB on a dark / a light toolbar (has_color is\n'
        '// false for an item without its own color).\n'
        'struct HiveyBarIcon {\n  const unsigned char* png;\n  size_t size;\n'
        '  unsigned int color_on_dark;\n  unsigned int color_on_light;\n  bool has_color;\n};\n\n'
        '// Hivey Tools\' workspaces (the sidebar\'s rail), in its order.\n'
        'struct HiveyBarWorkspace {\n  const char* mode;\n  const char* title_en;\n'
        '  const char* title_fr;\n  const unsigned char* png;\n  size_t png_size;\n'
        '  unsigned int color_on_dark;\n  unsigned int color_on_light;\n  bool has_color;\n};\n'
        'inline constexpr HiveyBarWorkspace kHiveyBarWorkspaces[] = {\n' + '\n'.join(workspaces) + '\n};\n\n'
        + '\n'.join(tools) + '\n\n'
        '// Sites Hivey Tools shows in frames (its web chats).\n'
        'inline constexpr const char* kHiveyAiFrameHosts[] = {\n'
        + ''.join(f'    {_c_string(h)},\n' for h in hosts) + '};\n\n'
        '#endif  // CHROME_BROWSER_HIVEY_HIVEY_BAR_ASSETS_H_\n')
    log(f'Hivey bar: {len(tabs)} sidebar workspaces ({", ".join(t["mode"] for t in tabs)}), '
        f'{len(hosts)} web chat hosts')


def _unpack_directory(name, spec, unpacked):
    """An extension kept in this repository (Hivey Cyber); PNG icons are
    rendered from its SVG."""
    shutil.copytree(ROOT / spec['path'], unpacked, dirs_exist_ok=True)
    if spec.get('icon_svg'):
        import cairosvg
        (unpacked / 'icons').mkdir(exist_ok=True)
        for size in (16, 32, 48, 128):
            cairosvg.svg2png(url=str(unpacked / spec['icon_svg']), write_to=str(unpacked / f'icons/icon-{size}.png'),
                             output_width=size, output_height=size)
    return json.loads((unpacked / 'manifest.json').read_text())['version']


def step_bundle(args):
    """Generated inputs of the build: the bundled extensions (signed .crx files
    and a header listing them) and the public key of the update signature."""
    update_key = _write_update_key_header()
    specs = json.loads((ROOT / 'extensions' / 'bundled.json').read_text())
    shutil.rmtree(BUNDLED, ignore_errors=True)
    BUNDLED.mkdir(parents=True)
    unpackers = {'release-zip': _unpack_release_zip, 'submodule': _unpack_submodule, 'directory': _unpack_directory}
    entries, defines, info = [], [], {}
    for name, spec in specs.items():
        unpacked = BUNDLED / name
        unpacked.mkdir()
        version = unpackers[spec['type']](name, spec, unpacked)
        crx = BUNDLED / f'{name}.crx'
        ext_id = crx3.pack(unpacked, _extension_key(name), crx)
        macro = name.upper().replace('-', '_').replace('HIVEY_', 'HIVEY_BUNDLED_')
        entries.append(f'    {{"{ext_id}", "{version}", "{name}.crx", {str(spec.get("pin", False)).lower()}}},'
                       f'  // {spec["name"]} ({spec["license"]})')
        defines.append(f'#define {macro}_ID "{ext_id}"')
        info[name] = {'id': ext_id, 'version': version, 'sha256': sha256_file(crx)}
        log(f'bundled {spec["name"]} {version}: id {ext_id}, {crx.stat().st_size // (1 << 20)} MiB')
    header = SRC / 'chrome/browser/hivey/bundled_extensions.h'
    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_text(
        '// Generated by scripts/hb.py (step "bundle"). Do not edit.\n'
        '#ifndef CHROME_BROWSER_HIVEY_BUNDLED_EXTENSIONS_H_\n'
        '#define CHROME_BROWSER_HIVEY_BUNDLED_EXTENSIONS_H_\n\n'
        + '\n'.join(defines) + '\n\n'
        '// Extensions that ship with the browser, in <module dir>/extensions.\n'
        'struct HiveyBundledExtension {\n'
        '  const char* id;\n'
        '  const char* version;\n'
        '  const char* crx;\n'
        '  bool pinned;  // shown in the toolbar on install\n'
        '};\n'
        'inline constexpr HiveyBundledExtension kHiveyBundledExtensions[] = {\n'
        + '\n'.join(entries) + '\n};\n\n'
        '#endif  // CHROME_BROWSER_HIVEY_BUNDLED_EXTENSIONS_H_\n')
    log(f'update public key {update_key}')
    for spec in specs.values():
        if spec.get('bar_tabs'):
            _write_bar_assets(ROOT / spec['path'])
    _write_flags()
    # The offline IP-to-country database of the location bar's server chip
    # (scripts/geoip.py); the download cache lives outside BUNDLED, which this
    # step wipes.
    geoip_bin, geoip_month = geoip.build(BUNDLED, BUILD / 'downloads' / 'geoip')
    mark_done('bundle', extensions=info, update_key=update_key,
              geoip={'month': geoip_month, 'sha256': sha256_file(geoip_bin)})


def _stage_bundled_extensions():
    """Put the .crx files and the GeoIP database where the browser looks for
    them: <module dir>/extensions (the Windows installer packs
    out/Default/Extensions)."""
    dest = OUT / ('Extensions' if TARGET == 'win' else 'extensions')
    dest.mkdir(parents=True, exist_ok=True)
    for f in [*BUNDLED.glob('*.crx'), BUNDLED / geoip.FILE_NAME]:
        if f.exists():
            shutil.copy2(f, dest / f.name)


def step_domsub(args):
    domain_substitution.apply_substitution(UG / 'domain_regex.list', UG / 'domain_substitution.list', SRC,
                                           BUILD / 'domsubcache.tar.gz')
    mark_done('domsub')


def gn_args():
    def parse(path, skip=()):
        out = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and line.split('=')[0].strip() not in skip:
                out.append(line)
        return out
    lines = parse(UG / 'flags.gn')
    if TARGET == 'win':
        lines += parse(UGW / 'flags.windows.gn', WINDOWS_HOST_ONLY_FLAGS)
    lines += parse(ROOT / 'flags.hivey.gn') + parse(ROOT / f'flags.hivey.{TARGET}.gn')
    if ccache := _ccache():
        lines.append(f'cc_wrapper="{ccache}"')
    merged = {}
    for line in lines:  # later files override earlier ones
        merged[line.split('=')[0].strip()] = line
    return '\n'.join(merged.values()) + '\n'


# One compiler cache for every build tree of this host (the manual one and
# autoupdate's): a rebuild after a change, or a fresh tree of the same
# Chromium, recompiles only what really changed. HB_CCACHE=0 turns it off.
CCACHE_DIR = Path(os.environ.get('HB_CCACHE_DIR', '/root/projects/hivey-ccache'))


def _ccache():
    if os.environ.get('HB_CCACHE', '1') == '0':
        return None
    return shutil.which('ccache')


def _ccache_env():
    return {
        'CCACHE_DIR': str(CCACHE_DIR),
        'CCACHE_MAXSIZE': os.environ.get('HB_CCACHE_SIZE', '150G'),
        # Paths inside the tree are hashed relative to it: two trees share hits.
        'CCACHE_BASEDIR': str(SRC),
        # Each tree has its own copy of clang: compare its contents, not its path.
        'CCACHE_COMPILERCHECK': 'content',
        # Chromium compiles with Clang modules: cacheable only in direct and
        # depend mode (dependencies from the compiler's own -MD output).
        'CCACHE_SLOPPINESS': 'include_file_mtime,include_file_ctime,time_macros,file_macro,pch_defines,modules',
        'CCACHE_DIRECT': '1',
        'CCACHE_DEPEND': '1',
        'CCACHE_NOHASHDIR': '1',
    }


def _build_env():
    env = {**os.environ,
           # Go (Dawn's generators) must never fetch toolchains or modules.
           'GOTOOLCHAIN': 'local', 'GOPROXY': 'off', 'GOFLAGS': '-mod=mod',
           'GOPATH': str(BUILD / 'gopath'), 'GOCACHE': str(BUILD / 'gopath' / 'cache')}
    if TARGET == 'win':
        ensure_winsysroot()
        env['DEPOT_TOOLS_WIN_TOOLCHAIN'] = '1'
    if _ccache():
        env.update(_ccache_env())
    return env


def step_configure(args):
    env = _build_env()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'args.gn').write_text(gn_args())
    run([TOOLS / 'gn', 'gen', OUT, '--fail-on-unused-args'], cwd=SRC, env=env)
    mark_done('configure')


def _available_gb():
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):
                return int(line.split()[1]) / (1 << 20)
    except OSError:
        pass
    return 8.0


# Memory left to the host's other services (the LLM server loads a model on
# demand) while a build runs.
MEM_HEADROOM_GB = 16


def build_mem_max():
    """The build's memory cap (its systemd scope): HB_MEM_MAX ("26G",
    "none"), else what is available now minus MEM_HEADROOM_GB, at least 16G.
    Past it the kernel kills the build, never a service."""
    if os.environ.get('HB_MEM_MAX'):
        return os.environ['HB_MEM_MAX']
    return f'{max(16, int(_available_gb() - MEM_HEADROOM_GB))}G'


def args_jobs():
    """Parallel compile jobs: HB_JOBS, else what the machine can afford now:
    one per CPU, and about 3 GB of the build's memory cap per job (compilers
    starved of memory crash at random)."""
    if os.environ.get('HB_JOBS'):
        return int(os.environ['HB_JOBS'])
    available_gb = _available_gb()
    mem_max = build_mem_max()
    if mem_max.endswith('G') and mem_max[:-1].isdigit():
        available_gb = min(available_gb, float(mem_max[:-1]))
    return max(2, min(os.cpu_count() or 2, int(available_gb // 3)))


def step_build(args):
    env = _build_env()
    targets = args.targets or (['chrome', 'mini_installer'] if TARGET == 'win' else ['chrome'])
    jobs = args_jobs()
    cmd = [TOOLS / 'ninja', '-C', OUT, '-j', str(jobs)] + targets
    if os.environ.get('HB_KEEP_GOING'):  # e.g. 0 = keep going past every failure
        cmd[1:1] = ['-k', os.environ['HB_KEEP_GOING']]
    # Run inside a transient systemd scope with a memory cap: if a ThinLTO link
    # outgrows it, the kernel kills the build, never a production service.
    mem_max = build_mem_max()
    if shutil.which('systemd-run') and mem_max != 'none':
        cmd = ['systemd-run', '--scope', '--quiet', '--collect', '-p', f'MemoryMax={mem_max}',
               '-p', 'MemorySwapMax=0', '-p', 'CPUWeight=10', '-p', 'IOWeight=10', '--'] + cmd
    _stage_bundled_extensions()
    log(f'building with {jobs} jobs, memory cap {mem_max}'
        + (f', ccache in {CCACHE_DIR}' if _ccache() else ''))
    try:
        run(cmd, cwd=SRC, env=env)
    except subprocess.CalledProcessError:
        if os.environ.get('HB_KEEP_GOING') or jobs <= 2:
            raise
        # A compiler that crashed for want of memory: once more with half the
        # jobs (ninja resumes where it stopped).
        log(f'build failed with {jobs} jobs, retrying with {jobs // 2}')
        cmd[cmd.index(str(jobs), cmd.index('-j'))] = str(jobs // 2)
        run(cmd, cwd=SRC, env=env)
    mark_done('build')


# Files of a Linux build that make up the portable package (as in
# ungoogled-chromium-portablelinux); optional ones are skipped when absent.
LINUX_FILES = ['chrome', 'chrome_100_percent.pak', 'chrome_200_percent.pak', 'chrome_crashpad_handler',
               'chrome-wrapper', 'icudtl.dat', 'libEGL.so', 'libGLESv2.so', 'libvk_swiftshader.so',
               'libvulkan.so.1', 'locales', 'product_logo_48.png', 'resources.pak', 'v8_context_snapshot.bin',
               'vk_swiftshader_icd.json', 'xdg-mime', 'xdg-settings', 'extensions']
LINUX_REQUIRED = {'chrome', 'resources.pak', 'icudtl.dat', 'locales', 'v8_context_snapshot.bin'}

LINUX_LAUNCHER = """#!/bin/sh
# Hivey Browser launcher: runs the browser from wherever this folder lives.
HERE="$(dirname "$(readlink -f "$0")")"
export CHROME_WRAPPER="$(readlink -f "$0")"
# The window's class (WM_CLASS / Wayland app id): hivey-browser, as in the
# desktop entry, so docks show its icon.
export CHROME_DESKTOP=hivey-browser.desktop
exec "$HERE/chrome" "$@"
"""

LINUX_DESKTOP_ENTRY = """[Desktop Entry]
Version=1.0
Type=Application
Name={product_name}
GenericName=Web Browser
Comment=Privacy-first, customizable web browser
Exec=hivey-browser %U
Icon=hivey-browser
Terminal=false
Categories=Network;WebBrowser;
MimeType=text/html;text/xml;application/xhtml+xml;x-scheme-handler/http;x-scheme-handler/https;
StartupWMClass=hivey-browser
"""


# The Windows setup wizard (NSIS), a front end to mini_installer.
WINDOWS_SETUP_NSI = ROOT / 'installer' / 'windows' / 'hivey-setup.nsi'


def _nsis_string(text):
    return text.replace('$', '$$').replace('"', "'")


def _write_setup_addons(path):
    """The wizard's add-on sections (NSIS macros), one per bundled extension,
    with its extension ID from the bundle step: an add-on left out is
    recorded as removed by the user in the initial preferences."""
    specs = json.loads((ROOT / 'extensions' / 'bundled.json').read_text())
    ids = load_state().get('bundle', {}).get('extensions', {})
    macros = {'SECTIONS': [], 'STRINGS': [], 'DESCRIPTIONS': [], 'UNSELECTED_IDS': [], 'SILENT_OPTIONS': []}
    for name, spec in specs.items():
        if name not in ids:
            raise SystemExit(f'{name}: no extension ID, run hb.py bundle first')
        key = name.replace('-', '_')
        section = f'SecAddon_{key}'
        setup = spec.get('setup', {})
        title = _nsis_string(spec.get('display_name', spec['name']))
        unchecked = '' if setup.get('default', True) else '/o '
        macros['SECTIONS'].append(f'  Section {unchecked}"{title}" {section}\n  SectionEnd')
        for lang, nsis_lang in (('en', 'ENGLISH'), ('fr', 'FRENCH')):
            desc = _nsis_string(setup.get(lang) or setup.get('en') or f'{spec["name"]} ({spec["license"]})')
            macros['STRINGS'].append(f'  LangString AddonDesc_{key} ${{LANG_{nsis_lang}}} "{desc}"')
        macros['DESCRIPTIONS'].append(f'  !insertmacro MUI_DESCRIPTION_TEXT ${{{section}}} "$(AddonDesc_{key})"')
        macros['UNSELECTED_IDS'].append(f'  ${{IfNot}} ${{SectionIsSelected}} ${{{section}}}\n'
                                        f'    StrCpy $R9 \'$R9"{ids[name]["id"]}",\'\n'
                                        f'  ${{EndIf}}')
        macros['SILENT_OPTIONS'].append(f'  ClearErrors\n'
                                        f'  ${{GetOptions}} $Params "/NO-{name}" $0\n'
                                        f'  ${{IfNot}} ${{Errors}}\n'
                                        f'    !insertmacro UnselectSection ${{{section}}}\n'
                                        f'  ${{EndIf}}')
    path.write_text('; Generated by scripts/hb.py (step "package") from extensions/bundled.json. Do not edit.\n'
                    + ''.join(f'!macro HIVEY_ADDON_{macro}\n' + '\n'.join(lines) + '\n!macroend\n'
                              for macro, lines in macros.items()),
                    encoding='utf-8')


def _make_setup_wizard(version, mini_installer, dest):
    """The setup wizard, embedding the mini_installer (makensis, from the
    nsis package, runs on Linux)."""
    makensis = shutil.which('makensis')
    if not makensis:
        raise SystemExit('makensis is missing: apt-get install nsis')
    addons = BUILD / 'setup-addons.nsh'
    _write_setup_addons(addons)
    run([makensis, '-V2', '-INPUTCHARSET', 'UTF8', f'-DVERSION={version}', f'-DMINI_INSTALLER={mini_installer}',
         f'-DICON={SRC / "chrome/installer/mini_installer/mini_installer.ico"}', f'-DLICENSE_FILE={ROOT / "LICENSE"}',
         f'-DADDONS_NSH={addons}', f'-DOUTFILE={dest}', WINDOWS_SETUP_NSI])


def step_package(args):
    """Release artifacts in $HB_BUILD_DIR/dist, listed in SHA256SUMS.

    Windows: the setup wizard (-installer.exe, installer/windows/hivey-setup.nsi)
    and the bare mini_installer.exe (-update.exe), which the wizard embeds and
    the browser's updater runs. Linux: a portable .tar.xz (the browser, a
    launcher script, a .desktop entry and the icon).
    """
    v = dict(line.split('=') for line in (SRC / 'chrome/VERSION').read_text().split())
    full = f"{v['MAJOR']}.{v['MINOR']}.{v['BUILD']}.{v['PATCH']}"
    DIST.mkdir(parents=True, exist_ok=True)
    if TARGET == 'win':
        update = DIST / f'hivey-browser-{full}-windows-x64-update.exe'
        shutil.copy2(OUT / 'mini_installer.exe', update)
        artifact = DIST / f'hivey-browser-{full}-windows-x64-installer.exe'
        _make_setup_wizard(full, update, artifact)
        artifacts = [update, artifact]
    else:
        brand = json.loads((ROOT / 'brand' / 'brand.json').read_text())
        name = f'hivey-browser-{full}-linux-x64'
        stage = DIST / name
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True)
        for f in LINUX_FILES:
            src = OUT / f
            if not src.exists():
                if f in LINUX_REQUIRED:
                    raise SystemExit(f'{src} is missing: build first')
                continue
            if src.is_dir():
                shutil.copytree(src, stage / f)
            else:
                shutil.copy2(src, stage / f)
        (stage / 'hivey-browser').write_text(LINUX_LAUNCHER)
        (stage / 'hivey-browser').chmod(0o755)
        (stage / 'hivey-browser.desktop').write_text(LINUX_DESKTOP_ENTRY.format(**brand))
        if (OUT / 'product_logo_48.png').exists():
            shutil.copy2(OUT / 'product_logo_48.png', stage / 'hivey-browser.png')
        artifact = DIST / f'{name}.tar.xz'
        run(['tar', '-C', DIST, '-cJf', artifact, name])
        shutil.rmtree(stage)
        artifacts = [artifact]
    names = {a.name for a in artifacts}
    sums = DIST / 'SHA256SUMS'
    lines = [l for l in (sums.read_text().splitlines() if sums.exists() else []) if l.split()[-1] not in names]
    lines += [f'{sha256_file(a)}  {a.name}' for a in artifacts]
    sums.write_text('\n'.join(sorted(lines, key=lambda l: l.split()[-1])) + '\n')
    for a in artifacts:
        log(f'package: {a} ({a.stat().st_size // (1 << 20)} MiB)')
    mark_done('package', artifact=artifact.name, artifacts=sorted(names))


def step_status(args):
    log(f'build dir: {BUILD}  (Chromium {chromium_version()}, target {TARGET})')
    for s in STEPS:
        print(f"  {'✔' if is_done(s) else '·'} {s}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('step', choices=STEPS + ['all', 'status'])
    p.add_argument('targets', nargs='*', help='ninja targets for `build`')
    p.add_argument('--force', action='store_true', help='re-run a step even if already done')
    p.add_argument('--full-priority', action='store_true', help='do not lower CPU/IO priority')
    args = p.parse_args()
    if not args.full_priority:
        lower_priority()
    BUILD.mkdir(parents=True, exist_ok=True)
    os.environ['PATH'] = f"{TOOLS}:{os.environ['PATH']}"
    fns = {s: globals()[f'step_{s}'] for s in STEPS + ['status']}
    if args.step == 'all':
        for s in STEPS:
            if is_done(s) and s not in ('build', 'patch', 'package'):
                continue
            fns[s](args)
    else:
        if args.step in STEPS and is_done(args.step) and not args.force and \
                args.step not in ('build', 'patch', 'package'):
            log(f'{args.step}: already done (use --force to re-run)')
            return
        fns[args.step](args)


if __name__ == '__main__':
    main()
