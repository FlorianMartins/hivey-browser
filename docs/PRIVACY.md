# Privacy

## Principles

1. **Nothing leaves the machine unless the user asked for it.** No
   telemetry, no usage statistics, no crash reports, no field trials, no
   "phone home" at startup.
2. **No accounts required.** No Google sign-in or sync.
3. **Features that talk to a server are off by default** and say so where
   they are turned on (for example the Hivey AI sidebar).
4. **Claims are checked, not assumed.** A network capture of a fresh
   profile at startup is planned in CI (see the roadmap).

## What the base already removes

Inherited from ungoogled-chromium:

- Google API keys and services, Safe Browsing, field trials;
- hard-coded Google domains replaced with non-resolving ones (domain
  substitution), so a forgotten request fails instead of leaking;
- prebuilt binaries pruned from the source tree.

Inherited from ungoogled-chromium-windows: no RLZ, no machine ID, no
Windows event log, no private state tokens.

Hivey Browser build flags additionally keep crash/usage reporting
(`enable_reporting=false`) and field-trial configs off.

## What Hivey Browser adds

| Protection | Default | How to change it | Patch |
| --- | --- | --- | --- |
| Built-in ad and tracker blocker: EasyList + EasyPrivacy, applied to every site by Chromium's own subresource filter; nothing is downloaded at runtime and no per-site record is kept | **On** | Address bar icon > *Always allow on this site*, or Settings > Site settings > Ads | `privacy/builtin-adblock` |
| DuckDuckGo as default search engine, in every country; its remote new tab page and logo are removed so new tabs stay local | **On** | Settings > Search engine | `privacy/duckduckgo-default-search` |
| Fingerprinting deception: tiny noise in Canvas image data, `measureText()` and `get*ClientRects()`, recomputed on every page load | **On** | `chrome://flags/#disable-fingerprinting-noise` | `privacy/fingerprinting-noise-on-by-default` |
| Global Privacy Control: `Sec-GPC: 1` header and `navigator.globalPrivacyControl` tell sites not to sell or share your data | **On** | `chrome://flags/#enable-global-privacy-control` | `privacy/hardened-defaults` |
| Always use secure connections (strict): warns before loading any page over plain HTTP | **On** | Settings > Privacy and security > Security | `privacy/hardened-defaults` |
| Encrypted DNS (DNS-over-HTTPS, secure mode) through Quad9: your network provider no longer sees the sites you visit | **On** | Settings > Privacy and security > Security > Use secure DNS | `privacy/secure-dns-quad9` |
| GPU vendor and model hidden from WebGL (`WEBGL_debug_renderer_info` returns a blank value, the same for every Hivey user) | **On** | `chrome://flags/#spoof-webgl-info` | `privacy/webgl-gpu-info-hidden` |

About the blocker: the rules are converted at build time from EasyList and
EasyPrivacy (their version and sha256 are logged in
`$HB_BUILD_DIR/adblock-lists.json`) and ship inside the browser, so they
update with each release. It blocks requests (ads, trackers); hiding the
empty boxes left by ads (cosmetic filtering) is not supported by Chromium
154 yet. EasyList and EasyPrivacy are maintained by The EasyList authors
(https://easylist.to) and licensed under GPLv3 / CC BY-SA 3.0.

Why Quad9: a Swiss non-profit, no IP address logging, and it refuses to
resolve known malicious domains. Captive portals (hotel or airport Wi-Fi)
still work: Chromium opens their login page without secure DNS.

The noise is small enough to be invisible on screen but changes the
fingerprint a tracker computes on every page load.

## Build-time downloads are not runtime requests

Building fetches compilers and Microsoft SDK files (see
[BUILDING.md](BUILDING.md)). These are build-only tools; none of them is
contacted by the browser at runtime.
