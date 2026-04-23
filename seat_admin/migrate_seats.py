"""
Seat migration tool for the RSESeat V2 (soulbound) contract.

Phase 1 (--phase read):
  Reads all seat holders and revocation status from the OLD contract and
  writes migration_manifest.json to this directory.

Phase 2 (--phase write):
  Reads migration_manifest.json and re-mints every seat on the NEW contract,
  then re-revokes any that were revoked on the old contract.

Usage:
  python migrate_seats.py --phase read
  python migrate_seats.py --phase write --new-address 0xNEW_CONTRACT_ADDRESS
"""

import argparse
import json
import sys
import time
from pathlib import Path

from web3 import Web3

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

MANIFEST_PATH = Path(__file__).parent / "migration_manifest.json"
ABI_PATH = Path(__file__).parent / "abi" / "RSESeat.json"


def load_abi():
    with open(ABI_PATH) as f:
        return json.load(f)


def get_w3():
    rpc = config.BASE_RPC_URL if config.NETWORK == "base" else config.BASE_SEPOLIA_RPC_URL
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        raise SystemExit(f"Cannot connect to RPC: {rpc}")
    return w3


def phase_read(old_address: str):
    print(f"[read] Connecting to old contract at {old_address} ...")
    w3 = get_w3()
    abi = load_abi()
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(old_address),
        abi=abi,
    )

    total = contract.functions.totalSupply().call()
    print(f"[read] Total supply: {total}")

    seats = []
    for token_id in range(1, total + 1):
        for attempt in range(5):
            try:
                owner = contract.functions.ownerOf(token_id).call()
                revoked = contract.functions.isRevoked(token_id).call()
                break
            except Exception as e:
                if attempt == 4:
                    raise
                wait = 2 ** attempt
                print(f"  #{token_id} RPC error ({e}), retrying in {wait}s...")
                time.sleep(wait)
        seats.append({"token_id": token_id, "owner": owner, "revoked": revoked})
        print(f"  #{token_id:>4}  {owner}  {'REVOKED' if revoked else 'valid'}")
        time.sleep(0.25)

    manifest = {
        "old_contract": old_address,
        "network": config.NETWORK,
        "total": total,
        "seats": seats,
    }
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n[read] Manifest written to {MANIFEST_PATH}")


def send_tx(w3, fn, account):
    nonce = w3.eth.get_transaction_count(account.address)
    tx = fn.build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 5_000_000,
        "gasPrice": w3.eth.gas_price,
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt["status"] != 1:
        raise RuntimeError(f"Transaction failed: {tx_hash.hex()}")
    return tx_hash.hex()


def phase_write(new_address: str):
    if not MANIFEST_PATH.exists():
        raise SystemExit("migration_manifest.json not found — run --phase read first")

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    print(f"[write] Deploying to new contract at {new_address} ...")
    w3 = get_w3()
    abi = load_abi()
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(new_address),
        abi=abi,
    )
    account = w3.eth.account.from_key(config.ETH_PRIVATE_KEY)
    print(f"[write] Sending from {account.address}")

    seats = manifest["seats"]

    # Mint in batches of 50 to stay within gas limits
    BATCH_SIZE = 50
    recipients = [s["owner"] for s in seats]
    for start in range(0, len(recipients), BATCH_SIZE):
        batch = recipients[start:start + BATCH_SIZE]
        ids = list(range(start + 1, start + len(batch) + 1))
        print(f"[write] mintBatch tokens {ids[0]}–{ids[-1]} ({len(batch)} seats) ...")
        tx = send_tx(w3, contract.functions.mintBatch(batch), account)
        print(f"  tx: {tx}")
        time.sleep(2)

    # Re-revoke any seats that were revoked on the old contract
    revoked_ids = [s["token_id"] for s in seats if s["revoked"]]
    if revoked_ids:
        print(f"\n[write] Revoking {len(revoked_ids)} seats: {revoked_ids}")
        for token_id in revoked_ids:
            print(f"  revoking #{token_id} ...")
            tx = send_tx(w3, contract.functions.revoke(token_id), account)
            print(f"  tx: {tx}")
            time.sleep(1)
    else:
        print("\n[write] No seats to revoke.")

    print("\n[write] Migration complete.")
    print(f"  New contract: {new_address}")
    print(f"  Seats minted: {len(seats)}")
    print(f"  Seats revoked: {len(revoked_ids)}")
    print("\nNext steps:")
    print("  1. Update RSE_SEAT_CONTRACT_ADDRESS in config.py")
    print("  2. Update ABI files in seat_admin/abi/")
    print("  3. Verify with: python check.py <wallet_address>")


def main():
    parser = argparse.ArgumentParser(description="RSESeat migration tool")
    parser.add_argument("--phase", choices=["read", "write"], required=True)
    parser.add_argument("--new-address", help="New contract address (required for --phase write)")
    parser.add_argument(
        "--old-address",
        default=config.RSE_SEAT_CONTRACT_ADDRESS,
        help="Old contract address (default: from config.py)",
    )
    args = parser.parse_args()

    if args.phase == "read":
        phase_read(args.old_address)
    elif args.phase == "write":
        if not args.new_address:
            raise SystemExit("--new-address is required for --phase write")
        phase_write(args.new_address)


if __name__ == "__main__":
    main()
