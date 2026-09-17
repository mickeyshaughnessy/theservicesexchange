"""
Centrally managed RSE seats.

Mickey Shaughnessy is the registrar. A seat is (number, owner, phrase). The
phrase never goes on the wire: /grab_job presents seat number, owner name, and
SHA-256(phrase + "|" + UTC date). Software bots (location_type=remote) skip the
gate. Grab-job enforcement is still config.SEAT_VERIFICATION_ENABLED (off).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from utils import (
    get_account,
    get_seat_record,
    get_seats_index,
    list_seat_summaries,
    save_account,
    save_seat_record,
    save_seats_index,
)

logger = logging.getLogger(__name__)

_SEAT_CONTACT = (
    "Message Mickey Shaughnessy (call or SMS +1 530 219 0940, or email "
    "therobotservicesexchange@proton.me) to get or transfer a seat."
)

FOUNDING_TRANCHES: Tuple[Tuple[int, int, str], ...] = (
    (1, 1000, "Dr. Aftab"),
    (1001, 11000, "Amanda Jean"),
)

_WORDLIST: Optional[List[str]] = None
_WORDLIST_PATH = Path(__file__).resolve().parent / "seat_admin" / "bip39_english.txt"
_PROOF_SEP = "|"
_UPLOAD_WORKERS = 8


def parse_seat_id(raw: Any) -> Optional[int]:
    try:
        sid = int(raw)
    except (TypeError, ValueError):
        return None
    if sid < 1:
        return None
    return sid


def account_seat_id(user: Optional[Dict[str, Any]]) -> Optional[int]:
    if not user:
        return None
    for key in ("seat_id", "seat_token_id"):
        sid = parse_seat_id(user.get(key))
        if sid is not None:
            return sid
    return None


def normalize_owner(raw: Any) -> str:
    return " ".join(str(raw or "").split())


def owners_match(a: Any, b: Any) -> bool:
    return normalize_owner(a).casefold() == normalize_owner(b).casefold() and bool(normalize_owner(a))


def _owner_list(index: Dict[str, Any], owner: str) -> List[int]:
    raw = (index.get("by_owner") or {}).get(owner) or []
    out = []
    for item in raw:
        sid = parse_seat_id(item)
        if sid is not None:
            out.append(sid)
    return out


def _set_owner_list(index: Dict[str, Any], owner: str, ids: List[int]) -> None:
    by_owner = index.setdefault("by_owner", {})
    unique = sorted(set(ids))
    if unique:
        by_owner[owner] = unique
    else:
        by_owner.pop(owner, None)


def _index_put(index: Dict[str, Any], seat_id: int, owner: str, status: str) -> None:
    seats = index.setdefault("seats", {})
    prev = seats.get(str(seat_id)) or {}
    prev_owner = prev.get("owner")
    if prev_owner and prev_owner != owner:
        _set_owner_list(index, prev_owner, [i for i in _owner_list(index, prev_owner) if i != seat_id])
    seats[str(seat_id)] = {"owner": owner, "status": status}
    ids = _owner_list(index, owner)
    if seat_id not in ids:
        ids.append(seat_id)
    _set_owner_list(index, owner, ids)
    next_id = parse_seat_id(index.get("next_id")) or 1
    if seat_id >= next_id:
        index["next_id"] = seat_id + 1


def _sync_account(username: Optional[str]) -> None:
    if not username:
        return
    user = get_account(username)
    if not user:
        return
    index = get_seats_index(force_refresh=True)
    owned = []
    for sid in _owner_list(index, username):
        meta = (index.get("seats") or {}).get(str(sid)) or {}
        owned.append({"seat_id": sid, "status": meta.get("status") or "active"})
    active = [s for s in owned if s["status"] == "active"]
    primary = (active[0] if active else (owned[0] if owned else None))
    if primary:
        sid = primary["seat_id"]
        user["seat_id"] = sid
        user["seat_token_id"] = sid
        if primary["status"] == "active":
            user["seat_active"] = True
            user["seat_status_cached"] = "valid"
        else:
            user["seat_active"] = False
            user["seat_status_cached"] = "revoked"
    else:
        user.pop("seat_id", None)
        user.pop("seat_token_id", None)
        user["seat_active"] = False
        user["seat_status_cached"] = "no_seat"
    user["seats"] = owned
    save_account(username, user)


def refresh_account_seat(username: str, user_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Re-read the registry onto the account if the owner string is a username."""
    _sync_account(username)
    user = user_data if user_data is not None else get_account(username) or {}
    if user_data is not None:
        fresh = get_account(username, force_refresh=True) or {}
        for k in ("seat_id", "seat_token_id", "seat_active", "seat_status_cached", "seats"):
            if k in fresh:
                user_data[k] = fresh[k]
            elif k in user_data and k in ("seat_id", "seat_token_id"):
                user_data.pop(k, None)
        user = user_data
    sid = account_seat_id(user)
    status = user.get("seat_status_cached") or "no_seat"
    return {
        "seat_id": sid,
        "seat_status": status,
        "seat_active": bool(user.get("seat_active")),
        "seats": user.get("seats") or [],
    }


