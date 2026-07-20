"""Unit tests for privacy projections."""
import privacy


def test_noise_stable():
    a = privacy.noisy_lat_lon(39.74, -104.99, "neighborhood", entity_id="bid1", day=100)
    b = privacy.noisy_lat_lon(39.74, -104.99, "neighborhood", entity_id="bid1", day=100)
    assert a == b
    assert a is not None
    # Should move a bit but stay nearby
    assert abs(a[0] - 39.74) < 0.02
    assert abs(a[1] - (-104.99)) < 0.02


def test_hidden_omits_coords():
    assert privacy.noisy_lat_lon(39.74, -104.99, "hidden", entity_id="x") is None


def test_coarsen_city():
    out = privacy.coarsen_address("123 Main St, Denver, CO 80202", "city")
    assert out and "Denver" in out
    assert "123" not in out or "Main" not in out


def test_project_nearby():
    bid = {
        "bid_id": "abc",
        "service": "Mow lawn, call 555-123-4567",
        "price": 50,
        "currency": "USD",
        "lat": 39.74,
        "lon": -104.99,
        "address": "123 Main St, Denver, CO",
        "buyer_reputation": 4.0,
        "privacy_level": "neighborhood",
    }
    out = privacy.project_nearby_service(bid, 1.2)
    assert out["distance"] == 1.2
    assert "lat" in out and "lon" in out
    assert "555" not in (out.get("service") or "")
    assert "123 Main" not in (out.get("address") or "")


if __name__ == "__main__":
    test_noise_stable()
    test_hidden_omits_coords()
    test_coarsen_city()
    test_project_nearby()
    print("ok")
