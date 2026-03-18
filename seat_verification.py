"""
Minimal seat verification — reads from the RSE Seat ERC-721 contract on Base.

Uses web3.py to call isValidSeat(address) on the contract.
Config loaded from environment variables:
  RSE_SEAT_CONTRACT_ADDRESS
  BASE_RPC_URL (default: https://mainnet.base.org)
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

try:
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware
    _WEB3_AVAILABLE = True
except ImportError:
    _WEB3_AVAILABLE = False

logger = logging.getLogger(__name__)

_CONTRACT_ADDRESS = os.getenv("RSE_SEAT_CONTRACT_ADDRESS", "")
_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
_ABI_PATH = Path(__file__).parent / "abi" / "RSESeat.json"

# Module-level cached instances — initialized on first call
_w3 = None
_contract = None


def _get_contract():
    global _w3, _contract
    if _contract is not None:
        return _contract

    if not _CONTRACT_ADDRESS:
        raise ValueError("RSE_SEAT_CONTRACT_ADDRESS is not configured")

    with open(_ABI_PATH) as f:
        abi = json.load(f)

    _w3 = Web3(Web3.HTTPProvider(_RPC_URL))
    _w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    _contract = _w3.eth.contract(
        address=Web3.to_checksum_address(_CONTRACT_ADDRESS),
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


def verify_seat(wallet_address: str) -> dict:
    """
    Check whether a wallet holds a valid (non-revoked) RSE Seat NFT.

    Returns:
        {
            "valid":    bool,      # True if wallet owns an unrevoked seat
            "token_id": int|None,  # First relevant seat token ID (or None)
            "revoked":  bool,      # True if all owned seats are revoked
            "error":    str|None,  # Non-None on RPC/config failure
        }
    """
    if not _WEB3_AVAILABLE:
        return {"valid": False, "token_id": None, "revoked": False, "error": "web3 package not installed"}

    normalized = normalize_address(wallet_address)
    if normalized is None:
        return {
            "valid": False,
            "token_id": None,
            "revoked": False,
            "error": f"Invalid Ethereum address: {wallet_address}",
        }

    if not _CONTRACT_ADDRESS:
        return {
            "valid": False,
            "token_id": None,
            "revoked": False,
            "error": "RSE_SEAT_CONTRACT_ADDRESS is not configured",
        }

    try:
        contract = _get_contract()

        is_valid: bool = contract.functions.isValidSeat(normalized).call()
        token_id: Optional[int] = None
        revoked = False

        balance: int = contract.functions.balanceOf(normalized).call()

        if is_valid:
            # Find the first non-revoked seat to report its ID
            for i in range(balance):
                tid = contract.functions.tokenOfOwnerByIndex(normalized, i).call()
                if not contract.functions.isRevoked(tid).call():
                    token_id = tid
                    break
        elif balance > 0:
            # Has seats but all are revoked — report the first one
            token_id = contract.functions.tokenOfOwnerByIndex(normalized, 0).call()
            revoked = True

        return {"valid": is_valid, "token_id": token_id, "revoked": revoked, "error": None}

    except Exception as exc:
        logger.warning("Seat verification RPC error for %s: %s", wallet_address, exc)
        return {"valid": False, "token_id": None, "revoked": False, "error": str(exc)}
