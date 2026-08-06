#!/usr/bin/env python3
"""
Upload the Buy a Robot static catalog JSON to DigitalOcean Spaces.

Usage (from repo root, with config.py present):
  python3 scripts/catalog/upload_robots_catalog.py
  python3 scripts/catalog/upload_robots_catalog.py --file data/catalog/robots.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

# Repo root on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import boto3
from botocore.exceptions import ClientError

import config


def catalog_key() -> str:
    return getattr(config, "ROBOT_CATALOG_KEY", None) or f"{config.S3_PREFIX.rstrip('/')}/catalog/robots.json"


def catalog_public_url(key: str) -> str:
    override = getattr(config, "ROBOT_CATALOG_URL", None) or ""
    if override:
        return override
    return f"{config.DO_SPACES_URL.rstrip('/')}/{key}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload robots catalog to DO Spaces")
    parser.add_argument(
        "--file",
        default=os.path.join(ROOT, "data", "catalog", "robots.json"),
        help="Path to robots.json",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate only, do not upload")
    args = parser.parse_args()

    with open(args.file, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    robots = catalog.get("robots") or []
    if len(robots) < 1:
        print("ERROR: catalog has no robots", file=sys.stderr)
        return 1

    catalog["updated_at"] = int(time.time())
    catalog["updated_at_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    catalog["count"] = len(robots)

    body = json.dumps(catalog, indent=2)
    key = catalog_key()
    url = catalog_public_url(key)

    # Keep same-origin copy in sync for robots.html (no CORS needed)
    public_path = os.path.join(ROOT, "catalog", "robots.json")
    os.makedirs(os.path.dirname(public_path), exist_ok=True)
    with open(public_path, "w", encoding="utf-8") as pf:
        pf.write(body)
        if not body.endswith("\n"):
            pf.write("\n")
    # Also refresh local data path timestamps if we rewrote count/updated_at
    with open(args.file, "w", encoding="utf-8") as lf:
        lf.write(body)
        if not body.endswith("\n"):
            lf.write("\n")

    print(f"Catalog: {len(robots)} robots")
    print(f"Key:     {key}")
    print(f"URL:     {url}")
    print(f"Local:   {public_path}")

    if args.dry_run:
        print("Dry run — not uploading")
        return 0

    client = boto3.client(
        "s3",
        aws_access_key_id=config.DO_SPACES_KEY,
        aws_secret_access_key=config.DO_SPACES_SECRET,
        endpoint_url=config.DO_SPACES_ENDPOINT,
        region_name=config.DO_SPACES_REGION,
    )
    try:
        client.put_object(
            Bucket=config.DO_SPACES_BUCKET,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
            ACL="public-read",
            CacheControl="public, max-age=300",
        )
    except ClientError as e:
        print(f"Upload failed: {e}", file=sys.stderr)
        return 1

    print("✓ Uploaded robots catalog to DO Spaces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
