#!/usr/bin/env python3
"""
Weekly robot catalog updater.

Merges:
  1. Existing static catalog (local file or DO Spaces)
  2. Heuristic web crawl of known manufacturer product pages
  3. Optional X/Twitter signals (via `grok` headless if available, or xAI-less stubs)

Writes data/catalog/robots.json and optionally uploads to DO Spaces.

Designed to run from cron on the production box:
  15 4 * * 1  cd /var/www/theservicesexchange && ./scripts/catalog/run_weekly_catalog_update.sh

Environment:
  RSE_CATALOG_UPLOAD=1     upload to Spaces after merge (default 1 on prod)
  RSE_CATALOG_USE_GROK=1   invoke grok -p for X/@humanoidhub enrichment
  XAI_API_KEY              optional; used by grok headless
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LOCAL_CATALOG = os.path.join(ROOT, "data", "catalog", "robots.json")
USER_AGENT = "RSE-RobotCatalogBot/1.0 (+https://theservicesexchange.com/robots.html; weekly catalog refresh)"

# Seed product / news pages worth scraping for new model names
CRAWL_URLS = [
    "https://www.unitree.com/",
    "https://bostondynamics.com/products/",
    "https://www.figure.ai/",
    "https://www.1x.tech/",
    "https://agilityrobotics.com/",
    "https://apptronik.com/",
    "https://www.sanctuary.ai/",
    "https://www.anybotics.com/",
    "https://carbonrobotics.com/",
    "https://www.universal-robots.com/products/",
    "https://locusrobotics.com/",
    "https://www.geekplus.com/",
    "https://www.skydio.com/",
    "https://www.dji.com/",
    "https://neura-robotics.com/",
    "https://www.engineeredarts.co.uk/",
    "https://www.softbankrobotics.com/",
    "https://www.tesla.com/AI",
    "https://www.ubtrobot.com/",
    "https://www.fftai.com/",
]

# X accounts to watch for new humanoid / robot product announcements
X_ACCOUNTS = [
    "humanoidhub",
    "Figure_robot",
    "1x_tech",
    "agilityrobotics",
    "Apptronik",
    "BostonDynamics",
    "UnitreeRobotics",
    "Anybotics",
    "Tesla_AI",
    "Sanctuary_AI",
]


def _slug(maker: str, name: str) -> str:
    raw = f"{maker}-{name}".lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return raw[:80] or hashlib.sha1(f"{maker}{name}".encode()).hexdigest()[:12]


def load_local() -> Dict[str, Any]:
    if not os.path.isfile(LOCAL_CATALOG):
        return {"version": 1, "robots": [], "count": 0, "source": "empty"}
    with open(LOCAL_CATALOG, "r", encoding="utf-8") as f:
        return json.load(f)


def load_remote() -> Optional[Dict[str, Any]]:
    try:
        import config
        key = getattr(config, "ROBOT_CATALOG_KEY", None) or f"{config.S3_PREFIX.rstrip('/')}/catalog/robots.json"
        url = getattr(config, "ROBOT_CATALOG_URL", None) or f"{config.DO_SPACES_URL.rstrip('/')}/{key}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"remote catalog fetch skipped: {e}")
        return None


def fetch_text(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        # Cap HTML size
        return raw[:400_000].decode("utf-8", errors="ignore")


def extract_candidates(html: str, source_url: str) -> List[Dict[str, Any]]:
    """Heuristic extraction of product-like names from HTML titles/headings."""
    candidates: List[Dict[str, Any]] = []
    title_m = re.search(r"<title[^>]*>([^<]{3,120})</title>", html, re.I)
    page_title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""

    headings = re.findall(r"<h[12][^>]*>(.*?)</h[12]>", html, flags=re.I | re.S)
    texts = []
    if page_title:
        texts.append(page_title)
    for h in headings[:40]:
        clean = re.sub(r"<[^>]+>", " ", h)
        clean = re.sub(r"\s+", " ", clean).strip()
        if 3 <= len(clean) <= 80:
            texts.append(clean)

    robotish = re.compile(
        r"\b(robot|humanoid|quadruped|cobot|amr|autonomous|drone|rover|arm)\b",
        re.I,
    )
    for t in texts:
        if not robotish.search(t) and not re.search(
            r"\b(Spot|Atlas|Optimus|Digit|Apollo|NEO|G1|Go2|UR\d|Stretch)\b", t
        ):
            continue
        # Skip pure marketing slogans
        if t.lower() in ("products", "robots", "our robots", "solutions"):
            continue
        candidates.append({
            "name_hint": t,
            "source_url": source_url,
            "discovered_via": "web_crawl",
        })
    return candidates


def crawl_sites() -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    for url in CRAWL_URLS:
        try:
            html = fetch_text(url)
            found.extend(extract_candidates(html, url))
            print(f"  crawl ok: {url} (+candidates)")
        except Exception as e:
            print(f"  crawl fail: {url}: {e}")
        time.sleep(0.6)
    return found


def grok_x_enrichment() -> List[Dict[str, Any]]:
    """
    Use Grok Build headless to summarize recent robot product signals from X.
    Requires grok on PATH and credentials (XAI_API_KEY or ~/.grok/auth.json).
    """
    if os.environ.get("RSE_CATALOG_USE_GROK", "1") not in ("1", "true", "yes"):
        print("  grok enrichment disabled (RSE_CATALOG_USE_GROK=0)")
        return []

    accounts = " ".join(f"@{a}" for a in X_ACCOUNTS)
    prompt = f"""You are updating The RSE Buy-a-Robot catalog.
Search recent posts from these X accounts and related humanoid/robot news:
{accounts}

