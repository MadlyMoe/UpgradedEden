"""Reading the game's local manifests and fetching the live remote ones."""
import json
import os

from . import config, net


class Asset:
    __slots__ = ("key", "md5", "path", "size")

    def __init__(self, key, md5, path, size):
        self.key = key
        self.md5 = md5
        self.path = path
        self.size = size

    def url(self, package_url):
        return f"{package_url.rstrip('/')}/{self.path}"

    def __repr__(self):
        return f"<Asset {self.key} {self.size}B>"


def _parse_assets(obj):
    """{key: {md5, path, size}} -> {key: Asset}"""
    out = {}
    for key, v in (obj.get("assets") or {}).items():
        try:
            out[key] = Asset(key, v["md5"], v["path"], int(v["size"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def load_phase_manifests():
    """Read phase.manifest.1..N from the game install."""
    phases = []
    for n in range(1, config.PHASE_COUNT + 1):
        p = os.path.join(config.BUNDLED_DIR, f"phase.manifest.{n}")
        if not os.path.exists(p):
            continue
        try:
            obj = load_json(p)
        except (OSError, json.JSONDecodeError) as e:
            print(f"  ! phase {n}: {e}")
            continue
        phases.append({
            "phase": n,
            "package_url": obj.get("packageUrl", ""),
            "manifest_url": obj.get("remoteManifestUrl", ""),
            "version_url": obj.get("remoteVersionUrl", ""),
            "declared_size": int(obj.get("size", 0) or 0),
            "version": obj.get("version", ""),
        })
    return phases


def load_bundled():
    """Assets Steam shipped. Authoritative for what is already on disk."""
    if not os.path.exists(config.BUNDLED_MANIFEST):
        raise FileNotFoundError(config.BUNDLED_MANIFEST)
    return _parse_assets(load_json(config.BUNDLED_MANIFEST))


def fetch_project_manifest(phase, url, force=False):
    """Download (and cache) a phase's live project manifest."""
    config.ensure_dirs()
    cache = os.path.join(config.MANIFEST_CACHE, f"project.manifest.{phase}.json")
    if os.path.exists(cache) and not force:
        try:
            return _parse_assets(load_json(cache)), True
        except (OSError, json.JSONDecodeError):
            pass  # corrupt cache; refetch
    body = net.get(url)
    with open(cache, "wb") as fh:
        fh.write(body)
    return _parse_assets(json.loads(body.decode("utf-8-sig"))), False
