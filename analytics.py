"""
In-process + DigitalOcean Spaces analytics for the admin dashboard.

API timings live in memory per gunicorn worker and flush to Spaces.
Page views / clicks accumulate in memory and merge into one Spaces JSON object.
"""
from __future__ import annotations

import os
import re
import threading
import time
from typing import Any, Dict, List

from utils import (
    get_analytics_api_snapshots,
    get_analytics_traffic,
    save_analytics_api_snapshot,
    save_analytics_traffic,
)

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_LOCK = threading.Lock()
_STARTED = time.time()
_WORKER_ID = f"{os.getpid()}"

_api = {
    "total": 0,
    "errors": 0,
    "load_test": 0,
    "routes": {},  # key -> {count, total_time, min_time, max_time, errors, statuses}
    "recent": [],  # last 80
}
_pending_traffic = {
    "pages": {},
    "clicks": {},
    "events": {},
    "days": {},
}
_last_api_flush = 0.0
_last_traffic_flush = 0.0
_traffic_dirty = False


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    parts = [p for p in path.split("/") if p != ""]
    out = []
    for p in parts:
        if _UUID_RE.match(p):
            out.append("*")
        elif p.isdigit() and len(p) >= 3:
            out.append("*")
        else:
            out.append(p)
    return "/" + "/".join(out)


def record_api(method: str, path: str, status: int, duration: float, load_test: bool = False) -> None:
    route = f"{method} {normalize_path(path)}"
    with _LOCK:
        _api["total"] += 1
        if load_test:
            _api["load_test"] += 1
        if status >= 400:
            _api["errors"] += 1
        rec = _api["routes"].get(route)
        if rec is None:
            rec = {
                "count": 0,
                "total_time": 0.0,
                "min_time": duration,
                "max_time": duration,
                "errors": 0,
                "statuses": {},
            }
            _api["routes"][route] = rec
        rec["count"] += 1
        rec["total_time"] += duration
        rec["min_time"] = min(rec["min_time"], duration)
        rec["max_time"] = max(rec["max_time"], duration)
        if status >= 400:
            rec["errors"] += 1
        rec["statuses"][str(status)] = rec["statuses"].get(str(status), 0) + 1
        _api["recent"].append({
            "t": int(time.time()),
            "route": route,
            "status": status,
            "ms": round(duration * 1000, 1),
        })
        if len(_api["recent"]) > 80:
            _api["recent"] = _api["recent"][-80:]
    maybe_flush_api()


def record_traffic(event: str, path: str, href: str = "", label: str = "") -> None:
    event = (event or "event")[:64]
    path = (path or "/")[:240]
    href = (href or "")[:240]
    label = (label or "")[:120]
    day = time.strftime("%Y-%m-%d", time.gmtime())
    now = int(time.time())
    with _LOCK:
        global _traffic_dirty
        _pending_traffic["events"][event] = _pending_traffic["events"].get(event, 0) + 1
        day_rec = _pending_traffic["days"].setdefault(day, {"views": 0, "clicks": 0, "events": 0})
        day_rec["events"] += 1
        if event == "page_view":
            rec = _pending_traffic["pages"].setdefault(path, {"views": 0, "last": 0})
            rec["views"] += 1
            rec["last"] = now
            day_rec["views"] += 1
        elif event == "click":
            key = (label or href or path)[:160]
            rec = _pending_traffic["clicks"].setdefault(key, {"count": 0, "last": 0, "href": href, "path": path})
            rec["count"] += 1
            rec["last"] = now
            rec["href"] = href or rec.get("href") or ""
            rec["path"] = path
            day_rec["clicks"] += 1
        _traffic_dirty = True
    maybe_flush_traffic()


