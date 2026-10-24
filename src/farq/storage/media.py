from pathlib import Path
from typing import BinaryIO, Protocol

import boto3
from botocore.exceptions import ClientError

from farq.settings import Settings


class MediaStore(Protocol):
    def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None: ...

    def download(self, key: str, path: Path) -> None: ...


class S3MediaStore:
    """Media files in any S3-compatible store (SeaweedFS locally)."""

    def __init__(self, client, bucket: str):
        self._client = client
        self.bucket = bucket

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3MediaStore":
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            region_name="us-east-1",
        )
        return cls(client, settings.s3_bucket)

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        self._client.upload_fileobj(
            fileobj, self.bucket, key, ExtraArgs={"ContentType": content_type}
        )

    def download(self, key: str, path: Path) -> None:
        self._client.download_file(self.bucket, key, str(path))
