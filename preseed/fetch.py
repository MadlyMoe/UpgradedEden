"""Concurrent asset downloader with per-file md5 verification."""
import hashlib
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config, net, planner


class Stats:
    def __init__(self, total_files, total_bytes):
        self.total_files = total_files
        self.total_bytes = total_bytes
        self.done = 0
        self.bytes = 0
        self.failed = 0
        self.bad_md5 = 0
        self.started = time.monotonic()
        self.lock = threading.Lock()

    def tick(self, nbytes=0, failed=False, bad=False):
        with self.lock:
            self.done += 1
            self.bytes += nbytes
            if failed:
                self.failed += 1
            if bad:
                self.bad_md5 += 1
            return self.done

    def line(self):
        el = max(time.monotonic() - self.started, 1e-6)
        rate = self.done / el
        remaining = (self.total_files - self.done) / rate if rate > 0 else 0
        pct = 100.0 * self.done / max(self.total_files, 1)
        return (f"\r  {self.done:>7,}/{self.total_files:,} ({pct:5.1f}%)  "
                f"{rate:6.1f} files/s  {self.bytes/2**20:8.1f} MB  "
                f"fail {self.failed}  eta {remaining/60:5.1f}m   ")


def _download_one(asset, package_url, stats):
    dest = planner.mirror_path(asset)
    if os.path.exists(dest):
        try:
            if os.path.getsize(dest) == asset.size:
                with open(dest, "rb") as fh:
                    if hashlib.md5(fh.read()).hexdigest() == asset.md5:
                        stats.tick(0)
                        return asset, True, None
        except OSError:
            pass

    url = asset.url(package_url)
    try:
        body = net.get(url)
    except Exception as e:
        stats.tick(0, failed=True)
        return asset, False, f"{type(e).__name__}: {e}"

    got = hashlib.md5(body).hexdigest()
    if got != asset.md5:
        stats.tick(len(body), failed=True, bad=True)
        return asset, False, f"md5 mismatch (want {asset.md5}, got {got})"

    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".part"
        with open(tmp, "wb") as fh:
            fh.write(body)
        os.replace(tmp, dest)
    except OSError as e:
        stats.tick(len(body), failed=True)
        return asset, False, f"write failed: {e}"

    stats.tick(len(body))
    return asset, True, None


def run(plan, concurrency=None, progress=True):
    """Download every asset in the plan. Returns (ok_count, failures)."""
    concurrency = concurrency or config.CONCURRENCY
    config.ensure_dirs()
    assets = plan.needed
    if not assets:
        return 0, []

    stats = Stats(len(assets), plan.needed_bytes)
    index = planner.load_mirror_index()
    idx_lock = threading.Lock()
    failures = []
    ok = 0
    last_save = time.monotonic()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futs = [pool.submit(_download_one, a, plan.package_url, stats)
                for a in assets]
        for fut in as_completed(futs):
            asset, good, err = fut.result()
            if good:
                ok += 1
                with idx_lock:
                    index[asset.key] = {"md5": asset.md5, "size": asset.size,
                                        "path": asset.path}
            else:
                failures.append((asset, err))
            if progress and stats.done % 25 == 0:
                sys.stdout.write(stats.line())
                sys.stdout.flush()
            now = time.monotonic()
            if now - last_save > 30:
                with idx_lock:
                    planner.save_mirror_index(index)
                last_save = now

    planner.save_mirror_index(index)
    if progress:
        sys.stdout.write(stats.line() + "\n")
    return ok, failures
