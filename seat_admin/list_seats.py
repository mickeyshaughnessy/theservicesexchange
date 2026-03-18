#!/usr/bin/env python3
"""List all RSE Seat NFTs with owner and revocation status."""

import csv
import sys
import click

import config


@click.command()
@click.option("--output", "-o", default=None, help="Write results to a CSV file at this path")
def main(output: str | None):
    w3 = config.get_w3()
    contract = config.get_contract(w3)

    total = contract.functions.totalSupply().call()
    if total == 0:
        click.echo("No seats minted yet.")
        sys.exit(0)

    click.echo(f"Fetching {total} seats from {config.NETWORK}...")

    rows = []
    for token_id in range(1, total + 1):
        try:
            owner = contract.functions.ownerOf(token_id).call()
            revoked = contract.functions.isRevoked(token_id).call()
        except Exception:
            # token may have been burned (not expected, but defensive)
            owner = "N/A"
            revoked = False
        rows.append({"tokenId": token_id, "owner": owner, "revoked": revoked})

    # Print table
    col_w = 46
    header = f"{'Token ID':<10} {'Owner':<{col_w}} {'Revoked'}"
    click.echo(header)
    click.echo("-" * (10 + col_w + 8))
    for r in rows:
        flag = "YES" if r["revoked"] else "no"
        click.echo(f"#{r['tokenId']:<9} {r['owner']:<{col_w}} {flag}")

    if output:
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["tokenId", "owner", "revoked"])
            writer.writeheader()
            writer.writerows(rows)
        click.echo(f"\nCSV written to: {output}")


if __name__ == "__main__":
    main()
