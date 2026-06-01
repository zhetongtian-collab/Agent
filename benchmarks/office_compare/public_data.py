from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tarfile
import tempfile
from urllib import request
import zipfile


OFFICEBENCH_URL = "https://codeload.github.com/zlwang-cs/OfficeBench/zip/refs/heads/main"
SPREADSHEETBENCH_URL = (
    "https://huggingface.co/datasets/KAKA22/SpreadsheetBench/resolve/main/"
    "spreadsheetbench_verified_400.tar.gz?download=true"
)


@dataclass(frozen=True)
class PublicDataRoots:
    officebench: Path
    spreadsheetbench: Path


def default_cache_root() -> Path:
    return Path(tempfile.gettempdir()) / "longchain-public-benchmarks"


def prepare_public_data(cache_root: Path | None = None) -> PublicDataRoots:
    root = (cache_root or default_cache_root()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    office_root = root / "OfficeBench-main"
    spreadsheet_root = root / "spreadsheetbench_verified_400" / "spreadsheetbench_verified_400"
    if not office_root.exists():
        office_archive = root / "OfficeBench-main.zip"
        _download(OFFICEBENCH_URL, office_archive)
        _extract_zip(office_archive, root)
    if not spreadsheet_root.exists():
        spreadsheet_archive = root / "spreadsheetbench_verified_400.tar.gz"
        spreadsheet_target = root / "spreadsheetbench_verified_400"
        _download(SPREADSHEETBENCH_URL, spreadsheet_archive)
        spreadsheet_target.mkdir(parents=True, exist_ok=True)
        _extract_tar(spreadsheet_archive, spreadsheet_target)
    return PublicDataRoots(officebench=office_root, spreadsheetbench=spreadsheet_root)


def _download(url: str, target: Path) -> None:
    if target.exists():
        return
    print(f"Downloading {url}", flush=True)
    request.urlretrieve(url, target)


def _extract_zip(archive: Path, target: Path) -> None:
    with zipfile.ZipFile(archive) as payload:
        _validate_members(target, [item.filename for item in payload.infolist()])
        payload.extractall(target)


def _extract_tar(archive: Path, target: Path) -> None:
    with tarfile.open(archive, "r:gz") as payload:
        _validate_members(target, [item.name for item in payload.getmembers()])
        payload.extractall(target, filter="data")


def _validate_members(target: Path, names: list[str]) -> None:
    resolved_target = target.resolve()
    for name in names:
        resolved_member = (target / name).resolve()
        if resolved_member != resolved_target and resolved_target not in resolved_member.parents:
            raise RuntimeError(f"Refusing to extract path outside cache: {name}")
