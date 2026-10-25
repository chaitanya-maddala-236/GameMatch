from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from gamematch.settings import RAW_DIR

SOURCES = {
    "australian_users_items.json.gz": "https://mcauleylab.ucsd.edu/public_datasets/data/steam/australian_users_items.json.gz",
    "steam_games.json.gz": "https://mcauleylab.ucsd.edu/public_datasets/data/steam/steam_games.json.gz",
    "australian_user_reviews.json.gz": "https://mcauleylab.ucsd.edu/public_datasets/data/steam/australian_user_reviews.json.gz",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = Request(url, headers={"User-Agent": "GameMatch/1.0 dataset downloader"})
    with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
        while block := response.read(1024 * 1024):
            output.write(block)
    temporary.replace(destination)


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "source": "UCSD/McAuley Recommender Systems Datasets — Steam Video Game and Bundle Data",
        "downloaded_at_utc": datetime.now(UTC).isoformat(),
        "files": {},
    }
    for name, url in SOURCES.items():
        destination = RAW_DIR / name
        if not destination.exists() or destination.stat().st_size == 0:
            print(f"Downloading {name} from the UCSD-hosted source")
            download(url, destination)
        manifest["files"][name] = {
            "url": url,
            "size_bytes": destination.stat().st_size,
            "sha256": sha256_file(destination),
        }
        print(f"Verified {name}: {destination.stat().st_size:,} bytes")
    (RAW_DIR / "download_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
