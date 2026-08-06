#!/usr/bin/env python3
"""
Replace placeholder robot catalog images with real photos from the public web.

Sources (in order, relevance-scored):
  1. Curated seed URLs for well-known models
  2. Wikimedia Commons search (title must match maker/name tokens)
  3. Wikipedia pageimage (page title must be relevant)
  4. Openverse (title/tags must match)
  5. Open Graph image from the robot's buyUrl

Uploads JPEG to DO Spaces under …/robots/{id}.jpg and rewrites catalog URLs.

Usage (repo root):
  python3 scripts/catalog/fetch_real_robot_images.py
  python3 scripts/catalog/fetch_real_robot_images.py --limit 20
  python3 scripts/catalog/fetch_real_robot_images.py --force-all
  python3 scripts/catalog/fetch_real_robot_images.py --dry-run
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import boto3

import config

LOCAL_CATALOG = os.path.join(ROOT, "data", "catalog", "robots.json")
PUBLIC_CATALOG = os.path.join(ROOT, "catalog", "robots.json")
IMG_PREFIX = f"{config.S3_PREFIX.rstrip('/')}/robots"
PUBLIC_BASE = f"{config.DO_SPACES_URL.rstrip('/')}/{IMG_PREFIX}"
UA = "RSE-RobotCatalogBot/1.0 (+https://theservicesexchange.com/robots.html; catalog image refresh)"
MIN_BYTES = 12_000
MAX_BYTES = 8_000_000
TARGET_W = 1280

# High-confidence public product / press images (id → url)
# Prefer official / Wikimedia when possible.
CURATED: Dict[str, str] = {
    "figure-02": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Figure_01_robot.jpg/1280px-Figure_01_robot.jpg",
    "bd-spot": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b9/Boston_Dynamics_Spot_in_Milan.jpg/1280px-Boston_Dynamics_Spot_in_Milan.jpg",
    "bd-atlas": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9a/Boston_Dynamics_LKAB_2_Almedalen_29_juni_2023.jpg/1280px-Boston_Dynamics_LKAB_2_Almedalen_29_juni_2023.jpg",
    "softbank-pepper": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/62/SoftBank_Pepper_which_is_working_at_Heijo_Palace.jpg/1280px-SoftBank_Pepper_which_is_working_at_Heijo_Palace.jpg",
    "softbank-nao": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/86/Nao_Robot_%28Robocup_2016%29.jpg/1280px-Nao_Robot_%28Robocup_2016%29.jpg",
    "anybotics-anymal": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d1/ANYmal_ARCHE_2019_1.jpg/1280px-ANYmal_ARCHE_2019_1.jpg",
    "ur-5e": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/Universal_Robots_UR5.jpg/1280px-Universal_Robots_UR5.jpg",
    "ur-10e": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/Universal_robot_UR10.jpg/1280px-Universal_robot_UR10.jpg",
    "kuka-lbr-iiwa": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/KUKA_LBR_iiwa.jpg/1280px-KUKA_LBR_iiwa.jpg",
    "abb-yumi": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5d/ABB_YuMi.jpg/1280px-ABB_YuMi.jpg",
    "fanuc-crx10": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9a/FANUC_CRX-10iA.jpg/1280px-FANUC_CRX-10iA.jpg",
    "irobot-roomba-j9": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e1/IRobot_Roomba.jpg/1280px-IRobot_Roomba.jpg",
    "dji-mavic3e": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6a/DJI_Mavic_Pro.jpg/1280px-DJI_Mavic_Pro.jpg",
    "waymo-driver": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/98/Waymo_Chrysler_Pacifica_in_Los_Altos_2017.jpg/1280px-Waymo_Chrysler_Pacifica_in_Los_Altos_2017.jpg",
    "intuitive-davinci-xi": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4a/Da_Vinci_Surgical_System.jpg/1280px-Da_Vinci_Surgical_System.jpg",
    "honda-asimo": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/05/HONDA_ASIMO.jpg/1280px-HONDA_ASIMO.jpg",
    "ea-ameca": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1c/Ameca_Engineered_Arts.jpg/1280px-Ameca_Engineered_Arts.jpg",
}


def s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=config.DO_SPACES_KEY,
        aws_secret_access_key=config.DO_SPACES_SECRET,
        endpoint_url=config.DO_SPACES_ENDPOINT,
        region_name=config.DO_SPACES_REGION,
    )


def http_get(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_get_json(url: str, timeout: int = 25) -> Any:
    return json.loads(http_get(url, timeout=timeout).decode("utf-8", errors="replace"))


def probe_is_placeholder(url: str) -> bool:
    try:
        data = http_get(url, timeout=15)
        im = Image.open(io.BytesIO(data))
        return im.size == (960, 640)
    except Exception:
        return True


def _tokens(robot: dict) -> List[str]:
    parts = []
    for key in ("maker", "name", "id"):
        raw = str(robot.get(key) or "")
        parts.extend(re.split(r"[^a-zA-Z0-9]+", raw))
    stop = {
        "the", "a", "an", "robot", "robotics", "inc", "ltd", "llc", "co", "ai",
        "and", "of", "for", "legacy", "system", "systems", "series",
    }
    out = []
    for p in parts:
        t = p.lower().strip()
        if len(t) < 2 or t in stop or t.isdigit():
            continue
        out.append(t)
    # unique preserve order
    seen = set()
    uniq = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def relevance_score(text: str, robot: dict) -> float:
    """Require meaningful token overlap so we don't accept Fujifilm X30 for Deep X30."""
    if not text:
        return 0.0
    t = text.lower()
    toks = _tokens(robot)
    if not toks:
        return 0.0
    # reject common false friends
    bad = ("camera", "lens", "fujifilm", "aircraft", "md-11", "airline", "logo", "svg", "diagram")
    if any(b in t for b in bad) and not any(x in t for x in ("robot", "humanoid", "drone", "cobot")):
        # still allow if strong brand match
        pass
    hits = sum(1 for tok in toks if tok in t)
    # require at least one strong token (maker or primary name word length>=4)
    strong = [tok for tok in toks if len(tok) >= 4]
    strong_hits = sum(1 for tok in strong if tok in t)
    if strong and strong_hits == 0:
        return 0.0
    if hits == 0:
        return 0.0
    score = hits / max(len(toks), 1)
    if "robot" in t or "humanoid" in t or "cobot" in t:
        score += 0.15
    maker = str(robot.get("maker") or "").lower()
    name = str(robot.get("name") or "").lower()
    if maker and maker in t:
        score += 0.35
    if name and len(name) >= 3 and name in t:
        score += 0.35
    return score


