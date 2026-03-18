#!/usr/bin/env python3
"""Mint one or more RSE Seat NFTs to a single wallet address."""

import sys
import click
from web3 import Web3

import config


@click.command()
@click.argument("wallet_address")
@click.option("--count", "-n", default=1, show_default=True, help="Number of seats to mint")
def main(wallet_address: str, count: int):
    try:
        address = Web3.to_checksum_address(wallet_address)
    except ValueError:
        click.echo(f"Invalid address: {wallet_address}", err=True)
        sys.exit(1)

    seats_word = "seat" if count == 1 else "seats"
    if not click.confirm(f"Mint {count} {seats_word} to {address}?", default=False):
        click.echo("Aborted.")
        sys.exit(0)

    w3, account = config.get_signer()
    contract = config.get_contract(w3)

    if count == 1:
        receipt = config.send_tx(w3, account, contract.functions.mint(address))
        # Parse SeatMinted event to get token ID
        events = contract.events.SeatMinted().process_receipt(receipt)
        token_id = events[0]["args"]["tokenId"] if events else "?"
        click.echo(f"Minted seat #{token_id}")
    else:
        recipients = [address] * count
        receipt = config.send_tx(w3, account, contract.functions.mintBatch(recipients))
        events = contract.events.SeatMinted().process_receipt(receipt)
        ids = [str(e["args"]["tokenId"]) for e in events]
        click.echo(f"Minted seats: #{', #'.join(ids)}")

    click.echo(f"Tx hash:  {receipt['transactionHash'].hex()}")
    click.echo(f"Gas used: {receipt['gasUsed']:,}")


if __name__ == "__main__":
    main()
