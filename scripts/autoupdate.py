#!/usr/bin/env python3
"""Keep Hivey Browser on the latest Chromium and Hivey AI sidebar, unattended.

    autoupdate.py [--dry-run] [--force-release]

Run every 5 minutes by a systemd timer on the build host (scripts/install-autoupdate.sh);
a run that finds nothing new only makes a few GitHub API calls.
Works in its own clone ($HB_AUTO_DIR, default ../hivey-browser-auto) and
build tree ($HB_AUTO_BUILD, default ../hivey-browser-build-auto), never in a
developer's checkout. Each run:

1. Looks for a newer ungoogled-chromium release that ungoogled-chromium-windows
   also supports (same Chromium version). If there is one, prepares branch
   auto/chromium-<version>: submodules bumped, HIVEY_REVISION back to 1,
   patches checked against the new source tarball and refreshed if they only
   drifted (scripts/patchcheck.py). A patch that no longer applies stops the
   run and opens an issue: that needs a human.
   The Hivey AI sidebar (submodule third_party/hivey-ai-sidebar) follows the
   main branch of its repository: when main has a newer commit whose CI
   passed, the same branch (or auto/hivey-ai-<commit> without a new
   Chromium) moves the submodule to it and bumps HIVEY_REVISION. Either way
   CHANGELOG.md gets the entry for the new version.
2. Releases when the resulting version has no GitHub release yet (a new
   Chromium, or a HIVEY_REVISION bump on main): fresh build of Windows and
   Linux, packages, signed draft release (scripts/release.py), checks on Linux
   here (no request at startup, privacy checks) and on a Windows runner
   (.github/workflows/windows-smoke.yml, run by the pull request's checks).
3. Only if every check passes: merges the branch (pull request) and
   publishes the release. Installed browsers then update themselves.
4. Replaces the `dev` pre-release (permanent test links) with the build of
   main, after a release or whenever main changed since the last dev build.

Any failure opens (or comments on) a GitHub issue labelled "autoupdate" with
the end of the log, and the same update is not retried until something new
(Chromium, sidebar or main) comes. --dry-run only reports what would happen.
"""

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = os.environ.get('HB_REPO', 'FlorianMartins/hivey-browser')
AUTO_DIR = Path(os.environ.get('HB_AUTO_DIR', ROOT.parent / 'hivey-browser-auto'))
AUTO_BUILD = Path(os.environ.get('HB_AUTO_BUILD', ROOT.parent / 'hivey-browser-build-auto'))
# Downloads shared with the developer build tree, to avoid fetching the same
# 2 GB tarball and Windows SDK twice.
SHARED_CACHES = [Path(p) for p in os.environ.get(
    'HB_SHARED_CACHES', str(ROOT.parent / 'hivey-browser-build')).split(':') if p]
LOG = AUTO_BUILD / 'autoupdate.log'
# What the last failed run tried (Chromium tag, sidebar commit, main commit):
# with checks every few minutes, the same failure is not retried until one of
# them changes.
FAILED = AUTO_BUILD / 'autoupdate-failed.txt'
UG_REPO = 'ungoogled-software/ungoogled-chromium'
UGW_REPO = 'ungoogled-software/ungoogled-chromium-windows'
AI_REPO = 'FlorianMartins/HiveyAI-Sidebar'
AI_PATH = 'third_party/hivey-ai-sidebar'
MONTHS = ('janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre',
          'novembre', 'décembre')


class Failure(Exception):
    pass


def log(msg):
    line = f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {msg}'
    print(line, flush=True)
    AUTO_BUILD.mkdir(parents=True, exist_ok=True)
    with open(LOG, 'a') as f:
        f.write(line + '\n')


def run(cmd, cwd=AUTO_DIR, env=None, check=True, capture=False):
    log('$ ' + ' '.join(str(c) for c in cmd))
    with open(LOG, 'a') as f:
        r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, text=True,
                           stdout=subprocess.PIPE if capture else f, stderr=subprocess.STDOUT)
    if check and r.returncode != 0:
        raise Failure(f'{cmd[0]} {cmd[1] if len(cmd) > 1 else ""} failed ({r.returncode})')
    return r.stdout if capture else r.returncode


def git(*args, capture=True, check=True):
    return run(['git', *args], capture=capture, check=check)


def gh_json(*args):
    return json.loads(subprocess.run(['gh', *args], check=True, capture_output=True, text=True).stdout)


def version_key(tag):
    """'156.0.8078.47-1.1' -> (156, 0, 8078, 47, 1, 1)."""
    return tuple(int(x) for x in tag.replace('-', '.').split('.'))


