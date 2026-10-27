# Architecture

## A patch stack, not a fork

Hivey Browser never forks the Chromium repository. Each release is rebuilt
from four layers, applied in this order on top of the official source
tarball:

```
Chromium source tarball (sha256-verified)
  └─ ungoogled-chromium        patches, binary pruning, domain substitution
      └─ ungoogled-chromium-windows   Windows product patches (selected)
          └─ Hivey patches     patches/series
              └─ Hivey branding    brand/brand.json → scripts/branding.py
                  └─ bundled extensions   extensions/bundled.json → hb.py bundle
```

One patched tree builds both targets: Windows (cross-compiled, `out/Default`)
and Linux (`out/Linux`).

The two ungoogled repositories are git submodules pinned to a release tag
(`third_party/`). Updating Chromium means bumping both submodules, then
fixing the Hivey patches that no longer apply; `scripts/autoupdate.py` does
it unattended when the patches still apply (see [RELEASES.md](RELEASES.md)). The smaller the Hivey layer,
the faster a security update ships, so features go into well-contained
patches or new files rather than broad edits.

### Which ungoogled-chromium-windows patches we use

That repository builds *on* Windows with upstream LLVM. We cross-compile
from Linux with Chromium's own clang and Rust, so the patches that only
adapt the build to a Windows host are skipped
(`WINDOWS_HOST_ONLY_PATCHES` in `scripts/hb.py`): Microsoft `rc.exe`,
`gn.exe`/`python.exe` paths, clang version checks, upstream-LLVM flag
workarounds, the upstream-Rust switch. The product patches are kept: no
RLZ, no machine ID, no Windows event log, no private state tokens,
building without Safe Browsing, the mini installer, and an opt-in
`--disable-encryption` flag (encryption stays **on** by default).

## Repository layout

| Path | Content |
| --- | --- |
| `scripts/hb.py` | build orchestrator (one sub-command per step) |
| `scripts/patchcheck.py` | applies the patch stack to the source tarball, no build |
| `scripts/mkpatch.py` | turns edited copies of Chromium files into a Hivey patch |
| `scripts/branding.py` | applies `brand/brand.json` |
| `scripts/crx3.py` | packs and signs the bundled extension |
| `scripts/release.py`, `scripts/autoupdate.py` | releases and the automatic Chromium updates |
| `brand/brand.json` | product identity |
| `extensions/bundled.json` | bundled extensions (uBlock Origin Lite), pinned |
| `flags.hivey.gn`, `flags.hivey.<target>.gn` | GN args, applied after the ungoogled ones |
| `HIVEY_REVISION` | Hivey revision on top of the Chromium version |
| `patches/series`, `patches/hivey/` | Hivey patches |
| `tests/` | startup-request and privacy checks (Windows and Linux) |
| `third_party/ungoogled-chromium*` | pinned submodules |
| `docs/` | documentation |

Hivey's patches, by area:

| Area | Patches |
| --- | --- |
| `build/` | ThinLTO thread cap, 7-Zip on a Linux host, the updater |
| `privacy/` | content blocker loader, referrer cap and ad APIs off, fingerprinting (canvas, text, rects, audio, CPU count, fonts, WebGL), GPC + HTTPS-only, Quad9, DuckDuckGo |
| `resources/` | Memory Saver, RAM limiter (+ settings), CPU and network limiters |
| `customization/` | default color, overlay scrollbars, compact mode, Hivey Settings |

New features go into new files (`chrome/browser/hivey/`,
`chrome/browser/ui/webui/hivey/`, `chrome/browser/resources/hivey_studio/`)
with small hooks in Chromium's files, so updates rarely conflict.

The build tree lives outside the repository (`$HB_BUILD_DIR`, by default
`../hivey-browser-build`).

## Product identity

`brand/brand.json` drives the Windows identity so the browser can sit next
to Chrome or Chromium without clashing: its own user-data directory, ProgIDs,
URL scheme and Active Setup GUID.

The COM classes the installer registers (elevation service, notification
toast activator, tracing service) also get their own CLSIDs from
`brand.json`. The COM *interface* IDs (IIDs) stay Chromium's: they are
shared by every Chromium-based browser in the IDL and precompiled MIDL
output, and do not identify the product.

## Feature work ahead

See [ROADMAP.md](ROADMAP.md).
