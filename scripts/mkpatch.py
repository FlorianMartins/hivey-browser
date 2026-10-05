#!/usr/bin/env python3
"""Turn an edited copy of some Chromium files into a Hivey patch.

    mkpatch.py <workdir> <patch file> "<one-line description>"

<workdir> holds a/ (files as in the patched source tree) and b/ (the same
files, edited). Editing copies instead of the build tree means a running
build never compiles a half-edited file. The patch is written with a leading
"# description" line, like ungoogled-chromium's patches.
"""
import subprocess
import sys
from pathlib import Path

work, out, desc = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
diffs = []
for b in sorted(p for p in (work / 'b').rglob('*') if p.is_file()):
    rel = b.relative_to(work / 'b').as_posix()
    a = work / 'a' / rel
    r = subprocess.run(['diff', '-u', '--label', f'a/{rel}', '--label', f'b/{rel}',
                        str(a) if a.exists() else '/dev/null', str(b)], capture_output=True, text=True)
    if r.returncode == 1:
        diffs.append(r.stdout)
    elif r.returncode > 1:
        raise SystemExit(r.stderr)
if not diffs:
    raise SystemExit('no changes')
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(f'# {desc}\n' + ''.join(diffs))
print(f'{out}: {len(diffs)} files')