def public_seat_view(rec: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not rec:
        return None
    return {
        "seat_id": rec.get("seat_id"),
        "owner": rec.get("owner") or rec.get("owner_username"),
        "status": rec.get("status") or "active",
        "assigned_at": rec.get("assigned_at"),
        "transferred_at": rec.get("transferred_at"),
        "transferred_from": rec.get("transferred_from"),
    }


def list_seats(*, owner: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
    rows = list_seat_summaries()
    for r in rows:
        r["owner"] = r.get("owner") or r.get("owner_username")
        r["owner_username"] = r.get("owner")
    by_owner: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        name = r.get("owner") or ""
        bucket = by_owner.setdefault(name, {"owner": name, "count": 0, "active": 0, "revoked": 0})
        bucket["count"] += 1
        if r.get("status") == "revoked":
            bucket["revoked"] += 1
        else:
            bucket["active"] += 1
    owner_norm = normalize_owner(owner) if owner else ""
    filtered = [r for r in rows if owners_match(r.get("owner"), owner_norm)] if owner_norm else rows
    try:
        cap = max(0, int(limit))
    except (TypeError, ValueError):
        cap = 200
    listed = filtered[:cap]
    return {
        "seats": listed,
        "count": len(filtered),
        "active": sum(1 for r in filtered if r.get("status") == "active"),
        "revoked": sum(1 for r in filtered if r.get("status") == "revoked"),
        "by_owner": sorted(by_owner.values(), key=lambda b: (-b["count"], b["owner"] or "")),
        "listed": len(listed),
        "note": "Mickey Shaughnessy assigns and transfers seats. " + _SEAT_CONTACT,
    }


def load_bip39_wordlist() -> List[str]:
    global _WORDLIST
    if _WORDLIST is not None:
        return _WORDLIST
    text = _WORDLIST_PATH.read_text(encoding="utf-8")
    words = [w.strip() for w in text.splitlines() if w.strip()]
    if len(words) != 2048:
        raise RuntimeError(f"BIP39 wordlist must have 2048 words, got {len(words)}")
    _WORDLIST = words
    return words


def generate_phrase() -> str:
    """12-word BIP39 mnemonic (128 bits of entropy)."""
    words = load_bip39_wordlist()
    entropy = secrets.token_bytes(16)
    checksum_nibble = hashlib.sha256(entropy).digest()[0] >> 4
    bits = (int.from_bytes(entropy, "big") << 4) | checksum_nibble
    out = []
    for i in range(12):
        idx = (bits >> (11 * (11 - i))) & 0x7FF
        out.append(words[idx])
    return " ".join(out)


def utc_today(now: Optional[datetime] = None) -> date:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    return now.date()


def daily_proof(phrase: str, day: date) -> str:
    material = f"{phrase}{_PROOF_SEP}{day.isoformat()}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def proof_matches(phrase: str, secret: str, now: Optional[datetime] = None) -> bool:
    if not phrase or not secret:
        return False
    got = str(secret).strip().lower()
    if len(got) != 64:
        return False
    today = utc_today(now)
    for delta in (-1, 0, 1):
        expected = daily_proof(phrase, today + timedelta(days=delta))
        if hmac.compare_digest(got, expected):
            return True
    return False


def extract_seat_proof(data: Optional[Dict[str, Any]]) -> Tuple[Optional[int], str, str, Optional[str]]:
    data = data or {}
    nested = data.get("seat") if isinstance(data.get("seat"), dict) else {}
    sid = parse_seat_id(
        nested.get("id")
        if nested.get("id") not in (None, "")
        else nested.get("seat_id")
        if nested.get("seat_id") not in (None, "")
        else data.get("seat_id")
    )
    owner = normalize_owner(nested.get("owner") or data.get("owner") or data.get("seat_owner"))
    secret = str(
        nested.get("secret")
        or nested.get("proof")
        or data.get("secret")
        or data.get("seat_secret")
        or ""
    ).strip()
    if sid is None or not owner or not secret:
        return sid, owner, secret, (
            "Seat proof required: seat.id, seat.owner, and seat.secret "
            "(SHA-256 hex of phrase|YYYY-MM-DD in UTC)."
        )
    return sid, owner, secret, None


def seat_required_for_grab(location_type: Optional[str]) -> bool:
    return (location_type or "physical").strip().lower() != "remote"


def verify_grab_proof(
    data: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    sid, owner, secret, missing = extract_seat_proof(data)
    if missing:
        return False, missing, None
    rec = get_seat_record(sid, force_refresh=True)
    if not rec:
        return False, f"Seat {sid} does not exist", None
    if (rec.get("status") or "active") == "revoked":
        return False, f"Seat {sid} is revoked", rec
    stored_owner = rec.get("owner") or rec.get("owner_username")
    if not owners_match(owner, stored_owner):
        return False, "Seat owner does not match", rec
    phrase = rec.get("phrase") or ""
    if not proof_matches(phrase, secret, now=now):
        return False, "Invalid seat secret", rec
    return True, "Seat verified", rec


def _new_record(seat_id: int, owner: str, admin: str, now: int, *, phrase: str,
                from_owner: Optional[str] = None) -> Dict[str, Any]:
    return {
        "seat_id": seat_id,
        "owner": owner,
        "owner_username": owner,
        "phrase": phrase,
        "status": "active",
        "assigned_at": now,
        "assigned_by": admin,
        "transferred_at": now if from_owner else None,
        "transferred_from": from_owner,
        "history": [{
            "op": "transfer" if from_owner else "assign",
            "at": now,
            "by": admin,
            "from": from_owner,
            "to": owner,
        }],
    }


def assign_seat(owner: str, *, seat_id: Optional[int] = None, admin: str = "mickey") -> Tuple[Dict[str, Any], int]:
    owner = normalize_owner(owner)
    if not owner:
        return {"error": "owner required"}, 400

    index = get_seats_index(force_refresh=True)
    now = int(time.time())
    if seat_id is None:
        seat_id = parse_seat_id(index.get("next_id")) or 1
        while str(seat_id) in (index.get("seats") or {}):
            seat_id += 1
    else:
        seat_id = parse_seat_id(seat_id)
        if seat_id is None:
            return {"error": "seat_id must be a positive integer"}, 400
        existing = (index.get("seats") or {}).get(str(seat_id))
        if existing and existing.get("owner") and not owners_match(existing.get("owner"), owner):
            return {
                "error": f"Seat {seat_id} is held by {existing.get('owner')}. Use transfer.",
            }, 409

    prev = get_seat_record(seat_id, force_refresh=True) or {}
    phrase = prev.get("phrase") or generate_phrase()
    if prev:
        rec = prev
        rec["seat_id"] = seat_id
        rec["owner"] = owner
        rec["owner_username"] = owner
        rec["phrase"] = phrase
        rec["status"] = rec.get("status") or "active"
        rec["assigned_at"] = rec.get("assigned_at") or now
        rec["assigned_by"] = rec.get("assigned_by") or admin
        hist = list(rec.get("history") or [])
        hist.append({"op": "assign", "at": now, "by": admin, "from": prev.get("owner"), "to": owner})
        rec["history"] = hist[-50:]
        new_phrase = False
    else:
        rec = _new_record(seat_id, owner, admin, now, phrase=phrase)
        new_phrase = True
    save_seat_record(seat_id, rec)
    _index_put(index, seat_id, owner, rec["status"])
    save_seats_index(index)
    _sync_account(owner)
    logger.info("Seat %s assigned to %s by %s", seat_id, owner, admin)
    body = {
        "message": "Seat assigned",
        "seat": public_seat_view(rec),
        "note": _SEAT_CONTACT,
    }
    if new_phrase:
        body["phrase"] = phrase
        body["phrase_note"] = (
            "Store this phrase privately. /grab_job sends SHA-256(phrase|YYYY-MM-DD UTC), never the phrase."
        )
    return body, 200


def transfer_seat(seat_id: int, to_owner: str, *, admin: str = "mickey") -> Tuple[Dict[str, Any], int]:
    to_owner = normalize_owner(to_owner)
    seat_id = parse_seat_id(seat_id)
    if seat_id is None:
        return {"error": "seat_id must be a positive integer"}, 400
    if not to_owner:
        return {"error": "to_owner required"}, 400

    index = get_seats_index(force_refresh=True)
    meta = (index.get("seats") or {}).get(str(seat_id))
    if not meta:
        return {"error": f"Seat {seat_id} does not exist"}, 404
    from_owner = meta.get("owner")
    if owners_match(from_owner, to_owner):
        return {"message": "Already the holder", "seat_id": seat_id, "owner": to_owner}, 200

    now = int(time.time())
    rec = get_seat_record(seat_id, force_refresh=True) or _new_record(
        seat_id, to_owner, admin, now, phrase=generate_phrase(), from_owner=from_owner,
    )
    rec["owner"] = to_owner
    rec["owner_username"] = to_owner
    rec["transferred_at"] = now
    rec["transferred_from"] = from_owner
    rec["status"] = rec.get("status") or "active"
    rec["phrase"] = rec.get("phrase") or generate_phrase()
    hist = list(rec.get("history") or [])
    hist.append({"op": "transfer", "at": now, "by": admin, "from": from_owner, "to": to_owner})
    rec["history"] = hist[-50:]
    save_seat_record(seat_id, rec)
    _index_put(index, seat_id, to_owner, rec["status"])
    save_seats_index(index)
    if from_owner:
        _sync_account(from_owner)
    _sync_account(to_owner)
    logger.info("Seat %s transferred %s -> %s by %s", seat_id, from_owner, to_owner, admin)
    return {
        "message": "Seat transferred",
        "seat": public_seat_view(rec),
        "from_owner": from_owner,
        "to_owner": to_owner,
        "from_username": from_owner,
        "to_username": to_owner,
    }, 200


def set_seat_revoked(seat_id: int, revoked: bool, *, admin: str = "mickey") -> Tuple[Dict[str, Any], int]:
    seat_id = parse_seat_id(seat_id)
    if seat_id is None:
        return {"error": "seat_id must be a positive integer"}, 400
    index = get_seats_index(force_refresh=True)
    meta = (index.get("seats") or {}).get(str(seat_id))
    if not meta:
        return {"error": f"Seat {seat_id} does not exist"}, 404
    owner = meta.get("owner")
    now = int(time.time())
    rec = get_seat_record(seat_id, force_refresh=True) or {
        "seat_id": seat_id,
        "owner": owner,
        "owner_username": owner,
        "history": [],
    }
    rec["status"] = "revoked" if revoked else "active"
    hist = list(rec.get("history") or [])
    hist.append({"op": "revoke" if revoked else "unrevoke", "at": now, "by": admin, "to": owner})
    rec["history"] = hist[-50:]
    save_seat_record(seat_id, rec)
    _index_put(index, seat_id, owner, rec["status"])
    save_seats_index(index)
    if owner:
        _sync_account(owner)
    return {"message": "Seat revoked" if revoked else "Seat restored", "seat": public_seat_view(rec)}, 200


def owner_for_seat(seat_id: int) -> Optional[str]:
    sid = parse_seat_id(seat_id)
    if sid is None:
        return None
    meta = (get_seats_index().get("seats") or {}).get(str(sid)) or {}
    return meta.get("owner")


def get_seat_admin_view(seat_id: int) -> Tuple[Dict[str, Any], int]:
    sid = parse_seat_id(seat_id)
    if sid is None:
        return {"error": "seat_id must be a positive integer"}, 400
    rec = get_seat_record(sid, force_refresh=True)
    if not rec:
        return {"error": f"Seat {sid} does not exist"}, 404
    out = dict(rec)
    return {"seat": out, "note": "Phrase is private. Do not paste it into /grab_job."}, 200


def export_seats_for_owner(owner: str) -> Tuple[Dict[str, Any], int]:
    owner = normalize_owner(owner)
    if not owner:
        return {"error": "owner required"}, 400
    index = get_seats_index(force_refresh=True)
    ids = _owner_list(index, owner)
    # Index keys are exact owner strings; also scan if casing differs.
    if not ids:
        for name, raw_ids in (index.get("by_owner") or {}).items():
            if owners_match(name, owner):
                ids = [parse_seat_id(i) for i in raw_ids]
                ids = [i for i in ids if i is not None]
                owner = name
                break
    seats = []
    for sid in ids:
        rec = get_seat_record(sid) or {}
        seats.append({
            "seat_id": sid,
            "owner": rec.get("owner") or owner,
            "status": rec.get("status") or "active",
            "phrase": rec.get("phrase") or "",
        })
    return {"owner": owner, "count": len(seats), "seats": seats}, 200


def _upload_record(rec: Dict[str, Any]) -> Optional[int]:
    sid = rec["seat_id"]
    if not save_seat_record(sid, rec):
        return sid
    return None


def issue_range(start: int, end: int, owner: str, *, admin: str = "mickey",
                skip_existing: bool = True) -> Dict[str, Any]:
    """Create seats start..end inclusive. Returns issued records (with phrases)."""
    owner = normalize_owner(owner)
    if not owner:
        raise ValueError("owner required")
    start = parse_seat_id(start)
    end = parse_seat_id(end)
    if start is None or end is None or end < start:
        raise ValueError("invalid seat range")

    index = get_seats_index(force_refresh=True)
    now = int(time.time())
    to_write: List[Dict[str, Any]] = []
    skipped = 0
    for sid in range(start, end + 1):
        existing_meta = (index.get("seats") or {}).get(str(sid))
        if skip_existing and existing_meta:
            skipped += 1
            continue
        rec = _new_record(sid, owner, admin, now, phrase=generate_phrase())
        to_write.append(rec)

    failed: List[int] = []
    if to_write:
        with ThreadPoolExecutor(max_workers=_UPLOAD_WORKERS) as pool:
            futures = {pool.submit(_upload_record, rec): rec["seat_id"] for rec in to_write}
            for fut in as_completed(futures):
                err_id = fut.result()
                if err_id is not None:
                    failed.append(err_id)

    if failed:
        retry = [r for r in to_write if r["seat_id"] in set(failed)]
        failed = []
        for rec in retry:
            err_id = _upload_record(rec)
            if err_id is not None:
                failed.append(err_id)

    for rec in to_write:
        if rec["seat_id"] not in failed:
            _index_put(index, rec["seat_id"], owner, rec["status"])
    save_seats_index(index)

    issued = [r for r in to_write if r["seat_id"] not in failed]
    logger.info(
        "Issued seats %s-%s to %s: wrote %s, skipped %s, failed %s",
        start, end, owner, len(issued), skipped, len(failed),
    )
    return {
        "owner": owner,
        "start": start,
        "end": end,
        "issued": len(issued),
        "skipped": skipped,
        "failed": failed,
        "seats": issued,
    }


def issue_founding_seats(*, admin: str = "mickey") -> Dict[str, Any]:
    tranches = []
    for start, end, owner in FOUNDING_TRANCHES:
        tranches.append(issue_range(start, end, owner, admin=admin, skip_existing=True))
    return {
        "tranches": tranches,
        "issued": sum(t["issued"] for t in tranches),
        "skipped": sum(t["skipped"] for t in tranches),
        "failed": [sid for t in tranches for sid in t["failed"]],
    }


def write_owner_export(path: Path, seats: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in seats:
            fh.write(json_line(rec) + "\n")


def json_line(rec: Dict[str, Any]) -> str:
    return json.dumps({
        "seat_id": rec.get("seat_id"),
        "owner": rec.get("owner"),
        "phrase": rec.get("phrase"),
        "status": rec.get("status") or "active",
    }, separators=(",", ":"))
