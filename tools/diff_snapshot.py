"""Diff two filesystem snapshots to locate the game's asset storage path.

Usage:
    py tools/diff_snapshot.py before after
"""
import os
import sys
from collections import defaultdict

SNAP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "snapshots")


def load(label):
    path = os.path.join(SNAP_DIR, f"{label}.tsv")
    files, dirs = {}, set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            kind, size, mtime, p = line.rstrip("\n").split("\t", 3)
            if kind == "D":
                dirs.add(p)
            else:
                files[p] = (int(size), int(mtime))
    return files, dirs


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:,.1f} TB"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    a, b = sys.argv[1], sys.argv[2]
    fa, da = load(a)
    fb, db = load(b)

    new_dirs = sorted(db - da)
    new_files = {p: v for p, v in fb.items() if p not in fa}
    changed = {p: (fa[p], fb[p]) for p in fb if p in fa and fa[p] != fb[p]}
    deleted = sorted(p for p in fa if p not in fb)

    print(f"=== NEW DIRECTORIES ({len(new_dirs):,}) ===")
    # collapse: show only shallowest new dirs, they imply their children
    roots = []
    for d in new_dirs:
        if not any(d.startswith(r + os.sep) for r in roots):
            roots.append(d)
    for d in roots[:60]:
        print(f"  {d}")
    if len(roots) > 60:
        print(f"  ... and {len(roots)-60:,} more")

    print(f"\n=== NEW FILES ({len(new_files):,}, {human(sum(s for s, _ in new_files.values()))}) ===")
    by_dir = defaultdict(lambda: [0, 0])
    for p, (s, _) in new_files.items():
        e = by_dir[os.path.dirname(p)]
        e[0] += 1
        e[1] += s
    for d, (n, sz) in sorted(by_dir.items(), key=lambda kv: -kv[1][0])[:40]:
        print(f"  {n:>8,} files  {human(sz):>12}  {d}")
    if len(by_dir) > 40:
        print(f"  ... and {len(by_dir)-40:,} more directories")

    print(f"\n=== MODIFIED FILES ({len(changed):,}) ===")
    for p, ((s1, _), (s2, _)) in sorted(changed.items())[:40]:
        print(f"  {human(s1):>12} -> {human(s2):>12}  {p}")
    if len(changed) > 40:
        print(f"  ... and {len(changed)-40:,} more")

    print(f"\n=== DELETED ({len(deleted):,}) ===")
    for p in deleted[:20]:
        print(f"  {p}")
    if len(deleted) > 20:
        print(f"  ... and {len(deleted)-20:,} more")

    # the interesting bit: state files
    print("\n=== LIKELY UPDATER STATE FILES ===")
    keys = ("manifest", ".temp", "version", ".json")
    hits = [p for p in list(new_files) + list(changed)
            if any(k in os.path.basename(p).lower() for k in keys)]
    for p in sorted(hits)[:40]:
        tag = "NEW" if p in new_files else "MOD"
        size = new_files[p][0] if p in new_files else changed[p][1][0]
        print(f"  [{tag}] {human(size):>12}  {p}")
    if not hits:
        print("  (none found)")


if __name__ == "__main__":
    main()
