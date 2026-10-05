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

## Build-time downloads are not runtime requests

Building fetches compilers and Microsoft SDK files (see
[BUILDING.md](BUILDING.md)). These are build-only tools; none of them is
contacted by the browser at runtime.
