# UpgradedEden — context for Claude

You are running on an **x86-64 Windows PC**. You were brought in to finish one
specific, well-scoped task that could not be done on the machine where this
project was built. Read this whole file before doing anything.

---

## The goal in one sentence

Make ANOTHER EDEN's in-game asset updater accept assets we downloaded
*ourselves*, in parallel, instead of letting it fetch ~26,000 files one at a
time over ~3.5 hours.

---

## Background: why this project exists

ANOTHER EDEN (Steam app **1252600**) ships ~13.6 GB of loose assets and then, on
first boot, runs an in-game updater to pull whatever is newer than the shipped
build. That updater is stock **Cocos2d-x v3.13 `AssetsManagerEx`** — confirmed
from exported symbols in `libcocos2d.dll` (`checkUpdate`, `genDiff`,
`batchDownload`, `setAssetDownloadState`, `saveToFile`, `decompressDownloadedZip`).

It issues **one HTTP request per asset file**. That would be fine if the CDN
were fast per request. It is not. Measured against the live CDN:

| Test | Result |
|---|---|
| 60 distinct small files, serial keep-alive | **466 ms/file** (2.1 files/s) |
| Same 60 again, ~30 s later | **522 ms/file** |
| Same *single* file, 8x back-to-back on one connection | **~40 ms** each |
| Network RTT to the Akamai edge | 36 ms |

`cdn-another-eden.akamaized.net` resolves to Akamai (`a1991.g1.akamai.net`), but
responses carry `server: AmazonS3` with **no `Cache-Control`, no `Age`, and no
edge-cache headers**. Objects are not retained at the edge, so nearly every
*distinct* asset request is a full round trip to the S3 origin (~470 ms) rather
than an edge hit (~40 ms, i.e. just the network RTT). Hammering one object is
fast; moving through 26,000 distinct objects is not.

The CDN scales fine when asked concurrently — 49 files/s at 32 parallel, 85 at
128, and **139 files/s** from this tool. So the fix is simply to do the same
work in parallel.

**This is not a DRM or auth bypass.** The manifests are public and
unauthenticated, every asset URL is public and unsigned (verified across all 8
categories: `areaAtlas`, `character`, `sound/voice`, `sound/bgm`, `lwf`, `ui`,
`i18n`, `spine`), and every manifest entry carries its own `md5`. We fetch
exactly the bytes the game would have fetched and verify each one against the
game's own hash. The repo ships **no game assets** — `data/` is gitignored.

---

## What is already done

- `preseed.py` + `preseed/` — working, tested pre-seeder (Python **stdlib only**)
- **Phase 1 fully mirrored and verified on the build machine: 26,273 files,
  215 MB, 0 failures, 0 md5 mismatches**
- Full scope known across all 16 phases: 118,324 unique assets — 89,704 already
  shipped by Steam, 26,273 mirrored, 2,347 (2.06 GB) still to fetch
- `tools/snapshot.py` + `tools/diff_snapshot.py` — the instrumentation you need

---

## What is NOT done — your job

We know **what** to download and we can download it fast. We do **not** know
where to *put* it so the game accepts it.

`AssetsManagerEx` keeps its own state: a local manifest, a temp manifest, and a
storage path prepended to the engine's search paths. Two open questions:

1. **Where** does it write downloaded assets?
2. **What** state files does it keep, and in what format?

What we already know:

- The **format** is known — `manifests/bundled/<region>/bundled.manifest` on
  disk uses the same JSON schema as the remote `project.manifest.N`:
  `{"assets": {"<key>": {"md5", "path", "size"}}}`.
- Stock Cocos2d-x names are `project.manifest`, `project.manifest.temp`,
  `version.manifest` — but this build uses **customised** names
  (`bundled.manifest`, `phase.manifest.N`), so treat the defaults as a
  hypothesis to confirm, not a fact.
- The game's own uninstall script deletes `$install_dir_path\contents*`, which
  is a strong hint the storage path is `<install>\contents<something>`.
  **Unconfirmed.**
- Static analysis was a dead end: the Lua bootstrap is **encrypted**
  (high-entropy, no readable strings) and the binaries are packed. No
  storage-path strings in `AnotherEden.exe`, `libcocos2d.dll`, or
  `cpp_gamelib_global_api.dll`. Don't waste time re-deriving this — observe the
  running game instead.