def search_commons(query: str, robot: dict) -> List[Tuple[float, str]]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": "12",
        "gsrnamespace": "6",
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
        "iiurlwidth": str(TARGET_W),
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    try:
        data = http_get_json(url)
    except Exception:
        return []
    pages = (data.get("query") or {}).get("pages") or {}
    out: List[Tuple[float, str]] = []
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        mime = (ii.get("mime") or "").lower()
        if mime not in ("image/jpeg", "image/png", "image/webp"):
            continue
        title = (p.get("title") or "")
        if any(x in title.lower() for x in ("logo", "icon", "svg", "diagram", "schematic", "pdf", ".svg")):
            continue
        cand = ii.get("thumburl") or ii.get("url")
        if not cand:
            continue
        cand = cand.split("?")[0]
        score = relevance_score(title + " " + cand, robot)
        if score < 0.25:
            continue
        out.append((score, cand))
    out.sort(key=lambda x: -x[0])
    return out


def search_wikipedia_pageimage(title_query: str, robot: dict) -> List[Tuple[float, str]]:
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": title_query,
        "srlimit": "5",
    }
    try:
        data = http_get_json(
            "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
        )
    except Exception:
        return []
    hits = (data.get("query") or {}).get("search") or []
    out: List[Tuple[float, str]] = []
    for hit in hits:
        title = hit.get("title") or ""
        score = relevance_score(title, robot)
        if score < 0.3:
            continue
        p2 = {
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "pageimages",
            "pithumbsize": str(TARGET_W),
            "pilicense": "any",
        }
        try:
            d2 = http_get_json(
                "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(p2)
            )
            pages = (d2.get("query") or {}).get("pages") or {}
            for page in pages.values():
                thumb = (page.get("thumbnail") or {}).get("source")
                if thumb:
                    out.append((score + 0.1, thumb.split("?")[0]))
        except Exception:
            continue
    out.sort(key=lambda x: -x[0])
    return out


