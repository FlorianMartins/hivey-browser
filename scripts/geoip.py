#!/usr/bin/env python3
"""IP-to-country database shipped with Hivey Browser (hivey_geoip.bin).

The location bar shows the country of the server a page was loaded from. The
lookup is local: the browser never asks anyone. This script turns db-ip.com's
"IP to Country Lite" database (CC BY 4.0, https://db-ip.com, updated monthly)
into the compact binary file the browser reads
(chrome/browser/hivey/hivey_geoip.cc).

    geoip.py <dest dir> [--cache <dir>]

hb.py calls build() in its `bundle` step.

File format (all integers big-endian):

    header, 24 bytes:
      magic      8 bytes  b'HIVEYGEO'
      version    u16      1
      reserved   u16      0
      v4_count   u32      number of IPv4 entries
      v6_count   u32      number of IPv6 entries
      month      u32      database month, YYYYMM (e.g. 202610)
    v4_count IPv4 entries, 6 bytes each:  start u32, country 2 ASCII bytes
    v6_count IPv6 entries, 18 bytes each: start 16 bytes, country 2 bytes

Each table is a partition of its whole address space, sorted by start: the
first entry starts at 0 and an entry covers every address up to the next
entry's start (the last one, up to the end of the space). Unassigned gaps are
explicit entries with the code "--" (db-ip's "ZZ" becomes "--" too), and
adjacent ranges with the same country are merged. A lookup is a binary search
for the last entry whose start is <= the address.
"""

import argparse
import csv
import datetime
import gzip
import io
import ipaddress
import shutil
import struct
import sys
import urllib.error
import urllib.request
from pathlib import Path

URL = 'https://download.db-ip.com/free/dbip-country-lite-{month}.csv.gz'
MAGIC = b'HIVEYGEO'
VERSION = 1
UNKNOWN = '--'
FILE_NAME = 'hivey_geoip.bin'
# A real monthly file has ~700k rows and ~250 countries: anything far below
# means a truncated download or a changed format.
MIN_ROWS = 100_000
MIN_COUNTRIES = 200
# Addresses whose country has been stable for decades (Google DNS, RIPE NCC,
# SURFnet), as a sanity check of the parsing.
SANITY = {'8.8.8.8': 'US', '193.0.6.139': 'NL', '2001:610::': 'NL'}


def log(msg):
    print(f'\033[1;33m[hb]\033[0m {msg}', flush=True)


def _months(today=None):
    """This month, then the previous one (db-ip publishes early in the month)."""
    today = today or datetime.date.today()
    first = today.replace(day=1)
    previous = (first - datetime.timedelta(days=1)).replace(day=1)
    return [first.strftime('%Y-%m'), previous.strftime('%Y-%m')]


def _download(cache):
    """The newest available month's .csv.gz, cached in `cache`."""
    cache.mkdir(parents=True, exist_ok=True)
    for month in _months():
        dest = cache / f'dbip-country-lite-{month}.csv.gz'
        if dest.exists():
            return month, dest
        url = URL.format(month=month)
        log(f'download {url}')
        tmp = dest.with_suffix('.gz.part')
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'hivey-browser-build'})
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, 'wb') as f:
                shutil.copyfileobj(r, f, 1 << 20)
        except urllib.error.HTTPError as e:
            tmp.unlink(missing_ok=True)
            if e.code == 404:  # not published yet: try the previous month
                log(f'geoip: {month} not available yet')
                continue
            raise
        tmp.rename(dest)
        return month, dest
    raise SystemExit('geoip: no db-ip country database found for this or last month')


def _parse(path):
    """IPv4 and IPv6 rows as (start, end, code) with integer addresses."""
    v4, v6 = [], []
    with gzip.open(path, 'rt', encoding='ascii', newline='') as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            start, end = ipaddress.ip_address(row[0]), ipaddress.ip_address(row[1])
            if start.version != end.version or int(end) < int(start):
                raise SystemExit(f'geoip: bad row {row}')
            code = row[2].strip().upper()
            if len(code) != 2 or not code.isalpha() or code == 'ZZ':
                code = UNKNOWN
            (v4 if start.version == 4 else v6).append((int(start), int(end), code))
    return v4, v6


