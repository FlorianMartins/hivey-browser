# Building Hivey Browser

This guide builds Windows x64 binaries (`chrome.exe` and the
`mini_installer.exe` installer) **on a Linux host**. No Windows machine or
Visual Studio installation is needed.

## Prerequisites

| What | Why |
| --- | --- |
| Linux x86_64 (tested on Ubuntu 24.04) | build host |
| ~120 GB free disk, 32 GB RAM | source (11 GB) + build output |
| `python3` ≥ 3.12, `git`, `curl`, `xz` | scripts and downloads |
| `msitools` (`msiextract`, `msiinfo`) | unpack two Windows SDK MSIs |
| `7zip` (or `p7zip-full`) | pack the installer archive |
| `pkg-config` | configure the Linux host tools (blocker ruleset converter) |
| Python `cairosvg`, `Pillow` | render the icons |
| [`xwin`](https://github.com/Jake-Shadle/xwin) (`cargo install --locked xwin`) | MSVC CRT + Windows SDK |
| `libfuse2` (Ubuntu: `libfuse2t64`) | case-insensitive mount of the Windows toolchain (ciopfs) |
| `systemd-run` (optional) | memory-capped build |

Accepting the Microsoft license is required for the MSVC/SDK download: set
`XWIN_ACCEPT_LICENSE=1` (the script passes `--accept-license` to xwin).

## One command

```bash
python3 scripts/hb.py all
```

`all` runs every step below in order and skips the ones already done
(stamps live in `$HB_BUILD_DIR/.hb-state.json`). `hb.py status` shows
progress. Any single step can be re-run with `hb.py <step> --force`.

## Steps

| Step | What it does |
| --- | --- |
| `fetch` | Downloads the Chromium "lite" source tarball pinned by ungoogled-chromium and checks its sha256. |
| `unpack` | Extracts it into `$HB_BUILD_DIR/src`. |
| `prune` | Deletes prebuilt binaries listed by ungoogled-chromium, except the precompiled MIDL/MC outputs in `win_build_output/` (type libraries and message tables generated from the tree's `.idl`/`.mc` files): Linux has no `midl.exe`/`mc.exe`, so a cross-build needs them. |
| `toolchain` | Fetches **build-only** tools (never shipped): Chromium's pinned clang + Windows runtime, Rust, the Linux sysroot, `rc`, Node, ninja, gn (built from source), the Windows PGO profile, Windows-only sources missing from the lite tarball, and the MSVC CRT + Windows SDK. Must run before `domsub`. |
| `patch` | Applies ungoogled-chromium's patches, the product patches of ungoogled-chromium-windows, then `patches/series`. |
| `brand` | Applies `brand/brand.json` (see below). |
| `adblock` | Builds Chromium's `ruleset_converter` for the Linux host (`out/HostTools`), downloads EasyList and EasyPrivacy, converts them into the blocker ruleset embedded in `resources.pak`. Re-run with `--force` to refresh the lists. |
| `domsub` | ungoogled-chromium's domain substitution. |
| `configure` | Writes `out/Default/args.gn` and runs `gn gen`. |
| `build` | `ninja chrome mini_installer`. |

Outputs: `$HB_BUILD_DIR/src/out/Default/chrome.exe` and
`mini_installer.exe`.

## Where every Windows piece comes from

Chromium normally gets its Windows toolchain from a zip packaged on a
Windows machine with Visual Studio. We assemble the same layout from
Microsoft's public sources instead, verifying every file:

| Piece | Source | Verified by |
| --- | --- | --- |
| MSVC CRT 14.51, Windows SDK 10.0.28000 headers/libs | VS 2026 manifest, via xwin | sha256 in the manifest |
| VC++ redistributable DLLs | same manifest, `Microsoft.VC.<ver>.CRT.Redist.*` | sha256 in the manifest |
| `d3dcompiler_47.dll`, DXC DLLs | same manifest, SDK MSI "Windows Store Apps Tools" | sha256 in the manifest |
| `dbghelp.dll`, `dbgcore.dll` | NuGet `Microsoft.Debugging.Platform.DbgEng` | sha256 pinned in `hb.py` (checked against the NuGet catalog's SHA512) |
| DirectX-Headers, webauthn headers, `windows.0.52.0.lib` | GitHub (Microsoft), versions from ungoogled-chromium-windows | pinned commit / sha512 |
| clang, Rust, `rc`, sysroot, Node, PGO profile, ciopfs | Chromium's own storage buckets | sha1/sha256/md5 pinned by Chromium |
| Go (Dawn's source generators) | go.dev, version from Dawn's `go.mod` | sha256 from go.dev's index; the build runs with `GOTOOLCHAIN=local GOPROXY=off`, so Go never downloads anything itself |

Known quirks the script handles:

- Windows code includes headers with arbitrary casing (`ObjBase.h` for
  `objbase.h`). As in Chromium's own cross-build, the toolchain is served
  from a case-insensitive FUSE mount (ciopfs, binary pinned by Chromium):
  files are stored lower-cased in `winsysroot.ciopfs/` and mounted at
  `winsysroot/`. The mount is (re)created automatically before
  `toolchain`, `configure` and `build`, e.g. after a reboot.

- Microsoft's July 2026 SDK manifest has a raw space in one URL path
  (`w kits2`), which xwin rejects; the cached manifest is percent-encoded.
- `setup_toolchain.py` looks for `cl.exe` to find the VC bin directory. We
  build with clang-cl only, so an empty marker file is created; anything
  that tried to run it would fail loudly.
- gn loads the toolchain of every Windows CPU, so x86 and arm64 libraries
  are downloaded too.
- The PGO profile is stored gzip-compressed on GCS; its published md5 is the
  one of the compressed bytes.

## Not disturbing other services

The build host may also run production services. By default:

- every step runs at the lowest CPU priority (`nice 19`) and idle I/O
  priority (`ionice -c3`);
- ninja runs with `-j 8` (`HB_JOBS` to change; `HB_KEEP_GOING=0` keeps going past failures to collect them all);
- the build runs inside a transient systemd scope with
  `MemoryMax=26G`, `CPUWeight=10`, `IOWeight=10` (`HB_MEM_MAX` to change,
  `none` to disable). If a link outgrows the cap, the kernel kills the build,
  never another service;
- ThinLTO links use 4 threads instead of all hardware threads
  (`hivey_thin_lto_jobs` in `flags.hivey.gn`, added by
  `patches/hivey/build/thin-lto-jobs-arg.patch`).

`--full-priority` disables the priority changes.

## Branding

`brand/brand.json` is the single source of truth for the product identity:
product and company names, install and user-data paths
(`%LOCALAPPDATA%\Hivey\Browser\User Data`), ProgIDs, URL scheme, Active
Setup GUID. Icons (executable `.ico`, tiles, product logos, wordmark in
Space Grotesk, OFL-licensed in `brand/fonts/`) are rendered from
`brand/logo.svg`; this needs the Python packages `cairosvg` and `Pillow`.

User-visible strings are renamed **together with their translations**:
every `.xtb` translation is keyed by a fingerprint of the English text, so a
plain search-and-replace would silently drop all translations. `branding.py`
parses each `.grd` with Chromium's own grit before and after the rename and
re-keys the translations. "The Chromium Authors" is never renamed (BSD
attribution).

## Starting over

Domain substitution and branding rewrite files in place, so a hardlinked copy
of the tree is not a snapshot. To get a pristine tree, delete
`$HB_BUILD_DIR/src` and `.hb-state.json` (keep `download_cache/`, `tools/`,
`winsysroot/`, `xwin-cache/`) and run `hb.py all` again.
