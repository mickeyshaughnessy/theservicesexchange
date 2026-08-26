"""Unit tests for /grab_job geohash whitelist matching."""
from unittest.mock import patch

import handlers


# Downtown Denver (known Nominatim / test fast-path coords)
DENVER = (39.7392, -104.9903)
# SF Civic Center
SF = (37.7793, -122.4192)


def test_encode_geohash_denver_prefix():
    gh = handlers.encode_geohash(*DENVER, precision=5)
    assert gh.startswith("9xj")
    assert len(gh) == 5
    # Nested cells share the parent prefix
    assert handlers.encode_geohash(*DENVER, precision=7).startswith(gh)


def test_parse_geohash_arg():
    assert handlers.parse_geohash_arg(None) == (None, None)
    assert handlers.parse_geohash_arg("") == (None, None)
    assert handlers.parse_geohash_arg("  ") == (None, None)
    assert handlers.parse_geohash_arg("9XJ") == ("9xj", None)
    gh, err = handlers.parse_geohash_arg("ail")  # a, i, l are not in geohash alphabet
    assert gh is None and err
    gh, err = handlers.parse_geohash_arg(123)
    assert gh is None and "string" in err
    gh, err = handlers.parse_geohash_arg("9" * 13)
    assert gh is None and "1–12" in err


def test_point_in_geohash():
    cell = handlers.encode_geohash(*DENVER, precision=5)
    assert handlers.point_in_geohash(*DENVER, cell)
    assert not handlers.point_in_geohash(*SF, cell)


def test_bid_in_geohash_region_physical():
    cell = handlers.encode_geohash(*DENVER, precision=5)
    denver_bid = {"location_type": "physical", "lat": DENVER[0], "lon": DENVER[1]}
    sf_bid = {"location_type": "physical", "lat": SF[0], "lon": SF[1]}
    remote_bid = {"location_type": "remote"}
    physical_no_coords = {"location_type": "physical"}

    assert handlers.bid_in_geohash_region(denver_bid, cell)
    assert not handlers.bid_in_geohash_region(sf_bid, cell)
    assert handlers.bid_in_geohash_region(remote_bid, cell)
    assert not handlers.bid_in_geohash_region(physical_no_coords, cell)


def test_bid_in_geohash_region_rideshare_dropoff():
    cell = handlers.encode_geohash(*DENVER, precision=5)
    # Pickup in Denver, drop-off in SF — robot would leave the whitelist cell
    ride = {
        "location_type": "physical",
        "lat": DENVER[0],
        "lon": DENVER[1],
        "start_lat": DENVER[0],
        "start_lon": DENVER[1],
        "end_lat": SF[0],
        "end_lon": SF[1],
    }
    assert not handlers.bid_in_geohash_region(ride, cell)
    local_ride = dict(ride, end_lat=DENVER[0], end_lon=DENVER[1])
    assert handlers.bid_in_geohash_region(local_ride, cell)


def _supply_account():
    return {
        "user_type": "supply",
        "last_grab_at": 0,
        "seat_active": True,
        "seat_token_id": None,
    }


def test_grab_job_rejects_invalid_geohash():
    with patch("handlers.get_account", return_value=_supply_account()):
        resp, status = handlers.grab_job({
            "username": "bot",
            "capabilities": "autonomous mower",
            "geohash": "not a hash!",
        })
    assert status == 400
    assert "geohash" in resp["error"].lower() or "Invalid" in resp["error"]


def test_grab_job_geohash_skips_jobs_outside_cell():
    denver_bid = {
        "bid_id": "in-cell",
        "username": "buyer",
        "service": "TEST: lawn mowing",
        "price": 80,
        "currency": "USD",
        "payment_method": "cash",
        "end_time": 2**31,
        "location_type": "physical",
        "lat": DENVER[0],
        "lon": DENVER[1],
        "address": "Denver, CO",
        "buyer_reputation": 2.5,
        "rejected_by": [],
    }
    sf_bid = dict(denver_bid, bid_id="out-cell", lat=SF[0], lon=SF[1], address="San Francisco, CA")
    cell = handlers.encode_geohash(*DENVER, precision=5)

    with patch("handlers.get_account", return_value=_supply_account()), \
         patch("handlers.get_all_bids", return_value=[sf_bid, denver_bid]), \
         patch("handlers.match_service_with_capabilities", return_value=True), \
         patch("handlers.calculate_reputation_score", return_value=2.5), \
         patch("handlers.save_job") as save_job, \
         patch("handlers.delete_bid") as delete_bid, \
         patch("handlers.save_account"), \
         patch("handlers._emit"), \
         patch("handlers.ensure_job_channel"), \
         patch("handlers.public_actor", return_value={}):
        job, status = handlers.grab_job({
            "username": "bot",
            "capabilities": "lawn mowing robot",
            "location_type": "physical",
            "lat": DENVER[0],
            "lon": DENVER[1],
            "max_distance": 5000,
            "geohash": cell,
        })

    assert status == 200
    assert job["bid_id"] == "in-cell"
    save_job.assert_called_once()
    delete_bid.assert_called_once_with("in-cell")


def test_grab_job_geohash_204_when_only_outside_jobs():
    sf_bid = {
        "bid_id": "out-cell",
        "username": "buyer",
        "service": "TEST: lawn mowing",
        "price": 80,
        "end_time": 2**31,
        "location_type": "physical",
        "lat": SF[0],
        "lon": SF[1],
        "buyer_reputation": 2.5,
        "rejected_by": [],
    }
    cell = handlers.encode_geohash(*DENVER, precision=5)

    with patch("handlers.get_account", return_value=_supply_account()), \
         patch("handlers.get_all_bids", return_value=[sf_bid]), \
         patch("handlers.match_service_with_capabilities", return_value=True):
        resp, status = handlers.grab_job({
            "username": "bot",
            "capabilities": "lawn mowing robot",
            "location_type": "physical",
            "lat": DENVER[0],
            "lon": DENVER[1],
            "max_distance": 5000,
            "geohash": cell,
        })

    assert status == 204
    assert "area" in resp.get("message", "").lower()


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"✓ {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"✗ {fn.__name__}: {exc}")
    if failed:
        raise SystemExit(1)
    print(f"\n{len(tests)} passed")