Return ONLY a JSON array (no markdown) of newly announced or commercially relevant robots.
Each object:
{{
  "maker": "string",
  "name": "string",
  "tags": ["Humanoid"|...],
  "desc": "one sentence",
  "earnings": "string estimate or Contact",
  "price": "string",
  "status": "available"|"preorder"|"planned",
  "statusLabel": "string",
  "buyUrl": "https://...",
  "source": "x.com"
}}
Max 25 items. Prefer real product names over vaporware. If nothing new, return [].
"""
    try:
        proc = subprocess.run(
            [
                "grok",
                "-p", prompt,
                "--output-format", "plain",
                "--max-turns", "8",
                "--disallowed-tools", "run_terminal_cmd,search_replace,Write,Edit",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=ROOT,
        )
    except FileNotFoundError:
        print("  grok binary not found — skip X enrichment")
        return []
    except subprocess.TimeoutExpired:
        print("  grok timed out — skip X enrichment")
        return []

    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        print(f"  grok exit {proc.returncode}: {(proc.stderr or '')[:300]}")
    # Extract JSON array from response
    m = re.search(r"\[[\s\S]*\]", out)
    if not m:
        print("  grok: no JSON array in response")
        return []
    try:
        data = json.loads(m.group(0))
        if isinstance(data, list):
            print(f"  grok: {len(data)} candidates from X/web")
            return [x for x in data if isinstance(x, dict)]
    except json.JSONDecodeError as e:
        print(f"  grok JSON parse error: {e}")
    return []


def merge_robot(existing_by_id: Dict[str, Dict], robot: Dict[str, Any]) -> None:
    maker = (robot.get("maker") or "Unknown").strip()
    name = (robot.get("name") or robot.get("name_hint") or "").strip()
    if not name:
        return
    rid = robot.get("id") or _slug(maker, name)
    if rid in existing_by_id:
        # Refresh buyUrl / status if new data provides them
        cur = existing_by_id[rid]
        for k in ("buyUrl", "status", "statusLabel", "price", "desc", "earnings", "tags"):
            if robot.get(k) and not cur.get(k):
                cur[k] = robot[k]
        cur["last_seen_at"] = int(time.time())
        return

    base_img = "https://mithril-media.sfo3.digitaloceanspaces.com/theservicesexchange/robots"
    entry = {
        "id": rid,
        "maker": maker,
        "name": name[:80],
        "image": robot.get("image") or f"{base_img}/{rid}.jpg",
        "tags": robot.get("tags") or ["Discovered"],
        "desc": (robot.get("desc") or f"Discovered listing for {maker} {name}. Verify price and availability with the manufacturer.")[:500],
        "earnings": robot.get("earnings") or "See market rates",
        "price": robot.get("price") or "Contact for quote",
        "status": robot.get("status") if robot.get("status") in ("available", "preorder", "planned") else "planned",
        "statusLabel": robot.get("statusLabel") or "Discovered",
        "buyUrl": robot.get("buyUrl") or robot.get("source_url") or "https://theservicesexchange.com/robots.html",
        "category": robot.get("category") or "Discovered",
        "discovered_via": robot.get("discovered_via") or robot.get("source") or "crawl",
        "last_seen_at": int(time.time()),
    }
    existing_by_id[rid] = entry


def save_local(catalog: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(LOCAL_CATALOG), exist_ok=True)
    with open(LOCAL_CATALOG, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)
        f.write("\n")
    print(f"Wrote {catalog['count']} robots → {LOCAL_CATALOG}")


def upload() -> int:
    script = os.path.join(os.path.dirname(__file__), "upload_robots_catalog.py")
    return subprocess.call([sys.executable, script, "--file", LOCAL_CATALOG])


def main() -> int:
    print("=== RSE robot catalog weekly update ===")
    base = load_remote() or load_local()
    robots = list(base.get("robots") or [])
    by_id = {r["id"]: dict(r) for r in robots if r.get("id")}

    print("Crawling manufacturer sites (signal only; no Unknown-maker inserts)…")
    crawl_hits = crawl_sites()
    print(f"  {len(crawl_hits)} heading/title signals retained for logs")
    # Touch last_seen on existing robots when their maker domain was crawled successfully
    crawled_hosts = set()
    for c in crawl_hits:
        url = c.get("source_url") or ""
        m = re.search(r"https?://([^/]+)/", url)
        if m:
            crawled_hosts.add(m.group(1).lower())
    now = int(time.time())
    for rid, r in by_id.items():
        buy = (r.get("buyUrl") or "").lower()
        if any(h in buy for h in crawled_hosts):
            r["last_seen_at"] = now

    print("X / Grok enrichment…")
    for item in grok_x_enrichment():
        if not item.get("maker") or not item.get("name"):
            continue
        item["discovered_via"] = item.get("source") or "x_grok"
        merge_robot(by_id, item)

    merged = sorted(by_id.values(), key=lambda r: (r.get("maker") or "", r.get("name") or ""))
    catalog = {
        "version": int(base.get("version") or 1),
        "updated_at": int(time.time()),
        "updated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "weekly_update",
        "count": len(merged),
        "x_accounts_watched": X_ACCOUNTS,
        "crawl_urls": CRAWL_URLS,
        "robots": merged,
    }
    save_local(catalog)

    do_upload = os.environ.get("RSE_CATALOG_UPLOAD", "1") in ("1", "true", "yes")
    if do_upload:
        print("Uploading to DO Spaces…")
        rc = upload()
        if rc != 0:
            return rc
    else:
        print("Upload skipped (RSE_CATALOG_UPLOAD=0)")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
