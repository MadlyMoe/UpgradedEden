"""Paths and constants for the pre-seeder."""
import os

# Steam install of ANOTHER EDEN. Override with UPGRADEDEDEN_GAME_DIR.
GAME_DIR = os.environ.get(
    "UPGRADEDEDEN_GAME_DIR",
    r"C:\Main\Gaming\Steam\steamapps\common\ANOTHER EDEN",
)

# Region/platform folder under manifests/bundled/.
# One of: windows, windows-ap, windows-eu, windows-us
REGION = os.environ.get("UPGRADEDEDEN_REGION", "windows-us")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
MANIFEST_CACHE = os.path.join(DATA_DIR, "manifests")
MIRROR_DIR = os.path.join(DATA_DIR, "mirror")
SNAPSHOT_DIR = os.path.join(DATA_DIR, "snapshots")

BUNDLED_DIR = os.path.join(GAME_DIR, "manifests", "bundled", REGION)
BUNDLED_MANIFEST = os.path.join(BUNDLED_DIR, "bundled.manifest")
GAME_FILES_DIR = os.path.join(GAME_DIR, "files")

# Phase manifests are phase.manifest.1 .. phase.manifest.16
PHASE_COUNT = 16

# Downloader tuning. 128 measured at ~85 files/s against the live CDN;
# 64 is the safer default for sustained runs.
CONCURRENCY = int(os.environ.get("UPGRADEDEDEN_CONCURRENCY", "64"))
TIMEOUT = 30
RETRIES = 3
USER_AGENT = "UpgradedEden-preseed/0.1"


def ensure_dirs():
    for d in (DATA_DIR, MANIFEST_CACHE, MIRROR_DIR, SNAPSHOT_DIR):
        os.makedirs(d, exist_ok=True)
