# UpgradedEden

A parallel asset pre-seeder for **ANOTHER EDEN** (Steam, app 1252600).

## The problem

The game's in-game updater is Cocos2d-x v3.13 `AssetsManagerEx` (confirmed from
symbols in `libcocos2d.dll`: `checkUpdate`, `genDiff`, `batchDownload`,
`setAssetDownloadState`, `saveToFile`, `decompressDownloadedZip`). It fetches
assets **one HTTP request per file**.

That would be tolerable if the CDN were fast per request. It isn't:

| Measurement | Result |
|---|---|
| 60 distinct small files, serial keep-alive | **466 ms/file** (2.1 files/s) |
| Same 60 again, ~30 s later | **522 ms/file** |
| Same *single* file, 8x back-to-back | **~40 ms** each |
| Network RTT to the Akamai edge | 36 ms |

`cdn-another-eden.akamaized.net` resolves to Akamai (`a1991.g1.akamai.net`), but
responses come back with `server: AmazonS3` and **no `Cache-Control`, no `Age`,
no edge-cache headers**. Objects are not retained at the edge, so nearly every
distinct asset request is a full round trip to the S3 origin (~470 ms) rather
than an edge hit (~40 ms, which is just the network RTT).

Phase 1 alone needs ~26,000 files. Serially that is **~3.5 hours** to move
215 MB.

## The fix

Do the same work concurrently. The CDN scales fine when you ask it to:

| Concurrency | Throughput |
|---|---|
| 1 (serial) | 2.1 files/s |
| 32 | 49.0 files/s |
| 64 | 73.9 files/s |
| 128 | 85.0 files/s |
| **this tool @ 96** | **~139 files/s** |

Phase 1 drops from ~3.5 hours to a few minutes.

## Why this is safe to do

- Manifests are public and unauthenticated
- Every asset URL is public and unsigned (verified across all 8 categories:
  `areaAtlas`, `character`, `sound/voice`, `sound/bgm`, `lwf`, `ui`, `i18n`, `spine`)
- Every manifest entry carries its own `md5`, so every byte is verified against
  the same hash the game itself uses

The tool fetches exactly the bytes the game would have fetched, and proves it.

## Usage

```
py preseed.py plan   [--phases 1,2] [--refresh]
py preseed.py fetch  [--phases 1] [--concurrency 64] [--limit N]
py preseed.py status
py preseed.py verify
```

Planning needs **no hashing** of the 13.6 GB install: `bundled.manifest`
is authoritative for what Steam shipped, so an asset is "already satisfied" if
its md5 matches the bundled manifest or something already verified into the
local mirror.

Configuration via environment:

- `UPGRADEDEDEN_GAME_DIR`   - Steam install path
- `UPGRADEDEDEN_REGION`     - `windows-us` (default), `windows-eu`, `windows-ap`, `windows`
- `UPGRADEDEDEN_CONCURRENCY`- default 64

## Status

**Done** - manifest reading, remote manifest fetch + cache, md5-based planning,
concurrent verified downloader, local mirror with resumable index.

**Not done** - placing the mirror into the game's own storage path so the
updater accepts it. This needs one instrumented run of the game to discover the
storage directory and the `project.manifest` state format. See
[tools/DISCOVERY.md](tools/DISCOVERY.md).

## Known blocker on ARM64

The development machine is a Snapdragon X Elite (ARM64) Surface Pro. The game
**cannot run there**: it ships an x64 kernel anti-cheat driver (`wfs64.sys`),
and ARM64 Windows cannot load x64 kernel drivers - Prism emulates user-mode code
only. The service fails with `WIN32_EXIT_CODE 1275` ("This driver has been
blocked from loading"), and the game exits cleanly (code 0) 1-3 seconds after
launch. Memory Integrity being enabled is a second, independent blocker.

The discovery run therefore requires a physical x86-64 Windows PC. Everything
else in this repo is machine-independent and works on ARM64.
