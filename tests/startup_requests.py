#!/usr/bin/env python3
"""Prove that Hivey Browser makes no network request at startup, but for the model.

    startup_requests.py <browser executable> [--seconds 60] [--keep DIR]

Starts the browser on a fresh profile (so the first-run tab opens too) with
a NetLog capture, lets it idle, closes it, and lists every request and DNS
lookup it made. Then starts it again on that profile, which is what every
start after the first one looks like. Allowed: browser-internal URLs
(chrome://, extensions, data:), the encrypted DNS resolver's own probe
(dns.quad9.net), and on Windows the proxy auto-discovery lookup (wpad, local
network only, when the system's "Automatically detect settings" is on). None
carries user data. On the very first start only, the local AI model's download
from Hugging Face or GitHub is allowed too. Anything else fails the check.

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
# The local AI model, fetched once on the very first start: from Hugging Face
# (and its storage), or the Hivey agent model from a GitHub release (and the
# storage GitHub redirects to).
MODEL_DOMAINS = ('huggingface.co', 'hf.co', 'github.com', 'githubusercontent.com')


def load_netlog(path):
    """NetLog JSON, repaired if the browser was killed mid-write."""
    text = Path(path).read_text(encoding='utf-8', errors='replace').rstrip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # One event per line: drop what the kill cut in the middle of a line.
        text = text[:text.rindex('},\n') + 1]
        return json.loads(text + ']}')


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


def is_model_host(host):
    return any(host == domain or host.endswith('.' + domain) for domain in MODEL_DOMAINS)


def offending(urls, hosts, first_start=False):
    def allowed(host):
        return host in ALLOWED_HOSTS or (first_start and is_model_host(host or ''))

    bad = []
    for url in sorted(urls):
        parts = urlsplit(url)
        if parts.scheme in INTERNAL_SCHEMES or allowed(parts.hostname):
            continue
        bad.append(url)
    bad += [h for h in sorted(hosts) if not allowed(h) and h not in ('localhost', '127.0.0.1')]
    return bad


def run_once(browser, profile, name, seconds, keep, first_start):
    """One start on that profile; the check's answer for it."""
    netlog = profile / f'{name}-netlog.json'
    cmd = [browser, f'--user-data-dir={profile / "profile"}', f'--log-net-log={netlog}',
           '--net-log-capture-mode=Default']
    if sys.platform.startswith('linux'):
        cmd.append('--password-store=basic')
        if os.geteuid() == 0:
            # Chromium refuses to run as root with its sandbox (CI containers).
            cmd.append('--no-sandbox')
    log_path = profile / f'{name}-browser.log'
    browser_log = open(log_path, 'w')
    proc = subprocess.Popen(cmd, stdout=browser_log, stderr=subprocess.STDOUT)
    try:
        time.sleep(seconds)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    browser_log.close()
    if keep:
        keep.mkdir(parents=True, exist_ok=True)
        shutil.copy2(log_path, keep / f'startup-{name}-browser.log')
    if not netlog.exists():
        print(f'FAIL: the browser wrote no NetLog on its {name} start (did it start?)')
        print(log_path.read_text()[-3000:])
        return False
    urls, hosts = contacts(load_netlog(netlog))
    bad = offending(urls, hosts, first_start)
    print(f'{name} start: {len(urls)} requests, {len(hosts)} DNS lookups in {seconds} s')
    for url in sorted(urls):
        print(f'  request  {url}')
    for host in sorted(hosts):
        print(f'  lookup   {host}')
    if bad:
        print(f'FAIL: the {name} start contacted ' + ', '.join(bad))
        # Only then: with the model's download, a first start's log is hundreds of MB.
        if keep:
            shutil.copy2(netlog, keep / f'startup-{name}-netlog.json')
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('browser')
    ap.add_argument('--seconds', type=int, default=60)
    ap.add_argument('--keep', type=Path, help='copy the NetLog there')
    args = ap.parse_args()

    profile = Path(tempfile.mkdtemp(prefix='hivey-startup-'))
    first = run_once(args.browser, profile, 'first', args.seconds, args.keep, True)
    # Run both even when the first fails: each tells something of its own.
    second = run_once(args.browser, profile, 'second', args.seconds, args.keep, False)
    shutil.rmtree(profile, ignore_errors=True)
    if not (first and second):
        return 1
    print('PASS: nothing left the machine (besides the encrypted DNS probe, and the model on the first start)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
