# MuMu resource download investigation

September 25–26, 2026. Surface Pro 11, Windows ARM64, MuMuPlayerARM 1.8.5.0,
isolated `ForeverEden 3.17.0` / `vm2.gmadoa` profile. United States, Japanese voices.

**Completed:** original assets were preloaded with the emulator's existing
parallel `curl`. All **119,259 Android asset files / 10,928,437,494 bytes** passed
final MD5, size and ownership checks, with no missing or mismatching files and
no remaining temporary files. The original client then passed **Download All**
and its update checks and reached **New Game**. It is left at that screen.

All five publisher-signed APK splits are unchanged, Root Access is **Off**, and
the instrumentation server is stopped. The final 1.66 GB transfer averaged
**7.74 MB/s**, versus the earlier stock sample of **0.373 MB/s**. Runtime tuning
was abandoned after process exits; the successful solution is resource preloading,
not a stable APK patch. Gameplay and anti-cheat reliability remain unverified.

## Findings

The original Android client uses
`net.wrightflyer.cocos2dx.network.Cocos2dxDownloader`, backed by LoopJ
`AsyncHttpClient` and Apache `ThreadSafeClientConnManager`. It starts six
tasks per downloader. Its actual HTTP pool initially permits ten connections
total and ten per route. Downloads use separate requests for many small files.
The task queue and connection limits restrict parallelism.

The manager's public `getDefaultMaxPerRoute()` misleadingly returns **2**:
its deprecated constructor creates a separate route-limit object for the
underlying `ConnPoolByRoute`. The actual backend uses **10**, supplied by
`AsyncHttpClient`. Changing only the public manager or HTTP parameters does
not update that existing backend. This corrects the initial diagnostic reading.

Download confirmation also recreates the phase downloaders, and native code
reapplies its task limit. Updating old instances once is insufficient.
Increasing a limit on an already queued batch also does not fill the new
slots: stock completion schedules only one replacement task.

## Measurements

| Observation | Result | Scope |
|---|---:|---|
| Initial guest network receive rate | 0.373 MB/s over 276.7 seconds | Whole guest; stock download at 24.16% |
| Host, 32 small assets, 8 parallel requests | 3.15–6.83 MB/s | 1.35 MB batch, sizes and MD5 verified; cache/order effects remain |
| Same host batch, one worker | 0.295 and 0.854 MB/s | Before and after parallel runs |
| Guest built-in curl, one 1.39 MB asset | 6.72 MB/s | Public CDN asset, HTTP 200 |
| Host, same 1.39 MB asset | 6.14 MB/s | Same URL |
| Tuned game, 24 tasks / backend still 10 | 3.232 MB/s over 188.9 seconds | Whole guest; includes a small diagnostic asset download |
| Tuned game, corrected backend | 3.326 MB/s over 136.9 seconds | 24 tasks and 24 actual pooled connections confirmed; process later exited |
| Optimized preloader, first long run | 6.160 GB in 854.37 seconds; 7.21 MB/s | Includes verification/publication and a 132-second CDN stall; also included PC movies subsequently removed |
| Final Android-only preload | 1.656 GB in 213.85 seconds; 7.74 MB/s | 7,092 files, including hash checks and publication; startup inventory excluded |
| Final complete-cache verification | 119,259 files / 10.928 GB, zero missing or mismatching | MD5, size, ownership and installed APK hashes; 85.96 seconds |

The samples establish available bandwidth and a material improvement; they
are not a controlled same-file full-install benchmark or a guaranteed speed.
The stock file writer uses 4 KiB buffers/progress callbacks, but their contribution
has not been isolated. No evidence establishes a fixed publisher speed throttle.

A later batch also exposed a transient per-asset stall: 511 files verified while
one 1,175,216-byte texture had not arrived. A separate host request to its original
URL hit a 20-second read timeout; the same URL with a checksum query returned
HTTP 200 in 1.713 seconds with the exact expected size and MD5. The guest's
original request eventually recovered; the batch took 132.3 seconds. No URL
change was needed in the preloader. This establishes an additional path-specific
delay, but does not isolate CDN caching, routing or connection behavior as its
cause. `android-preseed/cdn-stall-probe.json` retains the observations.

## Runtime tuning experiment — abandoned

`tools/android_download_tune.js` applies UpgradedEden's parallel-download
approach to the existing Android downloader: 24 tasks, 24 total connections,
and 24 connections per route in the actual backend. It checks package/build,
updates future downloaders, preserves original request/completion methods,
fills available slots under the existing queue lock, and reads back limits.

This was **temporary process instrumentation**, not a rebuilt or re-signed APK.
The original publisher-signed splits and current app data remain installed.
No URL, TLS, integrity check, account, gameplay, or anti-cheat method is patched.
Original inputs and other MuMu profiles are unchanged. The existing host
mirror was not copied into Android, and no manifest was fabricated or edited.

