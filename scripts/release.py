#!/usr/bin/env python3
"""Publish a Hivey Browser release on GitHub.

    release.py draft      write + sign hivey-update.json, create a draft release
    release.py publish    publish the draft (installed browsers then update)
    release.py dev        replace the `dev` pre-release (permanent test links)

Both read the version from the build tree ($HB_BUILD_DIR/src/chrome/VERSION)
and the artifacts from $HB_BUILD_DIR/dist (hb.py package). The release tag is
v<version>, e.g. v156.0.8078.4701.

hivey-update.json tells installed browsers what the latest version is and
where its installers are, with their size and sha256. On Windows the
browsers download "windows-x64" and run it silently with
--do-not-launch-chrome: that is the bare mini_installer (-update.exe), never
the setup wizard (-installer.exe, "windows-x64-setup"), so every installed
version, 4710 and older included, keeps updating the same way. It is signed
with the Ed25519 update key (hb.py ensure_update_key); browsers only accept a
manifest signed with the key whose public half they were built with. A
draft release is invisible to them: the updater reads releases/latest,
which only points to published releases.

The `dev` pre-release is a testing channel with permanent links, replaced
with every build of main (scripts/autoupdate.py), like the other Hivey
projects:
  https://github.com/FlorianMartins/hivey-browser/releases/download/dev/hivey-browser-dev-windows-x64-installer.exe
  https://github.com/FlorianMartins/hivey-browser/releases/download/dev/hivey-browser-dev-windows-x64-update.exe
  https://github.com/FlorianMartins/hivey-browser/releases/download/dev/hivey-browser-dev-linux-x64.tar.xz
Installed browsers never take it (pre-releases are not "latest").
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hb  # noqa: E402

REPO = os.environ.get('HB_REPO', 'FlorianMartins/hivey-browser')
# Artifacts of hb.py package. Windows: the setup wizard and the bare
# mini_installer it embeds (what the updater runs); a dist packaged before the
# wizard has only -installer.exe, then the mini_installer itself.
PLATFORMS = {'windows-x64': '-windows-x64-installer.exe', 'windows-x64-update': '-windows-x64-update.exe',
             'linux-x64': '-linux-x64.tar.xz'}


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


# Release assets have the same names in every release, so these links always
# serve the latest published version:
#   https://github.com/<repo>/releases/latest/download/<name>
STABLE_NAMES = {'windows-x64': 'hivey-browser-windows-x64-installer.exe',
                'windows-x64-update': 'hivey-browser-windows-x64-update.exe',
                'linux-x64': 'hivey-browser-linux-x64.tar.xz'}


def stage(found, names, directory):
    """Hard links to the artifacts under their published names, with their
    SHA256SUMS."""
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)
    staged = {}
    for platform, path in found.items():
        dest = directory / names[platform]
        os.link(path, dest)
        staged[platform] = dest
    sums = directory / 'SHA256SUMS'
    sums.write_text(''.join(f'{hb.sha256_file(f)}  {f.name}\n' for f in staged.values()))
    return staged, sums


def gh(*args, **kw):
    return subprocess.run(['gh', *args, '--repo', REPO], check=True, text=True, **kw)


def write_manifest(ver, tag, found):
    manifest = {
        'version': ver,
        'chromium': hb.chromium_version(),
        'published': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'page': f'https://github.com/{REPO}/releases/tag/{tag}',
    }
    entries = {platform: {
        'url': f'https://github.com/{REPO}/releases/download/{tag}/{path.name}',
        'sha256': hb.sha256_file(path),
        'size': path.stat().st_size,
    } for platform, path in found.items()}
    # "windows-x64" is what browsers run silently: the mini_installer.
    if 'windows-x64-update' in entries:
        manifest['windows-x64'] = entries.pop('windows-x64-update')
        if 'windows-x64' in entries:
            manifest['windows-x64-setup'] = entries.pop('windows-x64')
    manifest.update(entries)
    path = hb.DIST / 'hivey-update.json'
    path.write_text(json.dumps(manifest, indent=2) + '\n')
    sig = hb.DIST / 'hivey-update.json.sig'
    hb.ensure_update_key()
    subprocess.run(['openssl', 'pkeyutl', '-sign', '-inkey', hb.UPDATE_KEY, '-rawin', '-in', path, '-out', sig],
                   check=True)
    if sig.stat().st_size != 64:
        raise SystemExit('unexpected Ed25519 signature size')
    return path, sig


def changelog_section(ver):
    """The CHANGELOG.md section of a version (French, user-facing)."""
    text = (hb.ROOT / 'CHANGELOG.md').read_text()
    start = text.find(f'## {ver}')
    if start < 0:
        return ''
    end = text.find('\n## ', start + 1)
    return text[start:end if end > 0 else len(text)].strip()


def release_notes(ver):
    ug = (hb.UG / 'revision.txt').read_text().strip() if (hb.UG / 'revision.txt').exists() else '?'
    changes = changelog_section(ver)
    changes = f'{changes}\n\n---\n\n' if changes else ''
    return changes + f"""Hivey Browser {ver}, based on Chromium {hb.chromium_version()} (ungoogled-chromium revision {ug}).

