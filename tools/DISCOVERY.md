# Discovery run (needs an x86-64 Windows PC)

Everything except the final placement step is done. This run answers the two
open questions:

1. **Where** does `AssetsManagerEx` write downloaded assets?
2. **What** state files does it keep, and in what format?

Cocos2d-x defaults are `project.manifest`, `project.manifest.temp` and
`version.manifest`, but this build uses customised names (`bundled.manifest`,
`phase.manifest.N`), so the defaults are a guess worth confirming rather than
assuming. The **format** is already known - `bundled.manifest` on disk uses the
same JSON schema as the remote `project.manifest.N`.

## Requirements

- A physical **x86-64** Windows PC (not ARM64, not a VM - the anti-cheat driver
  `wfsdrv` is a kernel driver and is likely to refuse both)
- Python 3 (`py --version`)
- ANOTHER EDEN installed via Steam, **never launched on that machine**

The "never launched" part matters: on a virgin install every new file is
attributable to the game, which makes the diff trivially readable.

## Steps

**1. Copy this repo to the target PC.** Only `tools/` is strictly needed.

**2. If the install path differs, point the tool at it:**

```
set UPGRADEDEDEN_GAME_DIR=D:\SteamLibrary\steamapps\common\ANOTHER EDEN
```

**3. Let Steam finish any pending update FIRST.** An update mid-run writes
thousands of files and ruins the diff. Confirm Steam shows *Play*, not *Update*.

**4. Baseline, before the very first launch:**

```
py tools\snapshot.py before
```

**5. Launch the game.** Let it reach the verify/download screen and run for
**3-5 minutes**. Do *not* wait for it to finish - that is the ~3.5 hour path
this project exists to eliminate. A few minutes writes enough to reveal the
layout.

**6. Quit completely.** Confirm `AnotherEden.exe` is gone from Task Manager -
the updater may flush its state on exit.

**7. Capture and diff:**

```
py tools\snapshot.py after
py tools\diff_snapshot.py before after > discovery.txt
```

**8. Send back `discovery.txt`**, plus any files it lists under
*LIKELY UPDATER STATE FILES* (they are small JSON).

## What the diff reports

- **NEW DIRECTORIES** - collapsed to the shallowest new roots. The storage path
  should be obvious here; `<install>\contents*` is the working hypothesis,
  since the game's own uninstall script deletes `$install_dir_path\contents*`.
- **NEW FILES** - grouped by directory with counts and sizes, so the asset tree
  is visible at a glance.
- **MODIFIED FILES** - existing files the updater rewrote.
- **LIKELY UPDATER STATE FILES** - anything named `*manifest*`, `*.temp*`,
  `*version*` or `*.json*`. This is the payload we actually need.

## Caveat

Quitting mid-download means we see the **temp** manifest but probably not the
final `project.manifest` that `updateSucceed()` writes on phase completion. The
temp manifest carries the per-asset download states, which is normally what a
pre-seeder needs to forge. If it turns out the completion state is also
required, a second run that finishes one small phase will cover it.
