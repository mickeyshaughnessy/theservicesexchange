#!/usr/bin/env python3
"""Print RSE Seat contract info: address, network, supply, base URI, owner."""

import click

import config


@click.command()
def main():
    w3 = config.get_w3()
    contract = config.get_contract(w3)

    owner = contract.functions.owner().call()
    total_supply = contract.functions.totalSupply().call()
    # baseURI is exposed via tokenURI on token #1 if it exists, otherwise we
    # call the public getter — OZ doesn't expose _baseTokenURI directly, so we
    # read it from tokenURI(1) and strip the trailing "1.json" if supply > 0.
    base_uri = "(no tokens minted yet — URI unknown)"
    if total_supply > 0:
        token_uri = contract.functions.tokenURI(1).call()
        if token_uri.endswith("1.json"):
            base_uri = token_uri[: -len("1.json")]
        else:
            base_uri = token_uri or "(empty)"

    chain_id = w3.eth.chain_id

    click.echo(f"Network:          {config.NETWORK}  (chain {chain_id})")
    click.echo(f"RPC:              {config.rpc_url()}")
    click.echo(f"Contract:         {config.CONTRACT_ADDRESS}")
    click.echo(f"Owner:            {owner}")
    click.echo(f"Total supply:     {total_supply}")
    click.echo(f"Base URI:         {base_uri}")


if __name__ == "__main__":
    main()
