from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

from .paths import DATA_DIR

REPOSITORY = "julilili42/search-engine"
REQUIRED_ASSET_NAMES = ("pages.sqlite", "index.bin")
OPTIONAL_ASSET_NAMES = ("embeddings.npz",)


def _release_url(tag: str | None) -> str:
    suffix = "latest" if tag is None else f"tags/{quote(tag, safe='')}"
    return f"https://api.github.com/repos/{REPOSITORY}/releases/{suffix}"


def _asset_urls(release: dict) -> dict[str, str]:
    assets = {
        asset["name"]: asset["browser_download_url"]
        for asset in release.get("assets", [])
        if asset.get("name") in REQUIRED_ASSET_NAMES + OPTIONAL_ASSET_NAMES
    }
    missing = set(REQUIRED_ASSET_NAMES) - assets.keys()
    if missing:
        raise ValueError(f"Release is missing: {', '.join(sorted(missing))}")
    return assets


def _download(url: str, destination: Path) -> None:
    temporary = destination.with_name(destination.name + ".tmp")
    with urlopen(url) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output)
    temporary.replace(destination)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Download crawl data from GitHub Releases")
    parser.add_argument("--release", help="release tag; defaults to the latest release")
    args = parser.parse_args(argv)

    try:
        with urlopen(_release_url(args.release)) as response:
            release = json.load(response)
        assets = _asset_urls(release)
    except HTTPError as exc:
        parser.error(f"Could not fetch release: {exc}")
    except ValueError as exc:
        parser.error(str(exc))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_ASSET_NAMES + OPTIONAL_ASSET_NAMES:
        if name not in assets:
            continue
        print(f"Downloading {name}...")
        _download(assets[name], DATA_DIR / name)
