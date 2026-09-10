"""Local tests for capability domains, scores, and price parsing (no live API)."""
import unittest

from handlers import (
    parse_money,
    score_capability_match,
    _keyword_match_score,
    MATCH_SCORE_MIN,
)


class ParseMoneyTests(unittest.TestCase):
    def test_zero_string(self):
        amount, err = parse_money("0.00")
        self.assertIsNone(err)
        self.assertEqual(amount, 0.0)

    def test_zero_number(self):
        amount, err = parse_money(0)
        self.assertIsNone(err)
        self.assertEqual(amount, 0.0)

    def test_negative(self):
        amount, err = parse_money(-1)
        self.assertIsNone(amount)
        self.assertIn("non-negative", err)

    def test_garbage(self):
        amount, err = parse_money("free")
        self.assertIsNone(amount)
        self.assertEqual(err, "Invalid price")


class DomainMatchTests(unittest.TestCase):
    def test_chef_not_construction(self):
        score = score_capability_match(
            "Private chef, 4 guests, 5-course dinner",
            "Structural steel, crane, warehouse framing, commercial construction",
        )
        self.assertLess(score, MATCH_SCORE_MIN)

    def test_construction_not_chef(self):
        score = score_capability_match(
            "Deliver 2T steel rebar + 4m3 concrete, crane assist",
            "Private chef, catering, 5-course dinner, dietary cooking",
        )
        self.assertLess(score, MATCH_SCORE_MIN)

    def test_uav_not_chef(self):
        score = score_capability_match(
            "UAV intercept, 12 contacts, sector 7G",
            "Private chef, French-Japanese fusion, catering",
        )
        self.assertLess(score, MATCH_SCORE_MIN)

    def test_chef_matches_chef(self):
        self.assertGreaterEqual(_keyword_match_score(
            "Private chef, 4 guests, dietary, 5-course dinner",
            "ChefBot Maison, French-Japanese fusion, private dining, dietary cooking",
        ), MATCH_SCORE_MIN)

    def test_construction_matches_construction(self):
        self.assertGreaterEqual(_keyword_match_score(
            "Structural steel frame erection, warehouse, crane required",
            "Structural steel, ironworker, crane operator, commercial construction",
        ), MATCH_SCORE_MIN)

    def test_uav_matches_uav(self):
        self.assertGreaterEqual(_keyword_match_score(
            "UAV intercept, 12 contacts, sector 7G, critical priority",
            "APEX-7 interceptor fleet, UAV, defense clearance, drone intercept",
        ), MATCH_SCORE_MIN)


if __name__ == "__main__":
    unittest.main()
