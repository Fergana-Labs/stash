"""A checkpoint remains usable when the machine that trained it is gone."""

import io
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

        def get_object(self, *, Bucket, Key):
            class Body(io.BytesIO):
                def iter_chunks(self, chunk_size):
                    while chunk := self.read(chunk_size):
                        yield chunk

            body = Body(objects[(Bucket, Key)])
            bodies.append(body)
            return {"Body": body}

    bodies = []
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
        b"".join(artifacts.stream_model("owner/model.tar.gz"))
        == objects[("private-models", "owner/model.tar.gz")]
    )
    assert bodies[0].closed
