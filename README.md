# UpgradedEden

A parallel asset pre-seeder for **ANOTHER EDEN** (Steam, app 1252600).

ForeverEden preservation work now starts with the original Android 3.17.0
ARM64 client on the Surface. The original client has downloaded its resources
and rendered the opening story in an isolated MuMuPlayerARM Android 12 instance.
A separate private client now accepts local login, resource metadata and an
encrypted profile pull, loads the captured Mayor's House checkpoint and supports
movement there. Its profile is an offline, sanitized copy of an original-client
capture; the private path never
contacts the official account service. The Android launcher can also capture a
profile without root: after Android's one-time VPN and user-CA consent screens,
an app-scoped `VpnService` routes only the original client to a local TLS bridge,
requests one normal client-signed full pull, strips official identity/session
credentials and adds the resulting 207-table profile to its User Manager. It
never invokes account transfer or migration. The server recognizes 38 of the 39
actions found in the exact ARM64 client, but recognition is not support: 18
currently have non-stub semantics. Four necessary gameplay routes remain rejected
with HTTP 503 until their complete state contracts are recovered.
Subscription-only key recovery stays unreachable because local subscriptions
are not advertised.
Login, profile pull/push, local billing, paid battle continuation, dungeon-key
purchase, Dreams draws, quest close, gift receive, Battle Rush rewards and the
three Star Library reward paths have dedicated behavior. Their exact client
operation types and parameter fields are pinned from the frozen binary; issued
operations survive restart and are removed only after the matching client save
acknowledgement. Dreams draws spend local Chronos Stones and use the exact normal/guaranteed
layouts and weighted `lotteryPCEx` pools for all 1,682 drawable 3.17.0 banners.
Local tickets are bounded by the selected profile; key purchase and battle
continuation debit the exact original 3.17.0 consume rows (20/40 and 50 Chronos
Stones), and draws select from the full original pools. Specialized server-owned
reward and account effects that
cannot be proven from client saves remain uncertified rather than being counted
as complete.
See [LOCAL_LOGIN_REPORT.md](forevereden/LOCAL_LOGIN_REPORT.md) for the captured
starter profile, SQLite server, tests and explicit pairing-mode limitations.

Start the local ForeverEden listener from this repository with Node.js 24:

```powershell
npm run listen
```

No `npm install` is needed. Start the ForeverEden MuMu instance first. The command
automatically connects ADB, imports the selected User Manager profile and its
existing local state into a profile-specific SQLite database, installs the guest
loopback reverse, starts the host listener at `127.0.0.1:28765`, and launches the
private client. Press Ctrl+C to stop the listener and remove the reverse. Starting
the private client from the Android launcher itself remains available as a
standalone on-device JSON-backed mode. Its User Manager can create and select
local profiles, reset with a recovery copy, restore the latest backup, and
export/import a bounded profile-and-state backup.
Permanent asset preloading and the older temporary resource
setup is described in [LOCAL_LOGIN_REPORT.md](forevereden/LOCAL_LOGIN_REPORT.md#reproduce-the-local-login).

See [forevereden/README.md](forevereden/README.md)
for the frozen-client launcher, runtime identity, evidence and capability ledger.
Private movement, the captured quest/save flow, area transitions, treasure/profile deltas,
local purchases and their saves are implemented. Full server-owned combat and
publisher-only specialized reward semantics are intentionally outside the local
single-player scope. The Steam-specific
blocker and measurements below are historical; see
[REPOSITORY_REVIEW.md](REPOSITORY_REVIEW.md) for their verification limits.

## Necessary private-server status

The frozen 3.17.0 client path is playable for the tested local single-player
flows, but packet support is incomplete. Profile creation/selection/backup works, 207-table
saves are atomic and replay-safe, and the real client has completed area,
battle, quest, treasure, Dreams, dungeon entry/exit and restart flows. A
dungeon-exit reconnect loop was traced to locally advertised subscriptions;
subscriptions now report unavailable and the same saved profile restarts into
Spacetime Rift normally. SQLite stores run `PRAGMA quick_check` before use and
malformed JSON stores fail closed. The packaged launcher contains the exact
consume-ID key protocol and nested response shape expected by the frozen client.
The later quest-clear loop was a different failure: save sequence 1267 carried a
`StarLibraryUpdateState` delta for `UserStarLibraryMissionStatus`, whose composite
row identity was missing. The shared save path now keys it by `userId` and
`missionId`; the same retained device state retried sequence 1267 successfully and
loaded back into the dungeon without resetting the profile.

Four necessary gameplay actions remain incomplete and are rejected rather than
acknowledged: Cat Diary reward, roguelike dungeon completion, pack acquisition
and costume acquisition. Publisher migration, social/friends, ads, serial codes, official payment
history/subscriptions, remote authentication, and a duplicate server-side
ordinary-battle simulator are not necessary for this local server. Their
terminal compatibility exists only for the two migration-status checks used by
startup; excluded publisher-service actions are not claimed or acknowledged.

The Android download investigation and exact-manifest resource preloader are
documented in [forevereden/DOWNLOAD_INVESTIGATION.md](forevereden/DOWNLOAD_INVESTIGATION.md).
It preserves the signed APK and uses the isolated emulator's existing parallel curl.

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
storage directory and the `project.manifest` state format.

- Running that on an x86-64 box with Claude Code? [CLAUDE.md](CLAUDE.md) is
  the full self-contained handoff and is auto-loaded.
- Doing it by hand? [tools/DISCOVERY.md](tools/DISCOVERY.md) has the steps.

## Known blocker on ARM64

The development machine is a Snapdragon X Elite (ARM64) Surface Pro. The game
**cannot run there**: it ships an x64 kernel anti-cheat driver (`wfs64.sys`),
and ARM64 Windows cannot load x64 kernel drivers - Prism emulates user-mode code
only. The service fails with `WIN32_EXIT_CODE 1275` ("This driver has been
blocked from loading"), and the game exits cleanly (code 0) 1-3 seconds after
launch. Memory Integrity being enabled is a second, independent blocker.

The discovery run therefore requires a physical x86-64 Windows PC. Everything
else in this repo is machine-independent and works on ARM64.