def latest_upstream():
    """Newest ungoogled-chromium tag whose Chromium version has an
    ungoogled-chromium-windows tag too: (ug tag, ugw tag)."""
    ug_tags = [t['name'] for t in gh_json('api', f'repos/{UG_REPO}/tags?per_page=30')]
    ugw_tags = [t['name'] for t in gh_json('api', f'repos/{UGW_REPO}/tags?per_page=30')]
    for ug in sorted(ug_tags, key=version_key, reverse=True):
        chromium = ug.split('-')[0]
        matching = sorted((t for t in ugw_tags if t.startswith(chromium + '-')), key=version_key)
        if matching:
            return ug, matching[-1]
    raise Failure('no ungoogled-chromium release with a Windows counterpart')


def pinned_sidebar():
    """The sidebar commit main pins, or None before the submodule exists."""
    if not (AUTO_DIR / AI_PATH / '.git').exists():
        return None
    return git('-C', AI_PATH, 'rev-parse', 'HEAD').strip()


def latest_sidebar(pinned):
    """Newest commit on the sidebar's main branch whose checks all passed,
    if it is ahead of `pinned`; else None."""
    if not pinned:
        return None
    for commit in gh_json('api', f'repos/{AI_REPO}/commits?sha=main&per_page=10'):
        sha = commit['sha']
        if sha == pinned:
            return None
        runs = gh_json('api', f'repos/{AI_REPO}/commits/{sha}/check-runs?per_page=100')['check_runs']
        if runs and all(r['status'] == 'completed' and r['conclusion'] in ('success', 'skipped', 'neutral')
                        for r in runs):
            ahead = gh_json('api', f'repos/{AI_REPO}/compare/{pinned}...{sha}')['status'] == 'ahead'
            return sha if ahead else None
    return None


def sidebar_version():
    """The version the bundled sidebar gets (hb.py _unpack_submodule)."""
    manifest = json.loads((AUTO_DIR / AI_PATH / 'manifest.chrome.json').read_text())
    count = git('-C', AI_PATH, 'rev-list', '--count', 'HEAD').strip()
    return '.'.join(manifest['version'].split('.')[:2]) + f'.{count}'


def add_changelog(version, notes):
    """A user-facing entry (in French, like the file) for the new version."""
    path = AUTO_DIR / 'CHANGELOG.md'
    text = path.read_text()
    today = time.localtime()
    entry = (f'## {version} — {today.tm_mday} {MONTHS[today.tm_mon - 1]} {today.tm_year}\n\n'
             + ''.join(f'- {note}\n' for note in notes) + '\n')
    first = text.index('\n## ') + 1
    path.write_text(text[:first] + entry + text[first:])


def prepare_clone():
    if not (AUTO_DIR / '.git').exists():
        run(['gh', 'repo', 'clone', REPO, AUTO_DIR], cwd=AUTO_DIR.parent)
    git('fetch', '--prune', 'origin')
    git('checkout', '-B', 'main', 'origin/main')
    git('reset', '--hard', 'origin/main')
    git('clean', '-fdx', '-e', 'HIVEY_LOCAL')
    git('submodule', 'update', '--init', '--force')


def hb_env(target='win'):
    env = {**os.environ, 'HB_BUILD_DIR': str(AUTO_BUILD), 'HB_TARGET': target, 'XWIN_ACCEPT_LICENSE': '1'}
    return env


def hb(step, target='win', *extra):
    run([sys.executable, AUTO_DIR / 'scripts/hb.py', step, *extra], env=hb_env(target))


def link_shared_caches():
    for name in ('download_cache', 'xwin-cache'):
        dest = AUTO_BUILD / name
        for shared in SHARED_CACHES:
            src = shared / name
            if src.is_dir() and not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.symlink_to(src)


def fresh_tree():
    """Remove the source tree and per-version state; keep downloads."""
    for name in ('src', '.hb-state.json', 'dist', 'tools', 'bundled-extensions', 'domsubcache.tar.gz', 'pristine'):
        path = AUTO_BUILD / name
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            winsysroot = AUTO_BUILD / 'winsysroot'
            if os.path.ismount(winsysroot):
                run(['fusermount', '-u', winsysroot], check=False)
            shutil.rmtree(path)


