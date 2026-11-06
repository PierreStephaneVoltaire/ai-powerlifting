import glob
import hashlib
import logging
import os
import threading
from typing import Optional

import pandas as pd

from services.lib.aws import client as aws_client

logger = logging.getLogger(__name__)

SANDBOX_PATH = os.getenv("SANDBOX_PATH", "/tmp/sandbox")
DATASET_PREFIX = "datasets/openpowerlifting-"
CHUNK_ROWS = 250_000

TEXT_COLUMNS = ["Name"]
CATEGORY_COLUMNS = ["Federation", "MeetCountry", "State", "Equipment", "Sex", "AgeClass", "Event"]
FLOAT_COLUMNS = ["Best3SquatKg", "Best3BenchKg", "Best3DeadliftKg", "TotalKg", "Dots", "Age", "BodyweightKg"]
DATE_COLUMN = "Date"


class DatasetNotReadyError(Exception):
    pass


_lock = threading.Lock()
_ready = threading.Event()
_loading: Optional[threading.Thread] = None
_frame: Optional[pd.DataFrame] = None
_identity: Optional[str] = None
_error: Optional[BaseException] = None


def _pattern() -> str:
    return os.path.join(SANDBOX_PATH, "openpowerlifting-*.csv")


def ensure_downloaded() -> None:
    if glob.glob(_pattern()):
        return
    bucket = os.environ.get("POWERLIFTING_S3_BUCKET", "")
    if not bucket:
        return
    s3 = aws_client("s3", region_name=os.environ.get("AWS_REGION", "ca-central-1"))
    os.makedirs(SANDBOX_PATH, exist_ok=True)
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=DATASET_PREFIX):
        for obj in page.get("Contents", []) or []:
            key = obj["Key"]
            if not key.endswith(".csv"):
                continue
            destination = os.path.join(SANDBOX_PATH, os.path.basename(key))
            if os.path.isfile(destination) and os.path.getsize(destination) == obj.get("Size", 0):
                continue
            logger.info("Downloading s3://%s/%s", bucket, key)
            s3.download_file(bucket, key, destination)


def _read(path: str) -> pd.DataFrame:
    wanted = set(TEXT_COLUMNS + CATEGORY_COLUMNS + FLOAT_COLUMNS + [DATE_COLUMN])
    parts = []
    for chunk in pd.read_csv(
        path,
        usecols=lambda column: column in wanted,
        dtype={**{column: "str" for column in TEXT_COLUMNS + CATEGORY_COLUMNS}, **{column: "float32" for column in FLOAT_COLUMNS}},
        chunksize=CHUNK_ROWS,
    ):
        if DATE_COLUMN in chunk.columns:
            chunk["Year"] = pd.to_datetime(chunk.pop(DATE_COLUMN), errors="coerce").dt.year.astype("float32")
        parts.append(chunk)
    return pd.concat(parts, ignore_index=True)


def _files_identity(paths: list[str]) -> str:
    stats = [f"{os.path.basename(path)}:{os.path.getsize(path)}:{int(os.path.getmtime(path))}" for path in paths]
    return hashlib.sha256("|".join(stats).encode()).hexdigest()[:16]


def parse() -> pd.DataFrame:
    ensure_downloaded()
    paths = sorted(glob.glob(_pattern()))
    if not paths:
        raise FileNotFoundError(f"No powerlifting datasets found in sandbox matching: {_pattern()}")
    frame = pd.concat([_read(path) for path in paths], ignore_index=True)
    for column in CATEGORY_COLUMNS:
        if column in frame.columns:
            frame[column] = frame[column].astype("category")
    return frame


def _load() -> None:
    global _frame, _error, _identity
    try:
        frame = parse()
        identity = _files_identity(sorted(glob.glob(_pattern())))
    except BaseException as exc:
        logger.exception("OpenPowerlifting dataset load failed")
        with _lock:
            _error = exc
        _ready.set()
        return
    with _lock:
        _frame = frame
        _identity = identity
        _error = None
    logger.info("OpenPowerlifting dataset ready: %s rows", f"{len(frame):,}")
    _ready.set()


def warm_cache() -> None:
    global _loading, _error
    with _lock:
        if _frame is not None or (_loading is not None and _loading.is_alive()):
            return
        _error = None
        _ready.clear()
        _loading = threading.Thread(target=_load, daemon=True, name="opl-dataset")
        _loading.start()


def load_data(block: bool = False) -> pd.DataFrame:
    if _frame is not None:
        return _frame
    if _error is None or not isinstance(_error, FileNotFoundError):
        warm_cache()
    if block:
        _ready.wait()
    if _frame is not None:
        return _frame
    if isinstance(_error, FileNotFoundError):
        raise _error
    if _error is not None:
        raise DatasetNotReadyError(f"The dataset failed to load: {_error}")
    raise DatasetNotReadyError("The dataset is still loading in the background. Try again in a moment.")


def identity() -> str:
    load_data(block=True)
    return _identity or ""