Installed browsers update by themselves (Hivey Studio > About). To install:

- **Windows x64**: run `{STABLE_NAMES['windows-x64']}`, the setup wizard (install folder, bundled add-ons, privacy mode, shortcuts; per-user install, no admin rights). `{STABLE_NAMES['windows-x64-update']}` is the silent installer that installed browsers use to update.
- **Linux x64**: extract `{STABLE_NAMES['linux-x64']}` and run `hivey-browser`.

Permanent links to the latest version:
https://github.com/{REPO}/releases/latest/download/{STABLE_NAMES['windows-x64']} and
https://github.com/{REPO}/releases/latest/download/{STABLE_NAMES['linux-x64']}

`SHA256SUMS` lists the checksums. `hivey-update.json` is the signed (Ed25519) update manifest.
"""


def cmd_draft(args):
    ver = version()
    tag = f'v{ver}'
    found, sums = stage(artifacts(ver), STABLE_NAMES, hb.DIST / 'release')
    manifest, sig = write_manifest(ver, tag, found)
    files = [str(p) for p in found.values()] + [str(manifest), str(sig), str(sums)]
    exists = subprocess.run(['gh', 'release', 'view', tag, '--repo', REPO], capture_output=True).returncode == 0
    if exists:
        # --target: the draft's branch may be gone (deleted by the merge).
        gh('release', 'edit', tag, '--target', args.target, '--notes', release_notes(ver))
        gh('release', 'upload', tag, '--clobber', *files)
        # Assets of an earlier draft under other names (versioned names).
        keep = {Path(f).name for f in files}
        current = json.loads(gh('release', 'view', tag, '--json', 'assets', capture_output=True).stdout)
        for asset in current['assets']:
            if asset['name'] not in keep:
                gh('release', 'delete-asset', tag, asset['name'], '--yes')
    else:
        gh('release', 'create', tag, '--draft', '--title', f'Hivey Browser {ver}', '--notes', release_notes(ver),
           '--target', args.target, *files)
    hb.log(f'draft release {tag}: {", ".join(Path(f).name for f in files)}')
    print(tag)


DEV_NAMES = {'windows-x64': 'hivey-browser-dev-windows-x64-installer.exe',
             'windows-x64-update': 'hivey-browser-dev-windows-x64-update.exe',
             'linux-x64': 'hivey-browser-dev-linux-x64.tar.xz'}


def cmd_dev(args):
    ver = version()
    sha = args.commit
    staged, sums = stage(artifacts(ver), DEV_NAMES, hb.DIST / 'dev')
    files = [*staged.values(), sums]
    notes = (f'Build de dev {ver} (commit {sha[:12]}). Canal de test, remplacé à chaque build de main ; '
             'ce n\'est pas une version publiée : les navigateurs installés ne le prennent jamais.\n\n'
             + changelog_section(ver))
    if subprocess.run(['gh', 'api', f'repos/{REPO}/git/refs/tags/dev'], capture_output=True).returncode == 0:
        subprocess.run(['gh', 'api', '-X', 'PATCH', f'repos/{REPO}/git/refs/tags/dev', '-f', f'sha={sha}',
                        '-F', 'force=true'], check=True, capture_output=True)
    else:
        subprocess.run(['gh', 'api', '-X', 'POST', f'repos/{REPO}/git/refs', '-f', 'ref=refs/tags/dev',
                        '-f', f'sha={sha}'], check=True, capture_output=True)
    title = f'Dev build {ver} ({sha[:7]})'
    if subprocess.run(['gh', 'release', 'view', 'dev', '--repo', REPO], capture_output=True).returncode == 0:
        gh('release', 'edit', 'dev', '--prerelease', '--latest=false', '--title', title, '--notes', notes)
    else:
        gh('release', 'create', 'dev', '--prerelease', '--latest=false', '--verify-tag', '--title', title,
           '--notes', notes)
    gh('release', 'upload', 'dev', '--clobber', *[str(f) for f in files])
    hb.log(f'dev pre-release: {title}')
    for name in DEV_NAMES.values():
        print(f'https://github.com/{REPO}/releases/download/dev/{name}')


def cmd_publish(args):
    tag = args.tag or f'v{version()}'
    target = ['--target', args.target] if args.target else []
    gh('release', 'edit', tag, '--draft=false', '--latest', *target)
    hb.log(f'published {tag}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('draft')
    d.add_argument('--target', default='main', help='branch or commit the tag points to')
    p = sub.add_parser('publish')
    p.add_argument('--tag')
    p.add_argument('--target', help='commit the tag points to (after a squash merge, main)')
    v = sub.add_parser('dev')
    v.add_argument('--commit', required=True, help='commit the build comes from')
    args = ap.parse_args()
    {'draft': cmd_draft, 'publish': cmd_publish, 'dev': cmd_dev}[args.cmd](args)


if __name__ == '__main__':
    main()
