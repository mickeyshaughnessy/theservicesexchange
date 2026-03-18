#!/usr/bin/env python3
"""Mint RSE Seats #2-#100 in batches of 20 to the contract owner address."""

import sys
import time
from web3 import Web3
import config

OWNER = "0x6B2D765cfB33Aa5736e96231eD078f9D01917A03"
BATCH_SIZE = 20

def main():
    w3, account = config.get_signer()
    contract = config.get_contract(w3)

    supply_before = contract.functions.totalSupply().call()
    print(f"Total supply before: {supply_before}")
    print(f"Minting seats {supply_before + 1} through 100 in batches of {BATCH_SIZE}")
    print(f"Target address: {OWNER}")
    print()

    recipients = [Web3.to_checksum_address(OWNER)] * (100 - supply_before)
    batches = [recipients[i:i+BATCH_SIZE] for i in range(0, len(recipients), BATCH_SIZE)]

    total_gas = 0
    minted_ids = []

    for idx, batch in enumerate(batches, 1):
        print(f"Batch {idx}/{len(batches)}: minting {len(batch)} seats...")
        receipt = config.send_tx(w3, account, contract.functions.mintBatch(batch))
        gas = receipt["gasUsed"]
        total_gas += gas

        events = contract.events.SeatMinted().process_receipt(receipt)
        ids = [e["args"]["tokenId"] for e in events]
        minted_ids.extend(ids)

        first, last = ids[0] if ids else "?", ids[-1] if ids else "?"
        print(f"  Minted #{first} – #{last}  |  gas: {gas:,}  |  tx: {receipt['transactionHash'].hex()}")

        if idx < len(batches):
            time.sleep(2)

    print()
    print(f"Done. Minted {len(minted_ids)} seats (#{minted_ids[0]} – #{minted_ids[-1]})")
    supply_after = contract.functions.totalSupply().call()
    print(f"Total supply now: {supply_after}")
    print(f"Total gas used:   {total_gas:,}")

if __name__ == "__main__":
    main()