def bump(ug, ugw, ai_sha):
    """Branch with the new Chromium (ug, ugw) and/or sidebar commit (ai_sha)."""
    chromium = ug.split('-')[0] if ug else None
    branch = f'auto/chromium-{chromium}' if ug else f'auto/hivey-ai-{ai_sha[:7]}'
    git('checkout', '-B', branch)
    titles, notes = [], []
    if ug:
        for path, tag in (('third_party/ungoogled-chromium', ug), ('third_party/ungoogled-chromium-windows', ugw)):
            run(['git', '-C', path, 'fetch', '--tags', 'origin'])
            run(['git', '-C', path, 'checkout', '-q', tag])
        (AUTO_DIR / 'HIVEY_REVISION').write_text('1\n')
        hb('fetch')
        tarball = next((AUTO_BUILD / 'download_cache').glob(f'chromium-{chromium}-lite.tar.xz'))
        check = [sys.executable, AUTO_DIR / 'scripts/patchcheck.py', tarball, AUTO_BUILD / 'pristine', '--refresh']
        if run(check, env=hb_env(), check=False) != 0:
            raise Failure(f'patches do not apply to Chromium {ug}: they need a manual update')
        titles.append(f'Chromium {chromium} (ungoogled-chromium {ug}, windows {ugw})')
        notes.append(f'Basé sur **Chromium {chromium}** : les derniers correctifs de sécurité.')
    else:
        revision = int((AUTO_DIR / 'HIVEY_REVISION').read_text().strip()) + 1
        (AUTO_DIR / 'HIVEY_REVISION').write_text(f'{revision}\n')
    if ai_sha:
        run(['git', '-C', AI_PATH, 'fetch', 'origin'])
        run(['git', '-C', AI_PATH, 'checkout', '-q', ai_sha])
        version = sidebar_version()
        titles.append(f'Hivey AI sidebar {version} ({ai_sha[:7]})')
        notes.append(f'**Hivey AI** passe en version {version} : voir ses nouveautés dans '
                     f'[son journal](https://github.com/{AI_REPO}/blob/{ai_sha[:7]}/CHANGELOG.md).')
    add_changelog(computed_version(), notes)
    git('add', '-A')
    git('commit', '-q', '-m', ', '.join(titles) + '\n\n'
        'Automatic update (scripts/autoupdate.py): submodules bumped, patches checked\n'
        'against the source tarball and refreshed where they had drifted.', capture=False)
    return branch


def dev_build_commit():
    """Short commit of the current dev pre-release ('Dev build <version> (<sha>)')."""
    r = subprocess.run(['gh', 'release', 'view', 'dev', '--repo', REPO, '--json', 'name'],
                       capture_output=True, text=True)
    m = re.search(r'\(([0-9a-f]{7})\)', r.stdout) if r.returncode == 0 else None
    return m.group(1) if m else None


def release_exists(tag):
    return subprocess.run(['gh', 'release', 'view', tag, '--repo', REPO], capture_output=True).returncode == 0


def computed_version():
    """The version a build of the clone would have (hb.hivey_version)."""
    out = run([sys.executable, '-c', "import hb; print('.'.join(map(str, hb.hivey_version())))"],
              cwd=AUTO_DIR / 'scripts', env=hb_env(), capture=True)
    return out.strip().splitlines()[-1]


def build_all():
    fresh_tree()
    link_shared_caches()
    for step in ('fetch', 'unpack', 'prune', 'toolchain', 'patch', 'brand', 'bundle', 'domsub'):
        hb(step)
    for target in ('linux', 'win'):
        for step in ('configure', 'build', 'package'):
            hb(step, target)


