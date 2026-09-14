# Seat registry

Mickey Shaughnessy assigns, transfers, and revokes seats.

Use **admin.html → Seats** (signed in as Mickey) or:

```
GET  /admin/seats
POST /admin/seats/assign    { "username": "alice", "seat_id": 1 }
POST /admin/seats/transfer  { "seat_id": 1, "to_username": "bob" }
POST /admin/seats/revoke    { "seat_id": 1 }
POST /admin/seats/unrevoke  { "seat_id": 1 }
```

Blank `seat_id` on assign takes the next number. Destination username must already be registered. Seats stay transferable: transfer updates the registry.
