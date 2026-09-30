"""Private S3 model archives, shared by the API and isolated training workers."""

import os
import tarfile
import tempfile
from pathlib import Path

import boto3
from botocore.config import Config


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required for reward-model artifacts")
    return value


def client():
    return boto3.client(
        "s3",
        endpoint_url=required("S3_ENDPOINT"),
        aws_access_key_id=required("S3_ACCESS_KEY"),
        aws_secret_access_key=required("S3_SECRET_KEY"),
        region_name=required("S3_REGION"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def upload_model(model_dir: Path, key: str) -> None:
    # Disk and multipart transfer keep a multi-GB checkpoint out of process memory.
    with tempfile.TemporaryDirectory() as temp:
        archive = Path(temp) / "reward-model.tar.gz"
        with tarfile.open(archive, "w:gz", compresslevel=1) as tar:
            tar.add(model_dir, arcname="reward-model")
        client().upload_file(str(archive), required("S3_BUCKET"), key)


def download_model(key: str, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        archive = Path(temp) / "reward-model.tar.gz"
        client().download_file(required("S3_BUCKET"), key, str(archive))
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(destination, filter="data")
    return destination / "reward-model"


def download_url(key: str, filename: str) -> str:
    return client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": required("S3_BUCKET"),
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
            "ResponseContentType": "application/gzip",
        },
        ExpiresIn=300,
    )