def linux_smoke(version):
    dist = AUTO_BUILD / 'dist'
    archive = dist / f'hivey-browser-{version}-linux-x64.tar.xz'
    test_dir = AUTO_BUILD / 'linux-smoke'
    shutil.rmtree(test_dir, ignore_errors=True)
    test_dir.mkdir()
    with tarfile.open(archive) as t:
        t.extractall(test_dir, filter='data')
    browser = next(test_dir.glob('*/chrome'))
    run(['xvfb-run', '-a', sys.executable, AUTO_DIR / 'tests/startup_requests.py', browser,
         '--keep', test_dir / 'out'])
    profile = test_dir / 'cdp-profile'
    proc = subprocess.Popen(['xvfb-run', '-a', browser, f'--user-data-dir={profile}', '--remote-debugging-port=9333',
                             '--no-first-run', '--password-store=basic', 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(20)
        run([sys.executable, AUTO_DIR / 'tests/cdp_checks.py', 'http://127.0.0.1:9333', '--shots',
             test_dir / 'out/shots'])
    finally:
        proc.terminate()
        proc.wait(timeout=30)


def windows_smoke(tag, ref):
    run(['gh', 'workflow', 'run', 'windows-smoke.yml', '--repo', REPO, '--ref', ref, '-f', f'tag={tag}'])
    time.sleep(15)
    runs = gh_json('run', 'list', '--repo', REPO, '--workflow', 'windows-smoke.yml', '--limit', '1',
                   '--json', 'databaseId')
    run_id = str(runs[0]['databaseId'])
    run(['gh', 'run', 'watch', run_id, '--repo', REPO, '--exit-status', '--interval', '60'])


def merge(branch):
    git('push', '-u', 'origin', branch, '--force-with-lease', capture=False)
    existing = gh_json('pr', 'list', '--repo', REPO, '--head', branch, '--json', 'number')
    if not existing:
        run(['gh', 'pr', 'create', '--repo', REPO, '--head', branch, '--base', 'main',
             '--title', git('log', '-1', '--format=%s').strip(),
             '--body', 'Automatic update (scripts/autoupdate.py): new Chromium and/or Hivey AI sidebar. '
                       'Built for Windows and Linux; startup and privacy checks passed on both before '
                       'this pull request is merged.'])
    run(['gh', 'pr', 'checks', branch, '--repo', REPO, '--watch', '--fail-fast'])
    run(['gh', 'pr', 'merge', branch, '--repo', REPO, '--squash', '--delete-branch'])


def report_failure(message):
    tail = ''.join(LOG.read_text().splitlines(True)[-60:]) if LOG.exists() else ''
    body = f'{message}\n\nEnd of the log (`{LOG}`):\n\n```\n{tail}\n```'
    issues = gh_json('issue', 'list', '--repo', REPO, '--label', 'autoupdate', '--state', 'open',
                     '--json', 'number')
    if issues:
        subprocess.run(['gh', 'issue', 'comment', str(issues[0]['number']), '--repo', REPO, '--body', body])
    else:
        subprocess.run(['gh', 'label', 'create', 'autoupdate', '--repo', REPO, '--force',
                        '--description', 'Automatic Chromium and Hivey AI updates'], capture_output=True)
        subprocess.run(['gh', 'issue', 'create', '--repo', REPO, '--label', 'autoupdate',
                        '--title', f'Automatic update failed: {message}', '--body', body])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force-release', action='store_true', help='rebuild and release even if the tag exists')
    args = ap.parse_args()
    AUTO_BUILD.mkdir(parents=True, exist_ok=True)
    lock = open(AUTO_BUILD / 'autoupdate.lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0
    attempt = None
    try:
        prepare_clone()
        ug, ugw = latest_upstream()
        current = (AUTO_DIR / 'third_party/ungoogled-chromium/chromium_version.txt').read_text().strip()
        newer = version_key(ug.split('-')[0]) > version_key(current)
        log(f'pinned Chromium {current}; latest upstream {ug} / {ugw}')
        ai_pinned = pinned_sidebar()
        ai_sha = latest_sidebar(ai_pinned)
        log(f'pinned Hivey AI sidebar {ai_pinned and ai_pinned[:7]}; '
            + (f'newer passing commit {ai_sha[:7]}' if ai_sha else 'up to date'))
        if args.dry_run:
            log('dry run: ' + (f'would update to {ug}' if newer else 'no new Chromium')
                + (f', sidebar to {ai_sha[:7]}' if ai_sha else ''))
            return 0
        main_head = git('rev-parse', 'HEAD').strip()
        attempt = f'{ug if newer else "-"} {ai_sha or "-"} {main_head}'
        if FAILED.exists() and FAILED.read_text().strip() == attempt:
            log('this update failed before (see the autoupdate issue): waiting for something new')
            return 0
        branch = bump(ug if newer else None, ugw if newer else None, ai_sha) if newer or ai_sha else None
        version = computed_version()
        tag = f'v{version}'
        release = args.force_release or not release_exists(tag)
        dev = branch is None and dev_build_commit() != main_head[:7]
        if not release and not dev:
            log(f'{tag} is released and the dev build is main ({main_head[:7]}): nothing to do')
            return 0
        build_all()
        if release:
            log(f'releasing {tag}')
            draft_target = branch or 'main'
            if branch:
                git('push', '-u', 'origin', branch, '--force-with-lease', capture=False)
            run([sys.executable, AUTO_DIR / 'scripts/release.py', 'draft', '--target', draft_target],
                env=hb_env())
            linux_smoke(version)
            if branch:
                # The pull request's checks include the Windows smoke test of
                # this draft release; merge() waits for all of them.
                merge(branch)
            else:
                windows_smoke(tag, 'main')
            git('fetch', 'origin', 'main')
            main_head = git('rev-parse', 'origin/main').strip()
            run([sys.executable, AUTO_DIR / 'scripts/release.py', 'publish', '--tag', tag,
                 '--target', main_head], env=hb_env())
            log(f'{tag} published')
        else:
            log(f'dev build of main {main_head[:7]} ({tag} is already released)')
            linux_smoke(version)
        # The dev channel (permanent test links) follows main.
        run([sys.executable, AUTO_DIR / 'scripts/release.py', 'dev', '--commit', main_head], env=hb_env())
        return 0
    except Failure as e:
        log(f'FAILED: {e}')
        report_failure(str(e))
        if attempt:
            FAILED.write_text(attempt + '\n')
        return 1
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)


if __name__ == '__main__':
    sys.exit(main())