def _partition(rows, bits):
    """Sorted, gap-free, merged (start, code) entries covering [0, 2**bits)."""
    rows.sort()
    out = []

    def add(start, code):
        if out and out[-1][1] == code:
            return  # same country as the previous range: merge
        out.append((start, code))

    nxt = 0  # first address not covered yet
    for start, end, code in rows:
        if end < nxt:
            continue  # fully overlapped by an earlier row
        start = max(start, nxt)
        if start > nxt:
            add(nxt, UNKNOWN)
        add(start, code)
        nxt = end + 1
    if nxt < (1 << bits) or not out:
        add(nxt if out else 0, UNKNOWN)
    return out


def _lookup(table, addr):
    lo, hi = 0, len(table)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if table[mid][0] <= addr:
            lo = mid
        else:
            hi = mid
    return table[lo][1]


def _check(rows, v4, v6):
    countries = {c for t in (v4, v6) for _, c in t} - {UNKNOWN}
    if rows < MIN_ROWS or len(countries) < MIN_COUNTRIES or not v4 or not v6:
        raise SystemExit(f'geoip: database looks truncated ({rows} rows, {len(countries)} countries)')
    for ip, expected in SANITY.items():
        a = ipaddress.ip_address(ip)
        got = _lookup(v4 if a.version == 4 else v6, int(a))
        if got != expected:
            raise SystemExit(f'geoip: sanity check failed, {ip} is {got}, expected {expected}')


def _serialize(month, v4, v6):
    out = io.BytesIO()
    out.write(MAGIC)
    out.write(struct.pack('>HHIII', VERSION, 0, len(v4), len(v6), int(month.replace('-', ''))))
    for start, code in v4:
        out.write(struct.pack('>I', start) + code.encode('ascii'))
    for start, code in v6:
        out.write(start.to_bytes(16, 'big') + code.encode('ascii'))
    return out.getvalue()


def build(dest_dir, cache_dir=None):
    """Writes <dest_dir>/hivey_geoip.bin; returns its path and the db month."""
    dest_dir = Path(dest_dir)
    month, csv_gz = _download(Path(cache_dir) if cache_dir else dest_dir / 'geoip-cache')
    v4_rows, v6_rows = _parse(csv_gz)
    rows = len(v4_rows) + len(v6_rows)
    v4, v6 = _partition(v4_rows, 32), _partition(v6_rows, 128)
    _check(rows, v4, v6)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / FILE_NAME
    tmp = out.with_suffix('.part')
    tmp.write_bytes(_serialize(month, v4, v6))
    tmp.replace(out)
    log(f'geoip: db-ip country lite {month}, {rows} rows -> {len(v4)} IPv4 + {len(v6)} IPv6 ranges, '
        f'{out.stat().st_size / (1 << 20):.1f} MiB')
    return out, month


def read_lookup(path, ip):
    """Looks `ip` up in a written file (for tests): its 2-letter code or '--'."""
    data = Path(path).read_bytes()
    if data[:8] != MAGIC:
        raise ValueError('not a Hivey geoip file')
    version, _, n4, n6, _ = struct.unpack('>HHIII', data[8:24])
    if version != VERSION:
        raise ValueError(f'unsupported version {version}')
    a = ipaddress.ip_address(ip)
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    if a.version == 4:
        base, size, n, width = 24, 6, n4, 4
    else:
        base, size, n, width = 24 + 6 * n4, 18, n6, 16
    addr = int(a)
    lo, hi = 0, n
    while hi - lo > 1:
        mid = (lo + hi) // 2
        off = base + mid * size
        if int.from_bytes(data[off:off + width], 'big') <= addr:
            lo = mid
        else:
            hi = mid
    off = base + lo * size + width
    return data[off:off + 2].decode('ascii')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('dest', help='directory to write hivey_geoip.bin into')
    p.add_argument('--cache', help='where to keep the downloaded .csv.gz (default: <dest>/geoip-cache)')
    p.add_argument('--lookup', nargs='*', default=[], help='addresses to look up after building')
    args = p.parse_args()
    out, _ = build(args.dest, args.cache)
    for ip in args.lookup:
        print(f'{ip}\t{read_lookup(out, ip)}')


if __name__ == '__main__':
    sys.exit(main())
