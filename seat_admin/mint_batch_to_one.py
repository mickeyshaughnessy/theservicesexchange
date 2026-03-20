#!/usr/bin/env python3
"""Mint N seats to a single address in batches."""
import sys
import time
from web3 import Web3
import config

RECIPIENT = Web3.to_checksum_address(sys.argv[1])
COUNT      = int(sys.argv[2])
BATCH_SIZE = 100

def main():
    w3, account = config.get_signer()
    contract = config.get_contract(w3)

    supply_before = contract.functions.totalSupply().call()
    print(f"Minting {COUNT} seats to {RECIPIENT}")
    print(f"Seats #{supply_before + 1} – #{supply_before + COUNT}  |  {COUNT // BATCH_SIZE + (1 if COUNT % BATCH_SIZE else 0)} batches of up to {BATCH_SIZE}")
    print()

    remaining = COUNT
    total_gas  = 0
    minted     = []

    while remaining > 0:
        batch = [RECIPIENT] * min(BATCH_SIZE, remaining)
        batch_num = (COUNT - remaining) // BATCH_SIZE + 1
        total_batches = COUNT // BATCH_SIZE + (1 if COUNT % BATCH_SIZE else 0)
        print(f"Batch {batch_num}/{total_batches}: minting {len(batch)} seats...", end=" ", flush=True)

        receipt = config.send_tx(w3, account, contract.functions.mintBatch(batch))
        gas = receipt["gasUsed"]
        total_gas += gas

        events = contract.events.SeatMinted().process_receipt(receipt)
        ids = [e["args"]["tokenId"] for e in events]
        minted.extend(ids)

        print(f"#{ids[0]}–#{ids[-1]}  gas: {gas:,}  tx: {receipt['transactionHash'].hex()[:16]}...")
        remaining -= len(batch)
        if remaining > 0:
            time.sleep(2)

    supply_after = contract.functions.totalSupply().call()
    print()
    print(f"Done. Minted seats #{minted[0]}–#{minted[-1]} to {RECIPIENT}")
    print(f"Total supply: {supply_after}")
    print(f"Total gas:    {total_gas:,}")

if __name__ == "__main__":
    main()
