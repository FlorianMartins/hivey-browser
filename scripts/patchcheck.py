#!/usr/bin/env python3
"""Check the patch stack against a Chromium source tarball, without a build.

    patchcheck.py <tarball> <out dir> [--include PATH]... [--refresh]

Extracts only the files the patches touch (plus any --include PATH) from the
Chromium "lite" tarball into <out dir>, then applies, in order, the patches of
ungoogled-chromium, ungoogled-chromium-windows and patches/series. Hivey
patches must apply without fuzz: a fuzzy hunk is reported as an error, since
it may have landed in the wrong place.

It takes a few minutes (decompressing the tarball) and a few hundred MB, so it
runs on a CI runner when a new Chromium version comes out. <out dir> ends up
holding the files exactly as the build tree has them before branding and
domain substitution: copy it to write a new patch (see scripts/mkpatch.py).

--refresh rewrites each Hivey patch from the tree, so that patches which
applied with an offset apply exactly again. Each patch keeps its leading
"# description" line.
"""

import argparse
import lzma
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hb  # noqa: E402

PATH_RE = re.compile(r'^(?:---|\+\+\+) [ab]/(\S+)', re.M)


def patch_stack():
    """[(group, patch path)] in application order."""
    return ([('ungoogled-chromium', p) for p in hb._series(hb.UG / 'patches')] +
            [('ungoogled-chromium-windows', p) for p in hb._series(hb.UGW / 'patches', hb.WINDOWS_HOST_ONLY_PATCHES)] +
            [('hivey', p) for p in hb._series(hb.ROOT / 'patches')])


def touched_files(patch):
    return set(PATH_RE.findall(patch.read_text(encoding='utf-8', errors='replace')))


def extract(tarball, out, wanted):
    """Extract the wanted paths (relative to the source root) from the tarball."""
    found = set()
    with lzma.open(tarball) as xz, tarfile.open(fileobj=xz, mode='r|') as tar:
        for member in tar:
            rel = member.name.split('/', 1)[1] if '/' in member.name else ''
            if rel in wanted and member.isfile():
                member.name = rel
                tar.extract(member, out, filter='data')
                found.add(rel)
    return found


def apply(patch, tree, strict):
    cmd = ['patch', '-p1', '--forward', '--no-backup-if-mismatch', '-d', str(tree), '-i', str(patch)]
    if strict:
        cmd.append('--fuzz=0')
    else:
        cmd.append('--ignore-whitespace')
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, r.stdout + r.stderr


def refresh(patch, tree):
    """Rewrite a Hivey patch from the tree it was just applied to."""
    first = patch.read_text().split('\n', 1)[0]
    header = first + '\n' if first.startswith('#') else ''
    files = sorted(touched_files(patch))
    pristine = tree.parent / (tree.name + '.pre')
    diffs = []
    for rel in files:
        a, b = pristine / rel, tree / rel
        r = subprocess.run(['diff', '-u', '--label', f'a/{rel}', '--label', f'b/{rel}',
                            str(a) if a.exists() else '/dev/null', str(b) if b.exists() else '/dev/null'],
                           capture_output=True, text=True)
        if r.returncode > 1:
            raise SystemExit(r.stderr)
        diffs.append(r.stdout)
    patch.write_text(header + ''.join(diffs))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('tarball', type=Path)
    p.add_argument('out', type=Path)
    p.add_argument('--include', action='append', default=[], help='extra source path to extract')
    p.add_argument('--refresh', action='store_true', help='rewrite Hivey patches that applied with an offset')
    args = p.parse_args()

    stack = patch_stack()
    wanted = set(args.include)
    for _, patch in stack:
        wanted |= touched_files(patch)
    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)
    hb.log(f'extracting {len(wanted)} files from {args.tarball.name}')
    found = extract(args.tarball, args.out, wanted)
    hb.log(f'{len(found)} found in the tarball (the others are created by patches)')

    failures = []
    for group, patch in stack:
        strict = group == 'hivey'
        name = f'{group}: {patch.name}'
        if strict and args.refresh:
            pre = args.out.parent / (args.out.name + '.pre')
            shutil.rmtree(pre, ignore_errors=True)
            for rel in touched_files(patch):
                if (args.out / rel).exists():
                    (pre / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(args.out / rel, pre / rel)
        ok, output = apply(patch, args.out, strict)
        if not ok:
            failures.append(name)
            print(f'FAIL {name}\n{output}', flush=True)
            continue
        drift = [line for line in output.splitlines() if 'offset' in line or 'fuzz' in line]
        if strict and drift and args.refresh:
            refresh(patch, args.out)
            print(f'REFRESHED {name}', flush=True)
        elif strict and drift:
            print(f'OFFSET {name}: ' + '; '.join(drift), flush=True)
    shutil.rmtree(args.out.parent / (args.out.name + '.pre'), ignore_errors=True)
    if failures:
        raise SystemExit(f'{len(failures)} patch(es) do not apply: ' + ', '.join(failures))
    hb.log(f'all {len(stack)} patches apply')


if __name__ == '__main__':
    main()
