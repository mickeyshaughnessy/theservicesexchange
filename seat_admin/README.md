# Seat registry

Mickey Shaughnessy assigns, transfers, and revokes seats. A seat is a number, an owner name, and a private 12-word phrase. All seats are identical. The price is $0. A demand or supply account can also call `POST /seats/issue` and receive the next seat for free.

Use **admin.html → Seats** (signed in as Mickey) or:

```
POST /seats/issue               # caller's own next seat, price 0
GET  /admin/seats
GET  /admin/seats/{id}          # includes phrase
GET  /admin/seats/export?owner=Dr.%20Aftab
POST /admin/seats/assign        { "owner": "Dr. Aftab", "seat_id": 1 }
POST /admin/seats/transfer      { "seat_id": 1, "to_owner": "Amanda Jean" }
POST /admin/seats/revoke        { "seat_id": 1 }
POST /admin/seats/unrevoke      { "seat_id": 1 }
```

Blank `seat_id` on assign takes the next number. Destination does not need a registered username. Transfer keeps the phrase.

Founding issuance (run from repo root, writes Spaces + `seat_admin/exports/`):

```
python scripts/issue_founding_seats.py
```

Seats 1–1000 → Dr. Aftab; 1001–11000 → Amanda Jean.
