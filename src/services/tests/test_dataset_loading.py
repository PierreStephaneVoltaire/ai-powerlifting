import importlib
from pathlib import Path

import pytest

from services.lib import opl_dataset


class FakeS3:
    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, **kwargs):
        assert kwargs["Bucket"] == "powerlifting-data"
        assert kwargs["Prefix"] == "datasets/openpowerlifting-"
        return [{"Contents": [{"Key": "datasets/openpowerlifting-current.csv", "Size": 4}]}]

    def download_file(self, bucket, key, destination):
        assert bucket == "powerlifting-data"
        assert key.endswith("openpowerlifting-current.csv")
        Path(destination).write_text("data")


CSV = (
    "Name,Sex,Event,Equipment,Age,AgeClass,BodyweightKg,Best3SquatKg,Best3BenchKg,Best3DeadliftKg,TotalKg,Dots,Federation,Date,MeetCountry,State,Unused\n"
    "A Lifter,M,SBD,Raw,30,24-34,82.5,200,140,240,580,390.1,WRPF,2025-05-01,Canada,ON,x\n"
    "B Lifter,F,SBD,Raw,28,24-34,63,130,75,160,365,380.2,CPU,2024-03-02,Canada,QC,y\n"
    "C Lifter,M,B,Raw,40,40-44,100,,180,,180,110.5,USAPL,2023-07-09,USA,TX,z\n"
)


@pytest.fixture
def fresh_dataset(monkeypatch, tmp_path):
    monkeypatch.setattr(opl_dataset, "SANDBOX_PATH", str(tmp_path))
    monkeypatch.setattr(opl_dataset, "_frame", None)
    monkeypatch.setattr(opl_dataset, "_error", None)
    monkeypatch.setattr(opl_dataset, "_loading", None)
    opl_dataset._ready.clear()
    return tmp_path


def test_dataset_downloads_openpowerlifting_from_s3(monkeypatch, fresh_dataset):
    monkeypatch.setenv("POWERLIFTING_S3_BUCKET", "powerlifting-data")
    monkeypatch.setattr(opl_dataset, "aws_client", lambda *args, **kwargs: FakeS3())
    opl_dataset.ensure_downloaded()
    assert list(fresh_dataset.glob("openpowerlifting-*.csv"))


def test_dataset_parses_needed_columns_with_year_and_categories(monkeypatch, fresh_dataset):
    monkeypatch.delenv("POWERLIFTING_S3_BUCKET", raising=False)
    monkeypatch.setattr(opl_dataset, "CHUNK_ROWS", 2)
    (fresh_dataset / "openpowerlifting-current.csv").write_text(CSV)
    frame = opl_dataset.parse()
    assert len(frame) == 3
    assert "Unused" not in frame.columns and "Date" not in frame.columns
    assert frame["Year"].tolist() == [2025.0, 2024.0, 2023.0]
    assert str(frame["Federation"].dtype) == "category"
    assert sorted(frame["Federation"].cat.categories) == ["CPU", "USAPL", "WRPF"]
    assert str(frame["TotalKg"].dtype) == "float32"


def test_all_ranking_features_share_one_loaded_dataset(monkeypatch, fresh_dataset):
    monkeypatch.delenv("POWERLIFTING_S3_BUCKET", raising=False)
    (fresh_dataset / "openpowerlifting-current.csv").write_text(CSV)
    percentile = importlib.import_module("services.handlers.analysis.powerlifting_ranking_percentile.core")
    categories = importlib.import_module("services.handlers.analysis.powerlifting_filter_categories.core")
    stats = importlib.import_module("services.handlers.analysis.analyze_powerlifting_stats.core")
    frame = percentile.load_data()
    assert categories.load_data() is frame
    assert stats.load_data() is frame
    assert "WRPF" in categories.get_filter_categories(frame)["federations"]


def test_missing_dataset_is_reported_as_not_found(monkeypatch, fresh_dataset):
    monkeypatch.delenv("POWERLIFTING_S3_BUCKET", raising=False)
    with pytest.raises(FileNotFoundError):
        opl_dataset.load_data(block=True)
