#!/usr/bin/env python3
"""Upload RSE Seat metadata JSON files to DigitalOcean Spaces."""

import runpy
import sys
import urllib.request
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# Load root config.py
_root = runpy.run_path(str(Path(__file__).parent.parent / "config.py"))

DO_KEY      = _root["DO_SPACES_KEY"]
DO_SECRET   = _root["DO_SPACES_SECRET"]
DO_BUCKET   = _root["DO_SPACES_BUCKET"]
DO_REGION   = _root["DO_SPACES_REGION"]
DO_ENDPOINT = _root["DO_SPACES_ENDPOINT"]
DO_BASE_URL = _root["DO_SPACES_URL"]
S3_PREFIX   = _root["S3_PREFIX"].rstrip("/")   # "theservicesexchange"

METADATA_DIR   = Path(__file__).parent / "metadata"
SPACES_PREFIX  = f"{S3_PREFIX}/rse-seats"
PUBLIC_BASE    = f"{DO_BASE_URL}/{S3_PREFIX}/rse-seats"
IMAGE_URL      = f"{DO_BASE_URL}/{S3_PREFIX}/RSE.png"


def get_client():
    return boto3.client(
        "s3",
        aws_access_key_id=DO_KEY,
        aws_secret_access_key=DO_SECRET,
        endpoint_url=DO_ENDPOINT,
        region_name=DO_REGION,
    )


def upload_all(client) -> list[str]:
    files = sorted(METADATA_DIR.glob("*.json"), key=lambda p: int(p.stem))
    if not files:
        print(f"No JSON files found in {METADATA_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Uploading {len(files)} files to s3://{DO_BUCKET}/{SPACES_PREFIX}/")
    uploaded = []
    for path in files:
        key = f"{SPACES_PREFIX}/{path.name}"
        try:
            client.put_object(
                Bucket=DO_BUCKET,
                Key=key,
                Body=path.read_bytes(),
                ContentType="application/json",
                ACL="public-read",
            )
            uploaded.append(path.name)
        except ClientError as exc:
            print(f"  ERROR {path.name}: {exc}", file=sys.stderr)

    print(f"Uploaded {len(uploaded)} files.")
    return uploaded


def verify_url(url: str, label: str):
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            import json
            body = resp.read()
            json.loads(body)
            print(f"  OK  {label}: {url}")
    except Exception as exc:
        print(f"  FAIL {label}: {url} — {exc}", file=sys.stderr)


def verify_image(url: str):
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            print(f"  OK  seat image ({status}): {url}")
    except Exception as exc:
        print(f"  FAIL seat image: {url} — {exc}", file=sys.stderr)


def main():
    if not METADATA_DIR.exists():
        print(f"metadata/ directory not found. Run generate_metadata.py first.", file=sys.stderr)
        sys.exit(1)

    client = get_client()
    uploaded = upload_all(client)

    if not uploaded:
        sys.exit(1)

    print("\nVerifying uploads...")
    first = uploaded[0]
    last = uploaded[-1]
    verify_url(f"{PUBLIC_BASE}/{first}", f"first ({first})")
    verify_url(f"{PUBLIC_BASE}/{last}", f"last  ({last})")

    print("\nVerifying seat image...")
    verify_image(IMAGE_URL)

    print(f"\nMetadata live at: {PUBLIC_BASE}/")


if __name__ == "__main__":
    main()
