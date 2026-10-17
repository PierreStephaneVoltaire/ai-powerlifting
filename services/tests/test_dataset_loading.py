import importlib
from pathlib import Path


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


def test_analysis_dataset_loaders_download_openpowerlifting_from_s3(monkeypatch, tmp_path):
    monkeypatch.setenv("POWERLIFTING_S3_BUCKET", "powerlifting-data")
    for module_name in (
        "services.handlers.analysis.powerlifting_filter_categories.core",
        "services.handlers.analysis.powerlifting_ranking_percentile.core",
    ):
        module = importlib.import_module(module_name)
        monkeypatch.setattr(module, "SANDBOX_PATH", str(tmp_path / module_name.rsplit(".", 2)[-2]))
        monkeypatch.setattr(module, "aws_client", lambda *args, **kwargs: FakeS3(), raising=False)
        monkeypatch.setattr("services.lib.aws.client", lambda *args, **kwargs: FakeS3())
        module._ensure_dataset_downloaded()
        assert list(Path(module.SANDBOX_PATH).glob("openpowerlifting-*.csv"))