def maybe_flush_api(force: bool = False) -> None:
    global _last_api_flush
    now = time.time()
    if not force and now - _last_api_flush < 45:
        return
    with _LOCK:
        payload = {
            "worker": _WORKER_ID,
            "updated": int(now),
            "started": int(_STARTED),
            "total": _api["total"],
            "errors": _api["errors"],
            "load_test": _api["load_test"],
            "routes": _api["routes"],
            "recent": _api["recent"][-40:],
        }
        _last_api_flush = now
    try:
        save_analytics_api_snapshot(_WORKER_ID, payload)
    except Exception:
        pass


def maybe_flush_traffic(force: bool = False) -> None:
    global _last_traffic_flush, _traffic_dirty
    now = time.time()
    if not force and (not _traffic_dirty or now - _last_traffic_flush < 8):
        return
    with _LOCK:
        if not _traffic_dirty and not force:
            return
        pending = {
            "pages": _pending_traffic["pages"],
            "clicks": _pending_traffic["clicks"],
            "events": _pending_traffic["events"],
            "days": _pending_traffic["days"],
        }
        _pending_traffic["pages"] = {}
        _pending_traffic["clicks"] = {}
        _pending_traffic["events"] = {}
        _pending_traffic["days"] = {}
        _traffic_dirty = False
        _last_traffic_flush = now
    try:
        stored = get_analytics_traffic() or {}
        merged = _add_traffic(stored, pending)
        merged["updated"] = int(time.time())
        save_analytics_traffic(merged)
    except Exception:
        with _LOCK:
            # put deltas back so they are not lost
            _pending_traffic["pages"] = _add_map(_pending_traffic["pages"], pending["pages"], "views")
            _pending_traffic["clicks"] = _add_map(_pending_traffic["clicks"], pending["clicks"], "count")
            for k, n in (pending["events"] or {}).items():
                _pending_traffic["events"][k] = _pending_traffic["events"].get(k, 0) + int(n or 0)
            _pending_traffic["days"] = _add_days(_pending_traffic["days"], pending["days"])
            _traffic_dirty = True


def _add_map(left, right, count_key):
    out = dict(left or {})
    for k, v in (right or {}).items():
        if not isinstance(v, dict):
            continue
        prev = out.get(k) or {}
        if not isinstance(prev, dict):
            prev = {}
        merged = dict(prev)
        merged[count_key] = int(prev.get(count_key) or 0) + int(v.get(count_key) or 0)
        merged["last"] = max(int(prev.get("last") or 0), int(v.get("last") or 0))
        for extra in ("href", "path"):
            if v.get(extra):
                merged[extra] = v[extra]
        out[k] = merged
    return out


def _add_days(left, right):
    days = dict(left or {})
    for k, v in (right or {}).items():
        if not isinstance(v, dict):
            continue
        prev = days.get(k) or {}
        days[k] = {
            "views": int(prev.get("views") or 0) + int(v.get("views") or 0),
            "clicks": int(prev.get("clicks") or 0) + int(v.get("clicks") or 0),
            "events": int(prev.get("events") or 0) + int(v.get("events") or 0),
        }
    return days


