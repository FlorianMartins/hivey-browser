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
```

The two ungoogled repositories are git submodules pinned to a release tag
(`third_party/`). Updating Chromium means bumping both submodules, then
fixing the Hivey patches that no longer apply. The smaller the Hivey layer,
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
| `scripts/branding.py` | applies `brand/brand.json` |
| `brand/brand.json` | product identity |
| `flags.hivey.gn` | GN args, applied after the ungoogled ones |
| `patches/series`, `patches/hivey/` | Hivey patches |
| `third_party/ungoogled-chromium*` | pinned submodules |
| `docs/` | documentation |

The build tree lives outside the repository (`$HB_BUILD_DIR`, by default
`../hivey-browser-build`).

## Product identity

`brand/brand.json` drives the Windows identity so the browser can sit next
to Chrome or Chromium without clashing: its own user-data directory, ProgIDs,
URL scheme and Active Setup GUID.

Known debt: the COM CLSIDs/IIDs of the elevation service and the toast
activator are still Chromium's. They are baked into MIDL outputs that
Chromium ships precompiled (`third_party/win_build_output`), so changing
them needs regenerated MIDL output. This matters only when Chromium is
installed system-wide on the same machine, and will be fixed before the
first public release.

## Feature work ahead

See [ROADMAP.md](ROADMAP.md). Each feature (privacy defaults, resource
controls, theming and animations, the Hivey AI sidebar) is planned as its
own patch set under `patches/hivey/<area>/`, plus new files where possible.
