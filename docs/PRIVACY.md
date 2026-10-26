# Privacy

## Principles

1. **Nothing leaves the machine unless the user asked for it.** No
   telemetry, no usage statistics, no crash reports, no field trials, no
   "phone home" at startup.
2. **No accounts required.** No Google sign-in or sync.
3. **Features that talk to a server say so** and can be turned off (the
   update check, the Hivey AI sidebar when it comes).
4. **Claims are checked, not assumed.** `tests/startup_requests.py` starts a
   fresh profile with a NetLog capture and fails on any request;
   `tests/cdp_checks.py` measures each protection on a running browser. Both
   run on Windows and Linux before every release.

## What the base already removes

Inherited from ungoogled-chromium:

- Google API keys and services, Safe Browsing, field trials;
- hard-coded Google domains replaced with non-resolving ones (domain
  substitution), so a forgotten request fails instead of leaking;
- prebuilt binaries pruned from the source tree;
- hardened defaults: third-party cookies blocked, no hyperlink auditing
  (`<a ping>`), no network prediction (prefetch/preconnect), WebRTC without
  non-proxied UDP (no local IP leak), no background mode, translation,
  autofill and payment prompts off.

Inherited from ungoogled-chromium-windows: no RLZ, no machine ID, no
Windows event log, no private state tokens.

Hivey Browser build flags additionally keep crash/usage reporting
(`enable_reporting=false`) and field-trial configs off.

## What Hivey Browser adds

| Protection | Default | How to change it | Patch |
| --- | --- | --- | --- |
| Content blocker: uBlock Origin Lite with uBlock filters, EasyList, EasyPrivacy, Peter Lowe's list, malware lists (uBlock badware, URLhaus), tracking parameters (AdGuard URL tracking) and cookie banners; cosmetic filtering and scriptlets; rules ship with the browser, nothing is downloaded at runtime | **On** | Its toolbar icon (per site), or `chrome://extensions` | `privacy/bundled-content-blocker` |
| Cross-origin referrers cut to the origin, whatever the page's referrer policy (`Referer` header and `document.referrer`) | **On** | — | `privacy/referrer-cap-no-ad-apis` |
| No Topics API, Attribution Reporting or fenced frames (interest-based ads and their measurement) | **Off** | — | `privacy/referrer-cap-no-ad-apis` |
| Fingerprinting deception: tiny noise in Canvas image data, `measureText()`, `get*ClientRects()` and Web Audio data (`AudioBuffer`, `AnalyserNode`), recomputed per session | **On** | Hivey Studio > Privacy, or `chrome://flags/#disable-fingerprinting-noise` | `privacy/fingerprinting-*` |
| `navigator.hardwareConcurrency` reports at most 8 | **On** | same switch | `privacy/fingerprinting-audio-cpu` |
| Font fingerprinting protection: web pages only see the fonts that ship with Windows and common Linux desktops | **On** | same switch | `privacy/font-fingerprinting` |
| GPU vendor and model hidden from WebGL | **On** | `chrome://flags/#spoof-webgl-info` | `privacy/webgl-gpu-info-hidden` |
| Global Privacy Control (`Sec-GPC: 1`, `navigator.globalPrivacyControl`) | **On** | `chrome://flags/#enable-global-privacy-control` | `privacy/hardened-defaults` |
| Always use secure connections (strict HTTPS-only) | **On** | Hivey Studio > Privacy, or Settings > Security | `privacy/hardened-defaults` |
| Encrypted DNS (DNS-over-HTTPS, secure mode) through Quad9, which also refuses known malicious domains | **On** | Settings > Privacy and security > Security | `privacy/secure-dns-quad9` |
| DuckDuckGo as default search engine; its remote new tab page is removed | **On** | Settings > Search engine | `privacy/duckduckgo-default-search` |
| Web pages see the upstream Chromium version, not Hivey's | **On** | — | `build/hivey-updater` |
| USB, serial, HID and Bluetooth devices: sites cannot even ask for them (a common way to fingerprint and to attack hardware) | **Blocked** | Hivey Studio > Privacy, or per site in the address bar | `privacy/block-device-apis` |
| Hardened mode: no JavaScript optimizer (JIT) on any site, which removes the code most browser exploits target, at some speed cost | Off | Hivey Studio > Privacy | `customization/hivey-studio-themes` |

## The Hivey AI sidebar

AI browsers that read every page by themselves can be steered by a page:
hidden text tells the assistant to open another site, copy a form or send
your data somewhere (prompt injection). The Hivey AI sidebar is built so a
page cannot reach it on its own:

- **No site access by default.** It reads a page only when you open it on
  that tab (the extension's *on click* access), or on sites you allow in
  `chrome://extensions`. Only the AI providers' API addresses it names in its
  manifest stay allowed, so the chat works.
- **Your key, your provider.** Nothing is sent anywhere until you add an API
  key (Anthropic, OpenAI, OpenRouter, Mistral…) or point it at a local model;
  requests go straight from the browser to that provider, with no Hivey
  server in between.
- **Open source** (MIT, [HiveyAI-Sidebar](https://github.com/FlorianMartins/HiveyAI-Sidebar)),
  built from a pinned commit and signed into the browser like Hivey Shield.
  Hivey Studio > Privacy shows its status and links to its site access;
  `chrome://extensions` turns it off.

## Hivey Cyber: security tools

The shield-and-magnifier icon in the toolbar, and the right-click menu on a
page, a link or selected text, check a site in public security services:
WHOIS, IP geolocation, DNS records, certificates (crt.sh), VirusTotal,
urlscan.io, Shodan, SSL Labs, security headers, Mozilla Observatory and the
Wayback Machine, or search selected text in VirusTotal and Have I Been Pwned.
Each tool opens the service in a new tab, only when you click it: the
extension sends nothing by itself. Showing the site's IP address in the popup
asks Quad9's encrypted DNS, the resolver the browser already uses.

The noise is far too small to see or hear (audio: under 1e-6 of each sample,
about -120 dB) but changes the fingerprint a tracker computes. If a site that
draws in a canvas or processes audio misbehaves, turn the protection off in
Hivey Studio and restart.

Why Quad9: a Swiss non-profit, no IP address logging, and it refuses to
resolve known malicious domains. Captive portals (hotel or airport Wi-Fi)
still work: Chromium opens their login page without secure DNS.

## Requests the browser makes on its own

| Request | When | What it sends | Turn it off |
| --- | --- | --- | --- |
| Encrypted DNS probe to `dns.quad9.net` | at startup in secure DNS mode | a DNS query for a probe name, no browsing data | Settings > Security > secure DNS |
| Proxy auto-discovery (`wpad`, Windows) | at startup, when Windows' *Automatically detect settings* is on | a DNS lookup on the local network only | Windows Settings > Network > Proxy |
| Update check: `hivey-update.json` (+ signature) from GitHub releases | 10 minutes after start, then every 12 hours | a plain GET without cookies | Hivey Studio > About > Automatic updates |
| Update download (installer) | only when a newer, correctly signed release exists | a plain GET without cookies | same |

Nothing else: no extension, component or field-trial update service is
contacted (the bundled extensions update with the browser). The AI sidebar
talks only to the AI provider you set up, and only when you use it.

## Build-time downloads are not runtime requests

Building fetches compilers, Microsoft SDK files and uBlock Origin Lite (see
[BUILDING.md](BUILDING.md)). These are build-only; none of them is contacted
by the browser at runtime.