MuMu's built-in Root Access option was enabled only in `vm2.gmadoa`. The
matching ARM64 Frida server 17.12.0 was bound to guest loopback. Its downloaded
archive matched the official GitHub release SHA-256; provenance is retained
locally in `data/forevereden-evidence/tools/frida-source.json`.
The installed Frida CLI supplies its Java bridge; see
[Frida's Android documentation](https://frida.re/docs/android/).

An initial diagnostic attach using a manually assembled Java bridge ended
the game process before tuning. Restart preserved existing downloads: the
remaining confirmation fell from the original 10,414.7 MB to 7,744.4 MB.
The first tuned phase subsequently reported error 8; its cause is not proven.
A retry preserved its completed files and requested 7,690.6 MB. “Reacquire
Data” was not used. These are experimental results, not a reliability claim.

The process exited again after the faster interval. Its cause was not established;
do not attribute it to anti-cheat or call the tuning reliable. The process-local
changes are now gone, and the task's Frida server was stopped. The experimental
script is retained as evidence and explicitly marked unsuitable as a stable patch.

## Resource preloading

`tools/android_preseed.py` uses the existing Android `curl 7.73.0` parallel mode
with 24 requests, applying the same concurrency approach as UpgradedEden without
injecting code or rebuilding the client. Android's downloader avoids keeping a
second multi-gigabyte host mirror. The game's process must remain stopped.

The tool pins all sixteen live manifests by SHA-256 and rejects a different
generation/region/texture variant, unsafe paths, symlinks, invalid asset hashes,
unexpected data ownership and insufficient host free space. It hashes existing
files instead of trusting their names or old mirror metadata. Nonmatching
existing final files cause a refusal rather than an overwrite.

Each batch downloads to separate temporary filenames. Every file must match its
manifest MD5 before publication; the game must still be stopped. Files are renamed
into place, app ownership/permissions and SELinux labels are restored, and a
local batch journal records progress. Existing cache manifests and account data
were not rewritten by the preloader. The original client performed its final
resource check and generated its own updater state.

Publication initially spent about 30 seconds on some 512-file batches because
permissions and renames launched several subprocesses per tiny asset. The tool
now batches permission changes and uses Android mksh's native `rename` builtin.
That removes the avoidable publication overhead without adding a dependency.

Before preloading, **86,714 existing asset files matched their live manifests;
none mismatched**. The first **512 new assets** all passed hash checks and were
published. The first verification attempt safely refused publication because
Windows CRLF endings polluted checksum paths; guest control files now use LF.
The subsequent run planned 32,155 files / 8,969,462,574 bytes. This includes
all missing manifest-listed variants; it can exceed the client's selected subset.

The tool defaults to a 3 GiB host free-space reserve because the emulator's large
virtual free-space figure does not describe free space on the Surface SSD.
The reserve is adjustable, with a 2 GiB minimum. Completed batches remain usable
if interrupted. Root Access must be restored to Off after the download, followed
by a clean original-client start.

After 6,159,928,840 bytes in the optimized run, Android started a background
game process while Lawnchair remained the foreground activity. The preloader's
post-verification process guard refused publication. The background game was
force-stopped and the preloader resumed from a fresh inventory; previously
published resources were preserved. The exact background start trigger was not
captured. This is distinct from the earlier instrumented process exits.

Subsequent resume attempts refused to start when Windows free space fluctuated
below the remaining transfer plus reserve, including an attempt at 2 GiB.
NTFS compression of task analysis files recovered roughly 320 MB without
deleting their contents; the large decoded master retained its SHA-256.

The complete manifests also include `files/movie_pc/`. The initial Android
inventory had none of those files, and stock phase 1 had completed without them.
The Android preloader now excludes that directory, while retaining the separate
Android `files/movie/` resources. Seventy-nine PC movie files or verified temporary
files introduced by this task, totaling 1,682,657,504 bytes, were removed only
after checking their current hashes and absence from the original inventory.
The exact removal list is retained in `android-preseed/removed-task-pc-movies.json`.
The resulting remaining Android transfer was 1,655,510,442 bytes and resumed
with the default 3 GiB reserve. No preexisting resource or account data was removed.

## Exact content generation

The running updater selected **`ec741d3cc2f29b867892b1ed16a7a59b40e3968d`**,
texture variant **`pkm`**, region **`us`**. All sixteen live temporary manifests
were copied read-only before tuning into
`data/forevereden-evidence/android-download-before/`.

This differs from both the APK's packaged `898712...` generation and the old
Steam mirror's `5ddcd4...` generation. Earlier master/Lua research against the
packaged generation remains separate evidence; it cannot silently stand in for
these downloaded assets. The sixteen remote asset lists total 12,992,422,742
bytes across all listed variants/languages; that is not the selected UI download
size. The client selects its required subset and reuses existing/bundled files.

`forevereden/runtime-identity.json` remains the frozen APK baseline.
`data/forevereden-evidence/download-runtime-session.json` records its parent ID,
the exact temporary tuning-script hash, process/profile and live content version.
This experimental session does not claim the untouched baseline's runtime state
or a completed private-server content identity.

## Evidence

Local evidence is under `data/forevereden-evidence/`: original-class decompilation,
`download-network-samples.json`, `download-cdn-benchmark.json`, tuning/readback
logs, screenshots and manifest copies. `android-preseed/plan.json` records the
manifest hashes; `batches.jsonl` records verified/published batches.
`python tools/test_android_preseed.py` passes the path, batch, generation and
guest-newline regression checks. Installed hashes of all five APK splits still
match the frozen baseline. `android-preseed/verification.json` records the final
complete-cache checks; `download-stage.json` and `download-complete-new-game.png`
record the clean original-client acceptance at 2026-09-26 04:01 UTC. ADB reports
UID 2000 after Root Access was disabled, no task Frida server remains, and the
original process is running without the temporary hooks. Windows had about
4.96 GB free at completion. New Game was not pressed.