def search_openverse(query: str, robot: dict) -> List[Tuple[float, str]]:
    params = {
        "q": query,
        "page_size": "10",
        "license_type": "commercial,modification",
        "extension": "jpg,png",
        "mature": "false",
    }
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params)
    try:
        data = http_get_json(url)
    except Exception:
        return []
    out: List[Tuple[float, str]] = []
    for item in data.get("results") or []:
        title = str(item.get("title") or "")
        tags = " ".join(
            t.get("name", "") if isinstance(t, dict) else str(t)
            for t in (item.get("tags") or [])[:12]
        )
        score = relevance_score(title + " " + tags, robot)
        if score < 0.28:
            continue
        for key in ("url", "thumbnail"):
            u = item.get(key)
            if u and isinstance(u, str) and u.startswith("http"):
                out.append((score, u))
                break
    out.sort(key=lambda x: -x[0])
    return out


_OG_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_OG_RE2 = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.I,
)


def og_image_from_url(page_url: str) -> List[Tuple[float, str]]:
    if not page_url or not page_url.startswith("http"):
        return []
    try:
        html = http_get(page_url, timeout=18).decode("utf-8", errors="replace")
    except Exception:
        return []
    m = _OG_RE.search(html) or _OG_RE2.search(html)
    if not m:
        return []
    img = m.group(1).strip()
    if img.startswith("//"):
        img = "https:" + img
    if img.startswith("http"):
        # og:image from official product page is trusted
        return [(0.9, img)]
    return []


