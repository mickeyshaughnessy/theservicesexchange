#!/usr/bin/env python3
"""Check whether a wallet holds a valid (non-revoked) RSE Seat NFT."""

import sys
import click
from web3 import Web3

import config


@click.command()
@click.argument("wallet_address")
def main(wallet_address: str):
    try:
        address = Web3.to_checksum_address(wallet_address)
    except ValueError:
        click.echo(f"Invalid address: {wallet_address}", err=True)
        sys.exit(1)

    w3 = config.get_w3()
    contract = config.get_contract(w3)

    balance = contract.functions.balanceOf(address).call()
    if balance == 0:
        click.echo(f"INVALID — No seats  ({address})")
        sys.exit(0)

    seats = []
    for i in range(balance):
        token_id = contract.functions.tokenOfOwnerByIndex(address, i).call()
        revoked = contract.functions.isRevoked(token_id).call()
        seats.append((token_id, revoked))

    valid_seats = [tid for tid, revoked in seats if not revoked]

    if valid_seats:
        ids_str = ", ".join(f"#{tid}" for tid in valid_seats)
        click.echo(f"VALID — Wallet owns seat {ids_str} (not revoked)  ({address})")
    else:
        # Has seats but all revoked
        ids_str = ", ".join(f"#{tid}" for tid, _ in seats)
        click.echo(f"REVOKED — Seat {ids_str} is revoked  ({address})")

    click.echo("")
    click.echo(f"{'Token ID':<12} {'Revoked'}")
    click.echo("-" * 22)
    for token_id, revoked in seats:
        flag = "YES" if revoked else "no"
        click.echo(f"#{token_id:<11} {flag}")


if __name__ == "__main__":
    main()
