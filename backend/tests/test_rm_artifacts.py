"""A checkpoint remains usable when the machine that trained it is gone."""

import shutil
from pathlib import Path

from rm_worker import artifacts


def test_checkpoint_round_trip_across_workers(tmp_path, monkeypatch):
    objects = {}

    class Store:
        def upload_file(self, path, bucket, key):
            objects[(bucket, key)] = Path(path).read_bytes()

        def download_file(self, bucket, key, path):
            Path(path).write_bytes(objects[(bucket, key)])

        def generate_presigned_url(self, operation, *, Params, ExpiresIn):
            assert operation == "get_object" and ExpiresIn == 300
            assert Params["Bucket"] == "private-models"
            assert Params["Key"] == "owner/model.tar.gz"
            assert Params["ResponseContentDisposition"] == 'attachment; filename="model.tar.gz"'
            return "https://storage.example/temporary-download"

    monkeypatch.setattr(artifacts, "client", Store)
    monkeypatch.setenv("S3_BUCKET", "private-models")
    training = tmp_path / "training" / "model"
    training.mkdir(parents=True)
    (training / "model.safetensors").write_bytes(b"weights")
    (training / "reward_stats.json").write_text('{"mean": 0, "std": 1}')
    artifacts.upload_model(training, "owner/model.tar.gz")
    shutil.rmtree(training.parent)
    inference = artifacts.download_model("owner/model.tar.gz", tmp_path / "inference")
    assert (inference / "model.safetensors").read_bytes() == b"weights"
    assert (inference / "reward_stats.json").is_file()
    assert (
        artifacts.download_url("owner/model.tar.gz", "model.tar.gz")
        == "https://storage.example/temporary-download"
    )
