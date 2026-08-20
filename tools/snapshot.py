"""Filesystem snapshot tool.

Captures path/size/mtime for the roots Another Eden could plausibly write to,
so a before/after diff reveals where AssetsManagerEx stores downloaded assets
and its manifest state files.

Usage:
    py tools/snapshot.py before
    py tools/snapshot.py after
"""
import os
import sys
import time
import json

GAME_DIR = os.environ.get(
    "UPGRADEDEDEN_GAME_DIR",
    r"C:\Main\Gaming\Steam\steamapps\common\ANOTHER EDEN",
)

# (root, max_depth)  depth None == unlimited
ROOTS = [
    (GAME_DIR, None),
    (os.environ.get("LOCALAPPDATA", ""), 2),
    (os.environ.get("APPDATA", ""), 2),
    (os.path.join(os.environ.get("USERPROFILE", ""), "Documents"), 2),
    (r"C:\ProgramData", 2),
    (os.environ.get("TEMP", ""), 1),
    (r"C:\Windows\wfsdrv", None),
    (r"C:\Main\Gaming\Steam\steamapps\downloading", 2),
]


def walk(root, max_depth):
    """Yield (path, size, mtime_ns, is_dir). Depth-limited, error tolerant."""
    root = os.path.abspath(root)
    base_depth = root.rstrip(r"\/").count(os.sep)
    stack = [root]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    try:
                        depth = cur.count(os.sep) - base_depth + 1
                        if e.is_dir(follow_symlinks=False):
                            yield (e.path, -1, 0, True)
                            if max_depth is None or depth < max_depth:
                                stack.append(e.path)
                        else:
                            st = e.stat(follow_symlinks=False)
                            yield (e.path, st.st_size, st.st_mtime_ns, False)
                    except OSError:
                        continue
        except OSError:
            continue


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    label = sys.argv[1]
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "snapshots")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{label}.tsv")

    total = 0
    started = time.time()
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"# snapshot label={label} taken={time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        for root, depth in ROOTS:
            if not root or not os.path.exists(root):
                fh.write(f"# MISSING\t{root}\n")
                continue
            n = 0
            for path, size, mtime, is_dir in walk(root, depth):
                kind = "D" if is_dir else "F"
                fh.write(f"{kind}\t{size}\t{mtime}\t{path}\n")
                n += 1
            total += n
            print(f"  {root}  ->  {n:,} entries")

    meta = {"label": label, "taken": time.time(), "entries": total,
            "roots": [r for r, _ in ROOTS]}
    with open(os.path.join(out_dir, f"{label}.meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)

    print(f"\n{total:,} entries in {time.time()-started:.1f}s -> {out_path}")


if __name__ == "__main__":
    main()
