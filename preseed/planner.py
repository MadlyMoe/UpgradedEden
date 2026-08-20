"""Work out which assets actually need downloading.

An asset is already satisfied if its md5 matches either
  (a) what Steam shipped, per bundled.manifest, or
  (b) something already verified into our local mirror.
Planning therefore needs no hashing of the 13.6 GB install at all.
"""
import json
import os

from . import config, manifest

INDEX_PATH = os.path.join(config.MIRROR_DIR, "index.json")


def load_mirror_index():
    if not os.path.exists(INDEX_PATH):
        return {}
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def save_mirror_index(idx):
    config.ensure_dirs()
    tmp = INDEX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(idx, fh)
    os.replace(tmp, INDEX_PATH)


def mirror_path(asset):
    return os.path.join(config.MIRROR_DIR, asset.path.replace("/", os.sep))


class Plan:
    def __init__(self):
        self.needed = []        # list[Asset]
        self.have_bundled = 0
        self.have_mirror = 0
        self.phases = []
        self.package_url = ""
        self.conflicts = 0      # same key, different md5 across phases

    @property
    def needed_bytes(self):
        return sum(a.size for a in self.needed)


def build_plan(phase_numbers=None, force_refresh=False, verbose=True):
    bundled = manifest.load_bundled()
    bundled_md5 = {k: a.md5 for k, a in bundled.items()}
    mirror = load_mirror_index()

    phases = manifest.load_phase_manifests()
    if phase_numbers:
        phases = [p for p in phases if p["phase"] in phase_numbers]

    plan = Plan()
    plan.phases = [p["phase"] for p in phases]
    if phases:
        plan.package_url = phases[0]["package_url"]

    seen = {}
    for p in phases:
        if not p["manifest_url"]:
            continue
        assets, cached = manifest.fetch_project_manifest(
            p["phase"], p["manifest_url"], force=force_refresh)
        if verbose:
            tag = "cached" if cached else "fetched"
            print(f"  phase {p['phase']:>2}: {len(assets):>7,} assets ({tag})")
        for key, a in assets.items():
            prev = seen.get(key)
            if prev is None:
                seen[key] = a
            elif prev.md5 != a.md5:
                plan.conflicts += 1

    for key, a in seen.items():
        if bundled_md5.get(key) == a.md5:
            plan.have_bundled += 1
            continue
        m = mirror.get(key)
        if m and m.get("md5") == a.md5 and os.path.exists(mirror_path(a)):
            plan.have_mirror += 1
            continue
        plan.needed.append(a)

    plan.needed.sort(key=lambda a: a.size)   # small files first: fastest feedback
    return plan


def describe(plan):
    total = len(plan.needed) + plan.have_bundled + plan.have_mirror
    gb = plan.needed_bytes / 2 ** 30
    mb = plan.needed_bytes / 2 ** 20
    size = f"{gb:.2f} GB" if gb >= 1 else f"{mb:.1f} MB"
    lines = [
        f"phases            : {', '.join(str(p) for p in plan.phases)}",
        f"unique assets     : {total:,}",
        f"  already shipped : {plan.have_bundled:,}",
        f"  already mirrored: {plan.have_mirror:,}",
        f"  NEED DOWNLOAD   : {len(plan.needed):,}  ({size})",
    ]
    if plan.conflicts:
        lines.append(f"  md5 conflicts across phases: {plan.conflicts:,}")
    if plan.needed:
        avg = plan.needed_bytes / len(plan.needed) / 1024
        lines.append(f"  average file size : {avg:.1f} KB")
        # Two independent limits: per-request round trips, and raw bandwidth.
        # Whichever is larger governs. Large assets are bandwidth-bound.
        link_mbps = float(os.environ.get("UPGRADEDEDEN_LINK_MBPS", "50"))
        bw_secs = plan.needed_bytes * 8 / (link_mbps * 1e6)
        for rate in (49, 85, 139):
            lat_secs = len(plan.needed) / rate
            secs = max(lat_secs, bw_secs)
            bound = "latency" if lat_secs >= bw_secs else "bandwidth"
            lines.append(f"  est @ {rate:>3} files/s : {secs/60:>6.1f} min  ({bound}-bound)")
        lines.append(f"  (bandwidth assumption: {link_mbps:.0f} Mbps;"
                     f" set UPGRADEDEDEN_LINK_MBPS to change)")
    return "\n".join(lines)