---

## The procedure

Follow `tools/DISCOVERY.md`. Summary, with the parts that actually matter:

1. **Confirm the game has never been launched on this machine.** Check that
   `%LOCALAPPDATA%\AnotherEden` does not exist and there is no `contents*`
   directory in the install. On a virgin install every new file is attributable
   to the game, which makes the diff trivially readable. If it *has* been
   launched, say so — the diff will be much noisier and we should discuss it
   before proceeding.

2. **Let Steam finish any pending update first.** An update mid-run writes
   hundreds of thousands of files and destroys the signal. Confirm Steam shows
   *Play*, not *Update*.

3. If the install path differs from the default, set `UPGRADEDEDEN_GAME_DIR`.

4. `py tools\snapshot.py before` — **before the first launch.**

5. **Ask the user to launch the game** and let it run 3–5 minutes on the
   verify/download screen. Do not wait for completion — that is the ~3.5 hour
   path this project exists to eliminate. Have the user start it through Steam
   rather than launching the executable yourself, so startup is normal.

6. Have them **quit completely** and confirm `AnotherEden.exe` is gone from Task
   Manager. The updater may flush state on exit.

7. Capture and diff:

   ```
   py tools\snapshot.py after
   py tools\diff_snapshot.py before after > discovery.txt
   ```

8. **Read `discovery.txt` yourself and report the findings**, specifically:
   - the storage path (from *NEW DIRECTORIES*)
   - the on-disk asset tree layout (from *NEW FILES*, grouped by directory)
   - every file under *LIKELY UPDATER STATE FILES* — **dump their contents**;
     they are small JSON and they are the actual payload we need
   - whether downloaded assets sit at
     `<storage>/<version-hash>/contents/files/...` (matching the manifest
     `path` field) or at some flattened layout

---

## Known caveat

Quitting mid-download means you will likely see the **temp** manifest but not
the final one that `updateSucceed()` writes on phase completion. The temp
manifest carries per-asset download states, which is normally what a pre-seeder
needs to forge. If the completion state turns out to be required too, a second
run that finishes one *small* phase will cover it — phases 6, 10, 12 and 16 are
the smallest (457–856 assets each).

---

## Ground rules

- **Do not disable Memory Integrity, disable anti-cheat, or patch game
  binaries.** None of that is needed for this task, and it is not what this
  project is for.
- **Do not commit anything under `data/`** — it is gitignored for good reason
  (game assets we must not redistribute, plus snapshots containing local user
  paths).
- The tooling is **stdlib-only Python 3**. Do not add dependencies.
- If something here contradicts what you observe, trust your observations and
  say so. Several claims in this document are inferences and are marked as such.

---

## Useful commands

```
py preseed.py plan                  # what needs downloading
py preseed.py fetch --phases 1      # download phase 1 concurrently
py preseed.py status                # mirror state
py preseed.py verify                # re-verify every mirrored file's md5

py tools\snapshot.py before
py tools\snapshot.py after
py tools\diff_snapshot.py before after
```

Environment overrides: `UPGRADEDEDEN_GAME_DIR`, `UPGRADEDEDEN_REGION`
(`windows-us` default), `UPGRADEDEDEN_CONCURRENCY` (64),
`UPGRADEDEDEN_LINK_MBPS` (50).

---

## Why the build machine couldn't do this

It is a Snapdragon X Elite (**ARM64**) Surface Pro. ANOTHER EDEN ships an **x64
kernel anti-cheat driver** (`wfs64.sys`), and ARM64 Windows cannot load x64
kernel drivers — Prism emulates user-mode code only. The service fails with
`WIN32_EXIT_CODE 1275` ("This driver has been blocked from loading") and the
game exits cleanly (code 0) 1–3 seconds after launch, five times over. Memory
Integrity being enabled is a second, independent blocker.

To be precise about the evidence: the blocked driver and the immediate clean
exit are both **measured**. The causal link between them is a strong
**inference** — the packed binaries and encrypted Lua made the actual check
unreadable. If the game also fails to launch on your x86-64 machine, that
inference was wrong; report it rather than assuming this document is correct.
