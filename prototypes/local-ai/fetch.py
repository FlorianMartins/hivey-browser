#!/usr/bin/env python3
"""Download the pinned engine and models into a cache, verifying every sha256.

    fetch.py <cache dir> [model ...]     (no model: all of them)

Nothing is unpacked or kept unless its digest matches manifest.json.
"""
import hashlib
import json
import sys
import tarfile
import urllib.request
from pathlib import Path

MANIFEST = json.loads((Path(__file__).parent / 'manifest.json').read_text())


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, dest, digest):
    if dest.exists() and sha256(dest) == digest:
        print('ok', dest.name)
        return
    part = dest.with_suffix(dest.suffix + '.part')
    print('download', dest.name, flush=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'hivey-browser-prototype'})
    with urllib.request.urlopen(req, timeout=60) as r, open(part, 'wb') as out:
        while chunk := r.read(1 << 20):
            out.write(chunk)
    got = sha256(part)
    if got != digest:
        part.unlink()
        sys.exit(f'{dest.name}: sha256 {got}, expected {digest}')
    part.rename(dest)


def main():
    cache = Path(sys.argv[1])
    models = sys.argv[2:] or list(MANIFEST['models'])
    (cache / 'models').mkdir(parents=True, exist_ok=True)

    engine = MANIFEST['engine']
    archive = cache / f"llama-{engine['version']}-linux.tar.gz"
    fetch(engine['linux']['url'], archive, engine['linux']['sha256'])
    dest = cache / f"llama-{engine['version']}"
    if not dest.exists():
        with tarfile.open(archive) as tar:
            tar.extractall(dest, filter='data')

    for name in models:
        m = MANIFEST['models'][name]
        fetch(f"https://huggingface.co/{m['repo']}/resolve/{m['revision']}/{m['file']}",
              cache / 'models' / m['file'], m['sha256'])


if __name__ == '__main__':
    main()
