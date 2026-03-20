"""
RSE Seat verification — reads from the ERC-721 contract on Base (Ethereum L2).

Architecture note
-----------------
The RSE API never sends transactions or spends ETH. Every blockchain interaction
here is a read-only `eth_call` (a Solidity `view` function). No gas is consumed,
no private key is needed, and the supplier never pays anything. The API just
reads "does this wallet hold a non-revoked seat?" from the Base RPC node.

Calls made per verification (all free eth_calls):
  isValidSeat(address)          — primary gate: owns any unrevoked seat?
  balanceOf(address)            — how many seats does the wallet hold?
  tokenOfOwnerByIndex(address)  — which token IDs does it own?
  isRevoked(tokenId)            — is a specific seat revoked?

Caching
-------
Results are cached in-process for CACHE_TTL seconds (default 15 min). This
matches the /grab_job rate limit — a seat can only grab one job per 15 min
anyway, so re-verifying on-chain within that window adds no value. The cache
eliminates RPC latency and rate-limit pressure on the public node for all
repeated calls within the window.

Call invalidate_cache(wallet) after a manual revoke/unrevoke to force immediate
re-verification on the next request.

Supplier wallet requirement
---------------------------
Suppliers link their wallet address once via POST /set_wallet. After that the
check is fully automatic. They never sign transactions through the RSE API —
only a wallet *address* is needed for reading, not a private key.
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

try:
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware
    _WEB3_AVAILABLE = True
except ImportError:
    _WEB3_AVAILABLE = False

import config

logger = logging.getLogger(__name__)

_ABI_PATH = Path(__file__).parent / "abi" / "RSESeat.json"

# ── Web3 / contract singletons (initialised on first call) ───────────────────
_w3 = None
_contract = None

# ── Result cache: wallet → {result, expires_at} ──────────────────────────────
CACHE_TTL = 900  # 15 minutes — matches /grab_job rate limit per seat
_cache: dict = {}
_cache_lock = threading.Lock()


def _get_contract():
    global _w3, _contract
    if _contract is not None:
        return _contract
    if not config.RSE_SEAT_CONTRACT_ADDRESS:
        raise ValueError("RSE_SEAT_CONTRACT_ADDRESS is not configured")
    with open(_ABI_PATH) as f:
        abi = json.load(f)
    _w3 = Web3(Web3.HTTPProvider(config.BASE_RPC_URL))
    _w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    _contract = _w3.eth.contract(
        address=Web3.to_checksum_address(config.RSE_SEAT_CONTRACT_ADDRESS),
        abi=abi,
    )
    return _contract


def normalize_address(address: str) -> Optional[str]:
    """Return EIP-55 checksum address, or None if invalid."""
    if not _WEB3_AVAILABLE:
        return None
    try:
        return Web3.to_checksum_address(address)
    except ValueError:
        return None


def invalidate_cache(wallet_address: str) -> None:
    """Remove a wallet from the cache, forcing a live RPC check on next call."""
    normalized = normalize_address(wallet_address)
    if normalized:
        with _cache_lock:
            _cache.pop(normalized, None)
        logger.info("Seat cache invalidated for %s", normalized)


def _live_verify(normalized: str) -> dict:
    """Make the actual eth_call(s) to the Base RPC node. All reads are free."""
    contract = _get_contract()

    is_valid: bool = contract.functions.isValidSeat(normalized).call()
    token_id: Optional[int] = None
    revoked = False

    balance: int = contract.functions.balanceOf(normalized).call()

    if is_valid:
        for i in range(balance):
            tid = contract.functions.tokenOfOwnerByIndex(normalized, i).call()
            if not contract.functions.isRevoked(tid).call():
                token_id = tid
                break
    elif balance > 0:
        token_id = contract.functions.tokenOfOwnerByIndex(normalized, 0).call()
        revoked = True

    return {"valid": is_valid, "token_id": token_id, "revoked": revoked, "error": None}


def verify_seat(wallet_address: str) -> dict:
    """
    Check whether a wallet holds a valid (non-revoked) RSE Seat NFT.

    Returns cached result if available and < CACHE_TTL seconds old.
    Falls back to a live eth_call (free, no gas) otherwise.

    Returns:
        {
            "valid":    bool,      # True if wallet owns an unrevoked seat
            "token_id": int|None,  # First relevant seat token ID (or None)
            "revoked":  bool,      # True if all owned seats are revoked
            "error":    str|None,  # Non-None on RPC/config failure (fails open)
        }
    """
    if not _WEB3_AVAILABLE:
        return {"valid": False, "token_id": None, "revoked": False,
                "error": "web3 package not installed"}

    normalized = normalize_address(wallet_address)
    if normalized is None:
        return {"valid": False, "token_id": None, "revoked": False,
                "error": f"Invalid Ethereum address: {wallet_address}"}

    if not config.RSE_SEAT_CONTRACT_ADDRESS:
        return {"valid": False, "token_id": None, "revoked": False,
                "error": "RSE_SEAT_CONTRACT_ADDRESS is not configured"}

    # ── Cache lookup ──────────────────────────────────────────────────────────
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(normalized)
        if entry and now < entry["expires_at"]:
            logger.debug("Seat cache hit for %s", normalized)
            return entry["result"]

    # ── Live RPC call (free eth_call, no gas) ─────────────────────────────────
    try:
        result = _live_verify(normalized)
    except Exception as exc:
        logger.warning("Seat verification RPC error for %s: %s", normalized, exc)
        # Fail open — don't block the marketplace on an RPC outage
        return {"valid": False, "token_id": None, "revoked": False, "error": str(exc)}

    # ── Cache the result ──────────────────────────────────────────────────────
    with _cache_lock:
        _cache[normalized] = {"result": result, "expires_at": now + CACHE_TTL}

    return result
