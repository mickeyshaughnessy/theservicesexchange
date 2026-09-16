"""
Centrally managed RSE seats.

Mickey Shaughnessy is the registrar: assign, transfer, and revoke live in an
Exchange registry (DigitalOcean Spaces), not a chain. Seats are fully
transferable — transfer means Mickey updates the book. Grab-job enforcement is
still gated by config.SEAT_VERIFICATION_ENABLED (off by default).
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

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

_SEAT_CONTACT = "Message Mickey Shaughnessy (call or SMS +1 530 219 0940, or email therobotservicesexchange@proton.me) to get or transfer a seat."


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


def _owner_list(index: Dict[str, Any], username: str) -> List[int]:
    raw = (index.get("by_owner") or {}).get(username) or []
    out = []
    for item in raw:
        sid = parse_seat_id(item)
        if sid is not None:
            out.append(sid)
    return out


def _set_owner_list(index: Dict[str, Any], username: str, ids: List[int]) -> None:
    by_owner = index.setdefault("by_owner", {})
    unique = sorted(set(ids))
    if unique:
        by_owner[username] = unique
    else:
        by_owner.pop(username, None)


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
    revoked_only = owned and not active
    primary = (active[0] if active else (owned[0] if owned else None))
    if primary:
        sid = primary["seat_id"]
        user["seat_id"] = sid
        user["seat_token_id"] = sid  # legacy field on jobs/portfolios
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
    """Re-read the registry onto the account. Returns seat snapshot for API responses."""
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


def list_seats() -> Dict[str, Any]:
    rows = list_seat_summaries()
    return {
        "seats": rows,
        "count": len(rows),
        "active": sum(1 for r in rows if r.get("status") == "active"),
        "revoked": sum(1 for r in rows if r.get("status") == "revoked"),
        "note": "Mickey Shaughnessy assigns and transfers seats. " + _SEAT_CONTACT,
    }


def _new_record(seat_id: int, owner: str, admin: str, now: int, *, from_owner: Optional[str] = None) -> Dict[str, Any]:
    rec = {
        "seat_id": seat_id,
        "owner_username": owner,
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
    return rec


def assign_seat(username: str, *, seat_id: Optional[int] = None, admin: str = "mickey") -> Tuple[Dict[str, Any], int]:
    username = (username or "").strip()
    if not username:
        return {"error": "username required"}, 400
    dest = get_account(username)
    if not dest:
        return {"error": f"Account '{username}' not found"}, 404

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
        if existing and existing.get("owner") and existing.get("owner") != username:
            return {
                "error": f"Seat {seat_id} is held by {existing.get('owner')}. Use transfer.",
            }, 409

    prev = get_seat_record(seat_id, force_refresh=True) or {}
    rec = prev if prev else _new_record(seat_id, username, admin, now)
    rec["seat_id"] = seat_id
    rec["owner_username"] = username
    rec["status"] = rec.get("status") or "active"
    rec["assigned_at"] = rec.get("assigned_at") or now
    rec["assigned_by"] = rec.get("assigned_by") or admin
    if not prev:
        rec["history"] = rec.get("history") or []
    else:
        hist = list(rec.get("history") or [])
        hist.append({"op": "assign", "at": now, "by": admin, "from": prev.get("owner_username"), "to": username})
        rec["history"] = hist[-50:]
    save_seat_record(seat_id, rec)
    _index_put(index, seat_id, username, rec["status"])
    save_seats_index(index)
    _sync_account(username)
    logger.info("Seat %s assigned to %s by %s", seat_id, username, admin)
    return {"message": "Seat assigned", "seat": rec, "note": _SEAT_CONTACT}, 200


def transfer_seat(seat_id: int, to_username: str, *, admin: str = "mickey") -> Tuple[Dict[str, Any], int]:
    to_username = (to_username or "").strip()
    seat_id = parse_seat_id(seat_id)
    if seat_id is None:
        return {"error": "seat_id must be a positive integer"}, 400
    if not to_username:
        return {"error": "to_username required"}, 400
    dest = get_account(to_username)
    if not dest:
        return {"error": f"Account '{to_username}' not found"}, 404

    index = get_seats_index(force_refresh=True)
    meta = (index.get("seats") or {}).get(str(seat_id))
    if not meta:
        return {"error": f"Seat {seat_id} does not exist"}, 404
    from_owner = meta.get("owner")
    if from_owner == to_username:
        return {"message": "Already the holder", "seat_id": seat_id, "owner_username": to_username}, 200

    now = int(time.time())
    rec = get_seat_record(seat_id, force_refresh=True) or _new_record(seat_id, to_username, admin, now, from_owner=from_owner)
    rec["owner_username"] = to_username
    rec["transferred_at"] = now
    rec["transferred_from"] = from_owner
    rec["status"] = rec.get("status") or "active"
    hist = list(rec.get("history") or [])
    hist.append({"op": "transfer", "at": now, "by": admin, "from": from_owner, "to": to_username})
    rec["history"] = hist[-50:]
    save_seat_record(seat_id, rec)
    _index_put(index, seat_id, to_username, rec["status"])
    save_seats_index(index)
    if from_owner:
        _sync_account(from_owner)
    _sync_account(to_username)
    logger.info("Seat %s transferred %s -> %s by %s", seat_id, from_owner, to_username, admin)
    return {
        "message": "Seat transferred",
        "seat": rec,
        "from_username": from_owner,
        "to_username": to_username,
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
    return {"message": "Seat revoked" if revoked else "Seat restored", "seat": rec}, 200


def owner_for_seat(seat_id: int) -> Optional[str]:
    sid = parse_seat_id(seat_id)
    if sid is None:
        return None
    meta = (get_seats_index().get("seats") or {}).get(str(sid)) or {}
    return meta.get("owner")
