#!/usr/bin/env python3
"""Mint one RSE Seat NFT to each address listed in a file (one per line)."""

import sys
import click
from web3 import Web3

import config


@click.command()
@click.argument("addresses_file", type=click.Path(exists=True))
def main(addresses_file: str):
    with open(addresses_file) as f:
        raw = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not raw:
        click.echo("No addresses found in file.", err=True)
        sys.exit(1)

    recipients = []
    for line in raw:
        try:
            recipients.append(Web3.to_checksum_address(line))
        except ValueError:
            click.echo(f"Invalid address skipped: {line}", err=True)

    if not recipients:
        click.echo("No valid addresses.", err=True)
        sys.exit(1)

    click.echo(f"Addresses loaded: {len(recipients)}")
    if not click.confirm(f"Mint {len(recipients)} seats via mintBatch()?", default=False):
        click.echo("Aborted.")
        sys.exit(0)

    w3, account = config.get_signer()
    contract = config.get_contract(w3)

    receipt = config.send_tx(w3, account, contract.functions.mintBatch(recipients))
    events = contract.events.SeatMinted().process_receipt(receipt)
    ids = [str(e["args"]["tokenId"]) for e in events]

    click.echo(f"Minted {len(ids)} seats: #{', #'.join(ids)}")
    click.echo(f"Tx hash:  {receipt['transactionHash'].hex()}")
    click.echo(f"Gas used: {receipt['gasUsed']:,}")


if __name__ == "__main__":
    main()
