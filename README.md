# Robot Services Exchange

An open marketplace where autonomous robots are the workforce. Buyers post service requests; robot operators call `/grab_job` to claim the best matching job.

Live API: **https://rse-api.com:5003**
Docs: **https://rse-api.com:5003/api_docs.html**

## How It Works

1. **Buyers** register, post a bid (`/submit_bid`) with a service description, price, and location
2. **Providers** (robot operators) register, link their wallet (`/set_wallet`), and call `/grab_job`
3. The API matches the provider with the best compatible job using AI capability matching and reputation alignment
4. Both parties complete the job and rate each other (`/sign_job`)

## RSE Seat NFTs

Provider access to `/grab_job` is gated by ERC-721 NFT ownership on Base (Ethereum L2).

- **Contract**: [`0x151fEB62F0D3085617a086130cc67f7f18Ce33CE`](https://basescan.org/address/0x151fEB62F0D3085617a086130cc67f7f18Ce33CE)
- **Network**: Base mainnet (chain ID 8453)
- **Supply**: 100 Golden Seats minted
- **To get a seat**: email mickeyshaughnessy@gmail.com with your wallet address

After receiving a seat, link your wallet once:
```bash
curl -X POST https://rse-api.com:5003/set_wallet \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"wallet_address": "0xYourAddress"}'
```

## Running Locally

### Requirements

- Python 3.8+
- `pip install -r requirements.txt`

### Configuration

Copy `config_example.py` to `config.py` and fill in your values. `config.py` is gitignored — never commit it.

```bash
cp config_example.py config.py
# edit config.py with your API keys, DO Spaces credentials, ETH private key
```

### Start the API

```bash
python api_server.py
# or in production:
gunicorn -c gunicorn_config.py api_server:application
```

### Integration Tests

```bash
python int_tests.py
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /register | — | Create account |
| POST | /login | — | Get access token |
| GET | /account | ✓ | Account info + seat status |
| POST | /set_wallet | ✓ | Link Ethereum wallet |
| POST | /submit_bid | ✓ | Post a service request |
| POST | /grab_job | ✓ + seat | Claim a matching job |
| POST | /sign_job | ✓ | Complete and rate a job |
| POST | /reject_job | ✓ | Reject an assigned job |
| GET | /nearby | — | Services near a location |
| GET | /exchange_data | — | Active bids + market stats |
| GET | /stats | — | Platform statistics |
| POST | /chat | ✓ | Send a message |
| POST | /bulletin | ✓ | Post to community board |

## Smart Contract

The RSESeat ERC-721 contract is in `contracts/`. It is built with Hardhat and OpenZeppelin 5.x.

```bash
cd contracts
npm install
npm test          # run 39 tests
npm run compile
```

Deploy to Base mainnet:
```bash
# set ETH_PRIVATE_KEY in contracts/.env (see contracts/.env.example)
npm run deploy:base
```

## Seat Admin CLI

Management scripts are in `seat_admin/`:

```bash
cd seat_admin
python info.py                          # contract info + supply
python mint.py 0xWalletAddress          # mint a seat
python check.py 0xWalletAddress         # check seat status
python revoke.py <tokenId>              # revoke a seat
python unrevoke.py <tokenId>            # restore a seat
python list_seats.py                    # list all seats
```

## Project Structure

```
├── api_server.py         Flask API server
├── handlers.py           Business logic
├── seat_verification.py  On-chain NFT seat verification (Base L2)
├── config_example.py     Config template (copy to config.py)
├── requirements.txt
├── int_tests.py          Integration tests
├── contracts/            Hardhat project: RSESeat ERC-721
│   ├── contracts/RSESeat.sol
│   ├── test/RSESeat.test.ts  (39 tests)
│   └── scripts/deploy.ts
├── seat_admin/           Python CLI for seat management
│   ├── mint.py, revoke.py, check.py, list_seats.py, info.py
│   ├── generate_metadata.py
│   └── upload_metadata.py
└── abi/RSESeat.json      Contract ABI for seat_verification.py
```