def _add_traffic(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    events = dict(a.get("events") or {})
    for k, n in (b.get("events") or {}).items():
        events[k] = int(events.get(k) or 0) + int(n or 0)
    return {
        "pages": _add_map(a.get("pages"), b.get("pages"), "views"),
        "clicks": _add_map(a.get("clicks"), b.get("clicks"), "count"),
        "events": events,
        "days": _add_days(a.get("days"), b.get("days")),
    }


def snapshot_api() -> Dict[str, Any]:
    """Merge this worker's memory with other workers' Spaces snapshots."""
    maybe_flush_api(force=True)
    workers = []
    try:
        workers = get_analytics_api_snapshots()
    except Exception:
        workers = []
    with _LOCK:
        current = {
            "worker": _WORKER_ID,
            "updated": int(time.time()),
            "started": int(_STARTED),
            "total": _api["total"],
            "errors": _api["errors"],
            "load_test": _api["load_test"],
            "routes": _api["routes"],
            "recent": list(_api["recent"]),
        }
    by_worker = {str(w.get("worker")): w for w in workers if isinstance(w, dict)}
    by_worker[_WORKER_ID] = current

    routes: Dict[str, Dict[str, Any]] = {}
    total = errors = load_test = 0
    recent: List[Dict[str, Any]] = []
    for w in by_worker.values():
        total += int(w.get("total") or 0)
        errors += int(w.get("errors") or 0)
        load_test += int(w.get("load_test") or 0)
        recent.extend(w.get("recent") or [])
        for route, rec in (w.get("routes") or {}).items():
            dst = routes.setdefault(route, {
                "count": 0, "total_time": 0.0, "min_time": None, "max_time": 0.0,
                "errors": 0, "statuses": {},
            })
            dst["count"] += int(rec.get("count") or 0)
            dst["total_time"] += float(rec.get("total_time") or 0)
            dst["errors"] += int(rec.get("errors") or 0)
            mn = rec.get("min_time")
            if mn is not None:
                dst["min_time"] = mn if dst["min_time"] is None else min(dst["min_time"], mn)
            dst["max_time"] = max(dst["max_time"], float(rec.get("max_time") or 0))
            for code, n in (rec.get("statuses") or {}).items():
                dst["statuses"][str(code)] = dst["statuses"].get(str(code), 0) + int(n)

    rows = []
    for route, rec in routes.items():
        count = rec["count"] or 1
        rows.append({
            "route": route,
            "requests": rec["count"],
            "errors": rec["errors"],
            "error_rate": round(rec["errors"] / count * 100, 2),
            "avg_ms": round((rec["total_time"] / count) * 1000, 1),
            "min_ms": round((rec["min_time"] or 0) * 1000, 1),
            "max_ms": round(rec["max_time"] * 1000, 1),
            "statuses": rec["statuses"],
        })
    rows.sort(key=lambda r: r["requests"], reverse=True)
    recent.sort(key=lambda r: r.get("t") or 0, reverse=True)
    return {
        "total_requests": total,
        "total_errors": errors,
        "load_test_requests": load_test,
        "workers": len(by_worker),
        "process_uptime_s": int(time.time() - _STARTED),
        "routes": rows[:200],
        "recent": recent[:60],
    }


def snapshot_traffic() -> Dict[str, Any]:
    maybe_flush_traffic(force=True)
    stored = {}
    try:
        stored = get_analytics_traffic() or {}
    except Exception:
        stored = {}
    with _LOCK:
        pending = {
            "pages": dict(_pending_traffic["pages"]),
            "clicks": dict(_pending_traffic["clicks"]),
            "events": dict(_pending_traffic["events"]),
            "days": dict(_pending_traffic["days"]),
        }
    merged = _add_traffic(stored, pending)
    pages = [
        {"path": k, "views": int(v.get("views") or 0), "last": int(v.get("last") or 0)}
        for k, v in (merged.get("pages") or {}).items() if isinstance(v, dict)
    ]
    pages.sort(key=lambda r: r["views"], reverse=True)
    clicks = [
        {
            "label": k,
            "count": int(v.get("count") or 0),
            "last": int(v.get("last") or 0),
            "href": v.get("href") or "",
            "path": v.get("path") or "",
        }
        for k, v in (merged.get("clicks") or {}).items() if isinstance(v, dict)
    ]
    clicks.sort(key=lambda r: r["count"], reverse=True)
    days = [
        {"day": k, **v}
        for k, v in sorted((merged.get("days") or {}).items(), reverse=True)
        if isinstance(v, dict)
    ]
    events = [
        {"event": k, "count": int(n)}
        for k, n in sorted((merged.get("events") or {}).items(), key=lambda kv: int(kv[1] or 0), reverse=True)
    ]
    return {
        "page_views_total": sum(p["views"] for p in pages),
        "clicks_total": sum(c["count"] for c in clicks),
        "pages": pages[:100],
        "clicks": clicks[:150],
        "events": events[:80],
        "days": days[:60],
    }
