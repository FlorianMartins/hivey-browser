# Windows checks

`cdp_checks.py` drives a running Hivey Browser over the DevTools protocol and
measures its privacy defaults (it does not trust the settings pages):

| Check | How |
| --- | --- |
| Global Privacy Control | `navigator.globalPrivacyControl` and the `Sec-GPC: 1` header echoed by httpbin.org |
| WebGL GPU hidden | `WEBGL_debug_renderer_info` values (needs a GPU; a VM without one reports "no webgl") |
| Canvas fingerprint noise | the same drawing hashes differently on two page loads |
| Built-in blocker | an ad script and a tracker fail to load, a normal request succeeds |
| HTTPS-Only | a plain-HTTP site does not load directly |

```bash
# in the Windows VM / PC
chrome.exe --remote-debugging-port=9222
# from the build host, through an SSH tunnel to the VM
ssh -L 19222:127.0.0.1:9222 user@vm
python3 tests/vm/cdp_checks.py http://127.0.0.1:19222 --shots shots/
```

Results on 2026-10-06 (Windows 11 VM, first build): 8/8 pass. The WebGL
check could not be exercised (no GPU in the VM). Chromium 154 shows the
HTTPS-Only warning as a dialog over the page, so a screenshot is the way to
see it. An A/B run with `--disable-features=SubresourceFilter` loads the ad
script: blocking comes from the built-in blocker.