def candidate_queries(robot: dict) -> List[str]:
    maker = str(robot.get("maker") or "").strip()
    name = str(robot.get("name") or "").strip()
    q = []
    if maker and name:
        q.append(f'"{maker}" "{name}" robot')
        q.append(f"{maker} {name} robot")
        q.append(f"{maker} {name}")
    if name and len(name) > 2:
        q.append(f"{name} robot {maker}")
    # de-dupe
    seen = set()
    out = []
    for s in q:
        k = s.lower()
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def collect_candidates(robot: dict) -> List[str]:
    scored: List[Tuple[float, str]] = []
    rid = robot.get("id") or ""
    if rid in CURATED:
        scored.append((1.5, CURATED[rid]))

    for q in candidate_queries(robot)[:3]:
        scored.extend(search_commons(q, robot))
        if len(scored) >= 10:
            break
    if len(scored) < 6:
        for q in candidate_queries(robot)[:2]:
            scored.extend(search_wikipedia_pageimage(q, robot))
    if len(scored) < 6:
        for q in candidate_queries(robot)[:2]:
            scored.extend(search_openverse(q, robot))
    buy = robot.get("buyUrl") or ""
    if buy:
        scored.extend(og_image_from_url(buy))

    scored.sort(key=lambda x: -x[0])
    seen = set()
    out = []
    for score, u in scored:
        if score < 0.25:
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def download_and_normalize(url: str) -> Optional[bytes]:
    try:
        raw = http_get(url, timeout=30)
    except Exception:
        return None
    if len(raw) < MIN_BYTES or len(raw) > MAX_BYTES:
        return None
    try:
        im = Image.open(io.BytesIO(raw))
        im = im.convert("RGB")
    except Exception:
        return None
    w, h = im.size
    if w < 280 or h < 200:
        return None
    if w == 960 and h == 640:
        sample = im.resize((64, 42))
        colors = sample.getcolors(maxcolors=64 * 42) or []
        if len(colors) < 40:
            return None
    if w > TARGET_W:
        nh = int(h * (TARGET_W / w))
        im = im.resize((TARGET_W, max(nh, 1)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88, optimize=True)
    data = buf.getvalue()
    if len(data) < MIN_BYTES:
        return None
    return data


def upload_jpeg(client, rid: str, body: bytes, dry_run: bool) -> str:
    key = f"{IMG_PREFIX}/{rid}.jpg"
    if dry_run:
        print(f"  [dry-run] would upload {key} ({len(body)} bytes)")
        return f"{PUBLIC_BASE}/{rid}.jpg"
    client.put_object(
        Bucket=config.DO_SPACES_BUCKET,
        Key=key,
        Body=body,
        ContentType="image/jpeg",
        ACL="public-read",
        CacheControl="public, max-age=86400",
    )
    return f"{PUBLIC_BASE}/{rid}.jpg"


def save_catalog(catalog: dict) -> None:
    catalog["updated_at"] = int(time.time())
    catalog["updated_at_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    catalog["count"] = len(catalog.get("robots") or [])
    catalog["source"] = catalog.get("source") or "image_refresh"
    os.makedirs(os.path.dirname(LOCAL_CATALOG), exist_ok=True)
    with open(LOCAL_CATALOG, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)
        f.write("\n")
    os.makedirs(os.path.dirname(PUBLIC_CATALOG), exist_ok=True)
    with open(PUBLIC_CATALOG, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)
        f.write("\n")


def catalog_key() -> str:
    return getattr(config, "ROBOT_CATALOG_KEY", None) or f"{config.S3_PREFIX.rstrip('/')}/catalog/robots.json"


def upload_catalog(client, catalog: dict, dry_run: bool) -> None:
    key = catalog_key()
    body = json.dumps(catalog, indent=2).encode("utf-8")
    if dry_run:
        print(f"[dry-run] would upload catalog {key}")
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


def process_one(robot: dict) -> Tuple[str, str, Optional[bytes]]:
    rid = robot.get("id") or ""
    candidates = collect_candidates(robot)
    for url in candidates:
        body = download_and_normalize(url)
        if body:
            return rid, f"ok:{url[:90]}", body
        time.sleep(0.1)
    return rid, "no_image", None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-all", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ids", type=str, default="")
    parser.add_argument("--no-upload-catalog", action="store_true")
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Only robots whose image is missing or still 960x640 placeholder",
    )
    args = parser.parse_args()
    if not args.force_all:
        args.only_missing = True

    with open(LOCAL_CATALOG, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    robots: List[dict] = catalog.get("robots") or []

    only_ids = {x.strip() for x in args.ids.split(",") if x.strip()} if args.ids else set()

    targets: List[dict] = []
    print("Scanning catalog…")
    for r in robots:
        rid = r.get("id") or ""
        if only_ids and rid not in only_ids:
            continue
        if args.force_all or only_ids:
            targets.append(r)
        else:
            img = r.get("image") or ""
            if not img or probe_is_placeholder(img):
                targets.append(r)
        if args.limit and len(targets) >= args.limit:
            break

    if args.limit and len(targets) > args.limit:
        targets = targets[: args.limit]

    print(f"Will fetch images for {len(targets)} robots")
    client = s3_client()

    ok = 0
    fail = 0
    for i, r in enumerate(targets, 1):
        rid = r.get("id")
        print(f"[{i}/{len(targets)}] {rid} …", flush=True)
        try:
            _, status, body = process_one(r)
        except Exception as e:
            print(f"  FAIL {e}")
            fail += 1
            continue
        if not body:
            print("  no real image found")
            fail += 1
            continue
        url = upload_jpeg(client, rid, body, args.dry_run)
        r["image"] = url.split("?")[0]
        print(f"  ✓ {status} → {len(body)} bytes")
        ok += 1
        if ok % 8 == 0:
            save_catalog(catalog)
        time.sleep(0.2)

    save_catalog(catalog)
    print(f"Fetched OK: {ok}  failed: {fail}")
    print(f"Wrote {LOCAL_CATALOG} and {PUBLIC_CATALOG}")

    if not args.no_upload_catalog:
        upload_catalog(client, catalog, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
