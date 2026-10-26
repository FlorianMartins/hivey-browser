#!/usr/bin/env python3
"""Prove that Hivey Browser makes no network request at startup.

    startup_requests.py <browser executable> [--seconds 60] [--keep DIR]

Starts the browser on a fresh profile (so the first-run tab opens too) with
a NetLog capture, lets it idle, closes it, and lists every request and DNS
lookup it made. Allowed: browser-internal URLs (chrome://, extensions,
data:), the encrypted DNS resolver's own probe (dns.quad9.net), and on
Windows the proxy auto-discovery lookup (wpad, local network only, when the
system's "Automatically detect settings" is on). None carries user data.
Anything else fails the check.

Linux CI runs it under xvfb-run; Windows CI runs it on the installed
browser.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

INTERNAL_SCHEMES = {'chrome', 'chrome-extension', 'chrome-untrusted', 'data', 'blob', 'devtools', 'about'}
# The encrypted DNS probe, and Windows' proxy auto-discovery (WPAD), which
# follows the system setting and only asks the local network.
ALLOWED_HOSTS = {'dns.quad9.net', 'wpad'}


def load_netlog(path):
    """NetLog JSON, repaired if the browser was killed mid-write."""
    text = Path(path).read_text(encoding='utf-8', errors='replace').rstrip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        text = text.rstrip(',\n ')
        if not text.endswith(']}'):
            text += ']}'
        return json.loads(text)


def contacts(netlog):
    types = {v: k for k, v in netlog['constants']['logEventTypes'].items()}
    urls, hosts = set(), set()
    for event in netlog.get('events', []):
        name = types.get(event.get('type'))
        params = event.get('params') or {}
        if name == 'URL_REQUEST_START_JOB' and 'url' in params:
            urls.add(params['url'])
        elif name in ('HOST_RESOLVER_MANAGER_REQUEST', 'HOST_RESOLVER_MANAGER_JOB',
                      'HOST_RESOLVER_DNS_TASK') and 'host' in params:
            hosts.add(params['host'].split('://')[-1].rsplit(':', 1)[0])
    return urls, hosts


def offending(urls, hosts):
    bad = []
    for url in sorted(urls):
        parts = urlsplit(url)
        if parts.scheme in INTERNAL_SCHEMES or parts.hostname in ALLOWED_HOSTS:
            continue
        bad.append(url)
    bad += [h for h in sorted(hosts) if h not in ALLOWED_HOSTS and h not in ('localhost', '127.0.0.1')]
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('browser')
    ap.add_argument('--seconds', type=int, default=60)
    ap.add_argument('--keep', type=Path, help='copy the NetLog there')
    args = ap.parse_args()

    profile = Path(tempfile.mkdtemp(prefix='hivey-startup-'))
    netlog = profile / 'netlog.json'
    cmd = [args.browser, f'--user-data-dir={profile / "profile"}', f'--log-net-log={netlog}',
           '--net-log-capture-mode=Default']
    if sys.platform.startswith('linux'):
        cmd.append('--password-store=basic')
        if os.geteuid() == 0:
            # Chromium refuses to run as root with its sandbox (CI containers).
            cmd.append('--no-sandbox')
    browser_log = open(profile / 'browser.log', 'w')
    proc = subprocess.Popen(cmd, stdout=browser_log, stderr=subprocess.STDOUT)
    try:
        time.sleep(args.seconds)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    browser_log.close()
    if args.keep:
        args.keep.mkdir(parents=True, exist_ok=True)
        shutil.copy2(profile / 'browser.log', args.keep / 'startup-browser.log')
        if netlog.exists():
            shutil.copy2(netlog, args.keep / 'startup-netlog.json')
    if not netlog.exists():
        print('FAIL: the browser wrote no NetLog (did it start?)')
        print((profile / 'browser.log').read_text()[-3000:])
        return 1
    urls, hosts = contacts(load_netlog(netlog))
    bad = offending(urls, hosts)
    print(f'{len(urls)} requests, {len(hosts)} DNS lookups in {args.seconds} s on a fresh profile')
    for url in sorted(urls):
        print(f'  request  {url}')
    for host in sorted(hosts):
        print(f'  lookup   {host}')
    shutil.rmtree(profile, ignore_errors=True)
    if bad:
        print('FAIL: contacted ' + ', '.join(bad))
        return 1
    print('PASS: nothing left the machine (besides the encrypted DNS probe)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
