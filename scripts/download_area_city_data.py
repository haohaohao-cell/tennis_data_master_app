from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlretrieve

import py7zr


ROOT_DIR = Path(__file__).resolve().parents[1]
DOWNLOAD_URL = (
    "https://github.com/xiangyuecn/AreaCity-JsSpider-StatsGov/"
    "releases/download/2025.251231.260403/ok_geo.csv.7z"
)
DEFAULT_ARCHIVE_PATH = ROOT_DIR / "backend" / "data" / "ok_geo.csv.7z"
DEFAULT_TARGET_PATH = ROOT_DIR / "backend" / "data" / "area_city_ok_geo.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and extract AreaCity ok_geo.csv boundary data.")
    parser.add_argument("--archive", default=str(DEFAULT_ARCHIVE_PATH), help="Path to cache ok_geo.csv.7z.")
    parser.add_argument("--target", default=str(DEFAULT_TARGET_PATH), help="Path to write area_city_ok_geo.csv.")
    parser.add_argument("--force", action="store_true", help="Overwrite the target CSV when it already exists.")
    return parser.parse_args()


def download_archive(archive_path: Path) -> None:
    if archive_path.exists():
        print(f"Using existing archive: {archive_path}")
        return
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading AreaCity archive to {archive_path}")
    urlretrieve(DOWNLOAD_URL, archive_path)


def restore_windows_acl_inheritance(path: Path) -> None:
    if os.name != "nt":
        return

    try:
        subprocess.run(
            ["icacls", str(path), "/inheritance:e"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Warning: could not restore Windows ACL inheritance for {path}: {exc}")


def extract_csv(archive_path: Path, target_path: Path, *, force: bool) -> None:
    if target_path.exists() and not force:
        print(f"Target already exists: {target_path}")
        restore_windows_acl_inheritance(target_path)
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="area_city_extract_") as temp_dir:
        extract_dir = Path(temp_dir)
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            archive.extractall(path=extract_dir)

        candidates = list(extract_dir.rglob("ok_geo.csv"))
        if not candidates:
            raise RuntimeError("ok_geo.csv was not found inside the AreaCity archive.")

        shutil.move(str(candidates[0]), target_path)
    restore_windows_acl_inheritance(target_path)
    print(f"Wrote {target_path} ({target_path.stat().st_size} bytes)")


def main() -> None:
    args = parse_args()
    archive_path = Path(args.archive).resolve()
    target_path = Path(args.target).resolve()
    download_archive(archive_path)
    extract_csv(archive_path, target_path, force=args.force)


if __name__ == "__main__":
    main()
