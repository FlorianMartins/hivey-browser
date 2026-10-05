#!/usr/bin/env python3
"""Hivey Browser build orchestrator.

Cross-compiles a Windows x64 build of Hivey Browser from a Linux host, on top
of ungoogled-chromium. Every step is idempotent and records a stamp, so an
interrupted run can be resumed with `hb.py all`.

    hb.py fetch       download + verify the Chromium source tarball
    hb.py unpack      extract it into $HB_BUILD_DIR/src
    hb.py prune       remove prebuilt binaries (ungoogled pruning list)
    hb.py toolchain   fetch build-only host tools + MSVC CRT/Windows SDK (xwin)
    hb.py patch       ungoogled + ungoogled-windows (selected) + Hivey patches
    hb.py brand       apply brand/brand.json (names, paths, strings, icons)
    hb.py domsub      ungoogled domain substitution
    hb.py configure   write args.gn and run `gn gen`
    hb.py build       ninja (low CPU/IO priority)
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
OUT = SRC / 'out' / 'Default'
TOOLS = BUILD / 'tools'
STATE = BUILD / '.hb-state.json'

sys.path.insert(0, str(UG / 'utils'))
import downloads  # noqa: E402
import domain_substitution  # noqa: E402
import patches  # noqa: E402
import prune_binaries  # noqa: E402
sys.path.pop(0)

STEPS = ['fetch', 'unpack', 'prune', 'toolchain', 'patch', 'brand', 'domsub', 'configure', 'build']

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

# GN args from ungoogled-chromium-windows that assume upstream LLVM/Rust.
WINDOWS_HOST_ONLY_FLAGS = {'use_sysroot'}


def log(msg):
    print(f'\033[1;33m[hb]\033[0m {msg}', flush=True)


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def mark_done(step, **info):
    state = load_state()
    state[step] = {'done': True, **info}
    STATE.write_text(json.dumps(state, indent=2))


def is_done(step):
    return load_state().get(step, {}).get('done', False)


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


def step_prune(args):
    pruning = (UG / 'pruning.list').read_text().splitlines()
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
    """Windows x64 PGO profile (execution counters, no code), normally fetched
    by a gclient hook; checked against the md5 GCS reports for the object."""
    name = (SRC / 'chrome/build/win64.pgo.txt').read_text().strip()
    dest = SRC / 'chrome/build/pgo_profiles' / name
    if dest.exists():
        return
    url = _gcs('chromium-optimization-profiles/pgo_profiles', name)
    # The object is stored gzip-compressed and GCS decompresses it on the fly;
    # the md5 it publishes is the one of the stored (compressed) bytes.
    req = urllib.request.Request(url, headers={'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(req) as r:
        md5 = [h.split('=', 1)[1] for h in r.headers.get_all('x-goog-hash') if h.startswith('md5=')][0]
        raw = r.read()
    if base64.b64encode(hashlib.md5(raw).digest()).decode() != md5:
        raise SystemExit('PGO profile: md5 mismatch')
    dest.write_bytes(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)


def _toolchain_windows_sources():
    """Windows-only sources missing from the (Linux-oriented) lite tarball.

    Versions and hashes come from ungoogled-chromium-windows' downloads.ini so
    we stay in sync with them:
      * DirectX-Headers and webauthn headers (Microsoft, pinned commits);
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
                            ('webauthn', 'third_party/microsoft_webauthn/src')):
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
        # (LNK4099) when they are missing.
        run(cmd + ['splat', '--use-winsysroot-style', '--preserve-ms-arch-notation', '--disable-symlinks',
                   '--include-debug-symbols',
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


def step_brand(args):
    run([sys.executable, ROOT / 'scripts' / 'branding.py', SRC])
    mark_done('brand')


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
    lines = parse(UG / 'flags.gn') + parse(UGW / 'flags.windows.gn', WINDOWS_HOST_ONLY_FLAGS) + \
        parse(ROOT / 'flags.hivey.gn')
    merged = {}
    for line in lines:  # later files override earlier ones
        merged[line.split('=')[0].strip()] = line
    return '\n'.join(merged.values()) + '\n'


def step_configure(args):
    ensure_winsysroot()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'args.gn').write_text(gn_args())
    env = {**os.environ, 'DEPOT_TOOLS_WIN_TOOLCHAIN': '1'}
    run([TOOLS / 'gn', 'gen', OUT, '--fail-on-unused-args'], cwd=SRC, env=env)
    mark_done('configure')


def args_jobs():
    return int(os.environ.get('HB_JOBS', '8'))


def step_build(args):
    ensure_winsysroot()
    env = {**os.environ, 'DEPOT_TOOLS_WIN_TOOLCHAIN': '1',
           # Go (Dawn's generators) must never fetch toolchains or modules.
           'GOTOOLCHAIN': 'local', 'GOPROXY': 'off', 'GOFLAGS': '-mod=mod',
           'GOPATH': str(BUILD / 'gopath'), 'GOCACHE': str(BUILD / 'gopath' / 'cache')}
    targets = args.targets or ['chrome', 'mini_installer']
    cmd = [TOOLS / 'ninja', '-C', OUT, '-j', str(args_jobs())] + targets
    if os.environ.get('HB_KEEP_GOING'):  # e.g. 0 = keep going past every failure
        cmd[1:1] = ['-k', os.environ['HB_KEEP_GOING']]
    # Run inside a transient systemd scope with a memory cap: if a ThinLTO link
    # outgrows it, the kernel kills the build, never a production service.
    mem_max = os.environ.get('HB_MEM_MAX', '26G')
    if shutil.which('systemd-run') and mem_max != 'none':
        cmd = ['systemd-run', '--scope', '--quiet', '--collect', '-p', f'MemoryMax={mem_max}',
               '-p', 'MemorySwapMax=0', '-p', 'CPUWeight=10', '-p', 'IOWeight=10', '--'] + cmd
    run(cmd, cwd=SRC, env=env)
    mark_done('build')


def step_status(args):
    state = load_state()
    log(f'build dir: {BUILD}  (Chromium {chromium_version()})')
    for s in STEPS:
        print(f"  {'✔' if state.get(s, {}).get('done') else '·'} {s}")


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
            if is_done(s) and s not in ('build', 'patch'):
                continue
            fns[s](args)
    else:
        if args.step in STEPS and is_done(args.step) and not args.force and args.step not in ('build', 'patch'):
            log(f'{args.step}: already done (use --force to re-run)')
            return
        fns[args.step](args)


if __name__ == '__main__':
    main()
