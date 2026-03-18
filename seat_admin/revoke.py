#!/usr/bin/env python3
"""Revoke an RSE Seat NFT by token ID."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

import config

_LOG_PATH = Path(__file__).parent / "revocation_log.json"


def _append_log(entry: dict):
    log = []
    if _LOG_PATH.exists():
        with open(_LOG_PATH) as f:
            log = json.load(f)
    log.append(entry)
    with open(_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


@click.command()
@click.argument("token_id", type=int)
@click.option("--reason", default="", help="Reason for revocation (logged locally)")
def main(token_id: int, reason: str):
    w3, account = config.get_signer()
    contract = config.get_contract(w3)

    try:
        owner = contract.functions.ownerOf(token_id).call()
    except Exception:
        click.echo(f"Token #{token_id} does not exist.", err=True)
        sys.exit(1)

    already_revoked = contract.functions.isRevoked(token_id).call()
    if already_revoked:
        click.echo(f"Seat #{token_id} is already revoked.")

    click.echo(f"Seat #{token_id}  owner: {owner}")
    if not click.confirm(f"Revoke seat #{token_id}?", default=False):
        click.echo("Aborted.")
        sys.exit(0)

    receipt = config.send_tx(w3, account, contract.functions.revoke(token_id))

    entry = {
        "action": "revoke",
        "tokenId": token_id,
        "owner": owner,
        "reason": reason,
        "txHash": receipt["transactionHash"].hex(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _append_log(entry)

    click.echo(f"Seat #{token_id} revoked.")
    click.echo(f"Tx hash:  {receipt['transactionHash'].hex()}")
    click.echo(f"Gas used: {receipt['gasUsed']:,}")
    if reason:
        click.echo(f"Reason logged: {reason}")


if __name__ == "__main__":
    main()
