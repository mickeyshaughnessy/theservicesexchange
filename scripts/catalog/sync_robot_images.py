#!/usr/bin/env python3
"""
Ensure every robot in data/catalog/robots.json has a public image on DO Spaces.

- Reuses existing Spaces objects (any extension) when the id stem matches
- Generates branded placeholder JPEGs for missing assets
- Rewrites catalog image URLs to match uploaded keys
- Optionally re-uploads robots.json

Usage (repo root):
  python3 scripts/catalog/sync_robot_images.py
  python3 scripts/catalog/sync_robot_images.py --dry-run
  python3 scripts/catalog/sync_robot_images.py --no-upload-catalog
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import boto3
from botocore.exceptions import ClientError

import config

LOCAL_CATALOG = os.path.join(ROOT, "data", "catalog", "robots.json")
PUBLIC_CATALOG = os.path.join(ROOT, "catalog", "robots.json")
IMG_PREFIX = f"{config.S3_PREFIX.rstrip('/')}/robots"
PUBLIC_BASE = f"{config.DO_SPACES_URL.rstrip('/')}/{IMG_PREFIX}"

# Category → accent RGB (neon palette matching site)
CATEGORY_COLORS = {
    "Humanoid": (0, 255, 255),
    "Autonomous Vehicle": (57, 255, 20),
    "Quadruped": (255, 0, 255),
    "Manipulator": (255, 200, 0),
    "AMR": (0, 200, 255),
    "Cobot": (255, 120, 0),
    "Drone": (120, 180, 255),
    "Agriculture": (100, 255, 100),
    "Medical": (255, 80, 120),
    "Cleaning": (180, 255, 255),
    "Delivery": (255, 220, 100),
    "Security": (255, 80, 80),
    "Construction": (255, 160, 60),
    "Exoskeleton": (200, 120, 255),
    "Discovered": (85, 102, 170),
}


def catalog_key() -> str:
    return getattr(config, "ROBOT_CATALOG_KEY", None) or f"{config.S3_PREFIX.rstrip('/')}/catalog/robots.json"


def s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=config.DO_SPACES_KEY,
        aws_secret_access_key=config.DO_SPACES_SECRET,
        endpoint_url=config.DO_SPACES_ENDPOINT,
        region_name=config.DO_SPACES_REGION,
    )


def list_existing_images(client) -> Dict[str, str]:
    """Map robot id stem → full Spaces key for existing objects under robots/."""
    out: Dict[str, str] = {}
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=config.DO_SPACES_BUCKET, Prefix=IMG_PREFIX + "/"):
        for obj in page.get("Contents") or []:
            key = obj["Key"]
            fname = key.rsplit("/", 1)[-1]
            if "." not in fname:
                continue
            stem = fname.rsplit(".", 1)[0]
            out[stem] = key
    return out


def _font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
        "/System/Library/Fonts/Courier.ttc",
        "/Library/Fonts/Courier New.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> List[str]:
    words = text.split()
    if not words:
        return [""]
    lines: List[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = f"{cur} {w}"
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def make_placeholder(robot: dict, size: Tuple[int, int] = (960, 640)) -> bytes:
    w, h = size
    tags = robot.get("tags") or []
    category = robot.get("category") or (tags[0] if tags else "Robot")
    accent = CATEGORY_COLORS.get(category, (0, 255, 255))
    # Dim category match from first tag
    for t in tags:
        if t in CATEGORY_COLORS:
            accent = CATEGORY_COLORS[t]
            break

    img = Image.new("RGB", size, (8, 10, 28))
    draw = ImageDraw.Draw(img)

    # Grid background
    for x in range(0, w, 40):
        draw.line([(x, 0), (x, h)], fill=(18, 24, 48), width=1)
    for y in range(0, h, 40):
        draw.line([(0, y), (w, y)], fill=(18, 24, 48), width=1)

    # Outer neon frame
    draw.rectangle([12, 12, w - 13, h - 13], outline=accent, width=3)
    draw.rectangle([20, 20, w - 21, h - 21], outline=(accent[0] // 3, accent[1] // 3, accent[2] // 3), width=1)

    # Stylized robot glyph (simple head + body)
    cx, cy = w // 2, h // 2 - 40
    draw.rounded_rectangle([cx - 70, cy - 90, cx + 70, cy + 40], radius=18, outline=accent, width=4)
    draw.ellipse([cx - 28, cy - 60, cx - 8, cy - 40], outline=accent, width=3)
    draw.ellipse([cx + 8, cy - 60, cx + 28, cy - 40], outline=accent, width=3)
    draw.arc([cx - 30, cy - 30, cx + 30, cy + 10], 20, 160, fill=accent, width=3)
    draw.line([(cx, cy - 90), (cx, cy - 120)], fill=accent, width=3)
    draw.ellipse([cx - 8, cy - 136, cx + 8, cy - 120], outline=accent, width=3)
    draw.rounded_rectangle([cx - 50, cy + 50, cx + 50, cy + 130], radius=12, outline=accent, width=3)
    draw.line([(cx - 50, cy + 70), (cx - 100, cy + 40)], fill=accent, width=4)
    draw.line([(cx + 50, cy + 70), (cx + 100, cy + 40)], fill=accent, width=4)

    title_font = _font(36)
    sub_font = _font(22)
    tag_font = _font(18)
    small_font = _font(16)

    maker = str(robot.get("maker") or "")
    name = str(robot.get("name") or robot.get("id") or "Robot")
    max_text = w - 80

    y = h - 170
    for line in _wrap(draw, maker.upper(), sub_font, max_text)[:2]:
        tw = draw.textlength(line, font=sub_font)
        draw.text(((w - tw) / 2, y), line, fill=(140, 150, 180), font=sub_font)
        y += 28

    for line in _wrap(draw, name, title_font, max_text)[:2]:
        tw = draw.textlength(line, font=title_font)
        draw.text(((w - tw) / 2, y), line, fill=accent, font=title_font)
        y += 42

    tag_line = " · ".join(str(t) for t in tags[:3]) or category
    tw = draw.textlength(tag_line, font=tag_font)
    if tw > max_text:
        tag_line = tag_line[:40] + "…"
        tw = draw.textlength(tag_line, font=tag_font)
    draw.text(((w - tw) / 2, y + 4), tag_line, fill=(100, 110, 140), font=tag_font)

    badge = "THE RSE · ROBOT CATALOG"
    tw = draw.textlength(badge, font=small_font)
    draw.text(((w - tw) / 2, 36), badge, fill=(60, 80, 110), font=small_font)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()


def content_type_for_key(key: str) -> str:
    ext = key.rsplit(".", 1)[-1].lower()
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(ext, "application/octet-stream")


def upload_bytes(client, key: str, body: bytes, content_type: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry-run] would upload {key} ({len(body)} bytes, {content_type})")
        return
    client.put_object(
        Bucket=config.DO_SPACES_BUCKET,
        Key=key,
        Body=body,
        ContentType=content_type,
        ACL="public-read",
        CacheControl="public, max-age=86400",
    )


def save_catalog(catalog: dict) -> None:
    catalog["updated_at"] = int(time.time())
    catalog["updated_at_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    catalog["count"] = len(catalog.get("robots") or [])
    os.makedirs(os.path.dirname(LOCAL_CATALOG), exist_ok=True)
    with open(LOCAL_CATALOG, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)
        f.write("\n")
    # Same-origin public copy for nginx (avoids CORS for the page)
    os.makedirs(os.path.dirname(PUBLIC_CATALOG), exist_ok=True)
    with open(PUBLIC_CATALOG, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)
        f.write("\n")


def upload_catalog(client, catalog: dict, dry_run: bool) -> None:
    key = catalog_key()
    body = json.dumps(catalog, indent=2).encode("utf-8")
    if dry_run:
        print(f"[dry-run] would upload catalog {key} ({len(body)} bytes)")
        return
    client.put_object(
        Bucket=config.DO_SPACES_BUCKET,
        Key=key,
        Body=body,
        ContentType="application/json",
        ACL="public-read",
        CacheControl="public, max-age=300",
    )
    print(f"✓ Uploaded catalog → {config.DO_SPACES_URL.rstrip('/')}/{key}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync robot catalog images to DO Spaces")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-upload-catalog", action="store_true")
    parser.add_argument("--force-placeholders", action="store_true", help="Regenerate placeholders even if image exists")
    args = parser.parse_args()

    with open(LOCAL_CATALOG, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    robots: List[dict] = catalog.get("robots") or []
    if not robots:
        print("ERROR: empty catalog", file=sys.stderr)
        return 1

    client = s3_client()
    existing = list_existing_images(client)
    print(f"Catalog robots: {len(robots)}")
    print(f"Existing Spaces images: {len(existing)}")

    reused = 0
    created = 0
    rewritten = 0

    for r in robots:
        rid = r.get("id") or ""
        if not rid:
            continue
        key: Optional[str] = existing.get(rid)
        if key and not args.force_placeholders:
            url = f"{config.DO_SPACES_URL.rstrip('/')}/{key}"
            if r.get("image") != url:
                r["image"] = url
                rewritten += 1
            reused += 1
            continue

        # Create placeholder JPEG for this id
        key = f"{IMG_PREFIX}/{rid}.jpg"
        body = make_placeholder(r)
        upload_bytes(client, key, body, "image/jpeg", args.dry_run)
        r["image"] = f"{PUBLIC_BASE}/{rid}.jpg"
        existing[rid] = key
        created += 1
        if created % 25 == 0:
            print(f"  … generated {created} placeholders")

    save_catalog(catalog)
    print(f"Reused existing: {reused}")
    print(f"Placeholders created: {created}")
    print(f"URL rewrites: {rewritten}")
    print(f"Wrote {LOCAL_CATALOG} and {PUBLIC_CATALOG}")

    if not args.no_upload_catalog:
        upload_catalog(client, catalog, args.dry_run)

    # Quick integrity: every robot has image URL
    missing_url = [r["id"] for r in robots if not r.get("image")]
    if missing_url:
        print("WARNING still missing image field:", missing_url[:10])
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
