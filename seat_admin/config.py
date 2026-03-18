import json
import runpy
from pathlib import Path

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

# Load root config.py (gitignored, holds all live credentials)
_root = runpy.run_path(str(Path(__file__).parent.parent / "config.py"))

_ABI_PATH = Path(__file__).parent / "abi" / "RSESeat.json"

NETWORK = _root.get("SEAT_NETWORK", "base_sepolia")
BASE_RPC_URL = _root.get("BASE_RPC_URL", "https://mainnet.base.org")
BASE_SEPOLIA_RPC_URL = _root.get("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org")
CONTRACT_ADDRESS = _root.get("RSE_SEAT_CONTRACT_ADDRESS", "")
OWNER_PRIVATE_KEY = str(_root.get("ETH_PRIVATE_KEY", ""))


def rpc_url() -> str:
    if NETWORK == "base":
        return BASE_RPC_URL
    return BASE_SEPOLIA_RPC_URL


def get_w3() -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc_url()))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to RPC: {rpc_url()}")
    return w3


def _load_abi() -> list:
    with open(_ABI_PATH) as f:
        return json.load(f)


def get_contract(w3: Web3 | None = None):
    if not CONTRACT_ADDRESS:
        raise ValueError("RSE_SEAT_CONTRACT_ADDRESS is not set in config.py")
    w3 = w3 or get_w3()
    return w3.eth.contract(
        address=Web3.to_checksum_address(CONTRACT_ADDRESS),
        abi=_load_abi(),
    )


def get_signer(w3: Web3 | None = None):
    if not OWNER_PRIVATE_KEY:
        raise ValueError("ETH_PRIVATE_KEY is not set in config.py")
    w3 = w3 or get_w3()
    account = w3.eth.account.from_key(OWNER_PRIVATE_KEY)
    return w3, account


def send_tx(w3: Web3, account, fn_call) -> dict:
    """Build, sign, send a transaction and wait for receipt."""
    tx = fn_call.build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": fn_call.estimate_gas({"from": account.address}),
        "gasPrice": w3.eth.gas_price,
    })
    signed = w3.eth.account.sign_transaction(tx, account.key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt
