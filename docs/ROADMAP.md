# Roadmap

Windows x64 first, then Linux. Each phase ends with a build that is tested
on a real Windows machine before moving on.

## Phase 0: Foundations (in progress)

- [x] Reproducible cross-build from Linux (no Windows machine needed)
- [x] ungoogled-chromium base, pinned and verified
- [x] Branding: name, install/user-data paths, ProgIDs, translated strings
- [x] Build that cannot starve a shared host (priority, memory cap, LTO threads)
- [ ] First `chrome.exe` + `mini_installer.exe` built and started on Windows
- [x] Logo and icons (`brand/logo.svg`, rendered at build time)
- [x] Own COM CLSIDs (elevation service, toast activator, tracing service)
- [ ] CI build

## Phase 1: Privacy

- [x] Built-in ad/tracker blocker (EasyList + EasyPrivacy, request blocking): ruleset generated (4.1 MB), browser side compiled; Windows test pending
- [ ] Cosmetic filtering (hide empty ad boxes)
- [ ] Blocked-requests counter in the toolbar
- [x] Fingerprinting deception on by default (Canvas, measureText, ClientRects)
- [x] Global Privacy Control on by default
- [x] GPU vendor/model hidden from WebGL
- [ ] More fingerprinting protections (fonts, audio)
- [x] HTTPS-only (strict) mode on by default
- [x] Encrypted DNS (secure mode, Quad9) by default
- [ ] Hardened defaults (third-party cookies, referrers, WebRTC IP handling)
- [x] DuckDuckGo as default search engine (local new tab page)
- [ ] Zero requests at startup, proven by a network capture in CI

## Phase 2: Resource control

- [x] Memory Saver on by default
- [x] RAM limiter (`chrome://flags/#hivey-memory-limit`, 2 to 12 GB), compiled; to be tested on Windows
- [x] RAM limiter in Settings > Performance > Memory (English + French)
- [ ] CPU limit
- [ ] Tab sleeping with per-site exceptions
- [ ] Memory saver
- [ ] Live per-tab resource panel

## Phase 3: Look and feel

- [x] Hivey amber as the default browser color (native Material palette)
- [x] Fluent overlay scrollbars on Windows
- [ ] Theme engine: colors, accents, transparency, corner radius
- [ ] Built-in animations (tabs, page transitions), with a reduced-motion mode
- [ ] Customization page, theme import/export

## Phase 4: Hivey AI sidebar

- [ ] Native side panel, like Leo in Brave
- [ ] Bring your own key, or local models
- [ ] Off by default; nothing sent until the user turns it on

## Phase 5: Distribution

- [ ] Signed installer and automatic updates
- [ ] Download page
- [ ] Linux build
