#!/usr/bin/env python3
"""UpgradedEden asset pre-seeder.

Another Eden's in-game updater fetches assets one HTTP request at a time from a
CDN whose objects are not retained at the edge, so each distinct file costs a
~470 ms round trip to the S3 origin. This tool does the same work concurrently.

Commands:
    py preseed.py plan   [--phases 1,2] [--refresh]
    py preseed.py fetch  [--phases 1] [--concurrency 64] [--limit N]
    py preseed.py status
    py preseed.py verify
"""
import argparse
import hashlib
import os
import sys

from preseed import config, fetch, manifest, planner


def _phases(arg):
    if not arg:
        return None
    return [int(x) for x in arg.replace(" ", "").split(",") if x]


def cmd_plan(args):
    print("Reading manifests...")
    plan = planner.build_plan(_phases(args.phases), force_refresh=args.refresh)
    print()
    print(planner.describe(plan))
    return 0


def cmd_fetch(args):
    print("Reading manifests...")
    plan = planner.build_plan(_phases(args.phases), force_refresh=args.refresh)
    print()
    print(planner.describe(plan))
    if not plan.needed:
        print("\nNothing to download.")
        return 0
    if args.limit:
        plan.needed = plan.needed[:args.limit]
        print(f"\n(limited to {len(plan.needed):,} files for this run)")
    print(f"\nDownloading with concurrency {args.concurrency or config.CONCURRENCY}...")
    ok, failures = fetch.run(plan, concurrency=args.concurrency)
    print(f"\n  succeeded: {ok:,}")
    print(f"  failed   : {len(failures):,}")
    for asset, err in failures[:15]:
        print(f"    {asset.key}: {err}")
    if len(failures) > 15:
        print(f"    ... and {len(failures)-15:,} more")
    return 1 if failures else 0


def cmd_status(args):
    idx = planner.load_mirror_index()
    total = sum(v.get("size", 0) for v in idx.values())
    print(f"mirror dir    : {config.MIRROR_DIR}")
    print(f"indexed assets: {len(idx):,}")
    print(f"indexed bytes : {total/2**30:.2f} GB")
    on_disk = 0
    for root, _dirs, files in os.walk(config.MIRROR_DIR):
        on_disk += len([f for f in files if not f.endswith((".part", ".json"))])
    print(f"files on disk : {on_disk:,}")
    return 0


def cmd_verify(args):
    idx = planner.load_mirror_index()
    if not idx:
        print("mirror index is empty")
        return 0
    bad, missing, ok = [], [], 0
    for i, (key, meta) in enumerate(idx.items(), 1):
        p = os.path.join(config.MIRROR_DIR, meta["path"].replace("/", os.sep))
        if not os.path.exists(p):
            missing.append(key)
            continue
        with open(p, "rb") as fh:
            if hashlib.md5(fh.read()).hexdigest() == meta["md5"]:
                ok += 1
            else:
                bad.append(key)
        if i % 500 == 0:
            sys.stdout.write(f"\r  verified {i:,}/{len(idx):,}   ")
            sys.stdout.flush()
    print(f"\r  ok {ok:,}   bad {len(bad):,}   missing {len(missing):,}          ")
    for k in (bad + missing)[:15]:
        print(f"    {k}")
    return 1 if (bad or missing) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan");  p.set_defaults(fn=cmd_plan)
    p.add_argument("--phases"); p.add_argument("--refresh", action="store_true")

    f = sub.add_parser("fetch"); f.set_defaults(fn=cmd_fetch)
    f.add_argument("--phases"); f.add_argument("--refresh", action="store_true")
    f.add_argument("--concurrency", type=int); f.add_argument("--limit", type=int)

    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    v = sub.add_parser("verify"); v.set_defaults(fn=cmd_verify)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
