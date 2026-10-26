#!/usr/bin/env python3
"""Publish a Hivey Browser release on GitHub.

    release.py draft      write + sign hivey-update.json, create a draft release
    release.py publish    publish the draft (installed browsers then update)

Both read the version from the build tree ($HB_BUILD_DIR/src/chrome/VERSION)
and the artifacts from $HB_BUILD_DIR/dist (hb.py package). The release tag is
v<version>, e.g. v156.0.8078.4701.

hivey-update.json tells installed browsers what the latest version is and
where its installers are, with their size and sha256. It is signed with the
Ed25519 update key (hb.py ensure_update_key); browsers only accept a
manifest signed with the key whose public half they were built with. A
draft release is invisible to them: the updater reads releases/latest,
which only points to published releases.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hb  # noqa: E402

REPO = os.environ.get('HB_REPO', 'FlorianMartins/hivey-browser')
PLATFORMS = {'windows-x64': '-windows-x64-installer.exe', 'linux-x64': '-linux-x64.tar.xz'}


def version():
    v = dict(line.split('=') for line in (hb.SRC / 'chrome/VERSION').read_text().split())
    return f"{v['MAJOR']}.{v['MINOR']}.{v['BUILD']}.{v['PATCH']}"


def artifacts(ver):
    found = {}
    for platform, suffix in PLATFORMS.items():
        path = hb.DIST / f'hivey-browser-{ver}{suffix}'
        if path.exists():
            found[platform] = path
    if not found:
        raise SystemExit(f'no artifact for {ver} in {hb.DIST}: run hb.py package')
    return found


def gh(*args, **kw):
    return subprocess.run(['gh', *args, '--repo', REPO], check=True, text=True, **kw)


def write_manifest(ver, tag, found):
    manifest = {
        'version': ver,
        'chromium': hb.chromium_version(),
        'published': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'page': f'https://github.com/{REPO}/releases/tag/{tag}',
    }
    for platform, path in found.items():
        manifest[platform] = {
            'url': f'https://github.com/{REPO}/releases/download/{tag}/{path.name}',
            'sha256': hb.sha256_file(path),
            'size': path.stat().st_size,
        }
    path = hb.DIST / 'hivey-update.json'
    path.write_text(json.dumps(manifest, indent=2) + '\n')
    sig = hb.DIST / 'hivey-update.json.sig'
    hb.ensure_update_key()
    subprocess.run(['openssl', 'pkeyutl', '-sign', '-inkey', hb.UPDATE_KEY, '-rawin', '-in', path, '-out', sig],
                   check=True)
    if sig.stat().st_size != 64:
        raise SystemExit('unexpected Ed25519 signature size')
    return path, sig


def release_notes(ver):
    ug = (hb.UG / 'revision.txt').read_text().strip() if (hb.UG / 'revision.txt').exists() else '?'
    return f"""Hivey Browser {ver}, based on Chromium {hb.chromium_version()} (ungoogled-chromium revision {ug}).

Installed browsers update by themselves (Hivey Studio > About). To install:

- **Windows x64**: run `hivey-browser-{ver}-windows-x64-installer.exe` (per-user install, no admin rights).
- **Linux x64**: extract `hivey-browser-{ver}-linux-x64.tar.xz` and run `hivey-browser`.

`SHA256SUMS` lists the checksums. `hivey-update.json` is the signed (Ed25519) update manifest.
"""


def cmd_draft(args):
    ver = version()
    tag = f'v{ver}'
    found = artifacts(ver)
    manifest, sig = write_manifest(ver, tag, found)
    files = [str(p) for p in found.values()] + [str(manifest), str(sig), str(hb.DIST / 'SHA256SUMS')]
    exists = subprocess.run(['gh', 'release', 'view', tag, '--repo', REPO], capture_output=True).returncode == 0
    if exists:
        gh('release', 'upload', tag, '--clobber', *files)
    else:
        gh('release', 'create', tag, '--draft', '--title', f'Hivey Browser {ver}', '--notes', release_notes(ver),
           '--target', args.target, *files)
    hb.log(f'draft release {tag}: {", ".join(Path(f).name for f in files)}')
    print(tag)


def cmd_publish(args):
    tag = args.tag or f'v{version()}'
    gh('release', 'edit', tag, '--draft=false', '--latest')
    hb.log(f'published {tag}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('draft')
    d.add_argument('--target', default='main', help='branch or commit the tag points to')
    p = sub.add_parser('publish')
    p.add_argument('--tag')
    args = ap.parse_args()
    {'draft': cmd_draft, 'publish': cmd_publish}[args.cmd](args)


if __name__ == '__main__':
    main()
