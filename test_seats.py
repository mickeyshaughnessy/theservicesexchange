"""Unit tests for trust-based seats (number, owner, phrase)."""
import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import seats


class ProofTests(unittest.TestCase):
    def test_bip39_phrase_is_twelve_known_words(self):
        words = set(seats.load_bip39_wordlist())
        phrase = seats.generate_phrase()
        parts = phrase.split(" ")
        self.assertEqual(len(parts), 12)
        self.assertTrue(all(p in words for p in parts))
        self.assertNotEqual(phrase, seats.generate_phrase())

    def test_daily_proof_matches_today_and_neighbors(self):
        phrase = "abandon ability able about above absent absorb abstract absurd abuse access accident"
        now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
        secret = seats.daily_proof(phrase, now.date())
        self.assertEqual(len(secret), 64)
        self.assertTrue(seats.proof_matches(phrase, secret, now=now))
        yesterday = seats.daily_proof(phrase, (now - timedelta(days=1)).date())
        tomorrow = seats.daily_proof(phrase, (now + timedelta(days=1)).date())
        self.assertTrue(seats.proof_matches(phrase, yesterday, now=now))
        self.assertTrue(seats.proof_matches(phrase, tomorrow, now=now))
        two_days = seats.daily_proof(phrase, (now - timedelta(days=2)).date())
        self.assertFalse(seats.proof_matches(phrase, two_days, now=now))

    def test_proof_is_sha256_of_phrase_pipe_date(self):
        phrase = "one two three"
        day = datetime(2026, 1, 2, tzinfo=timezone.utc).date()
        expected = hashlib.sha256(b"one two three|2026-01-02").hexdigest()
        self.assertEqual(seats.daily_proof(phrase, day), expected)

    def test_owners_match_is_case_insensitive(self):
        self.assertTrue(seats.owners_match("Dr. Aftab", "dr. aftab"))
        self.assertFalse(seats.owners_match("Dr. Aftab", "Amanda Jean"))

    def test_remote_grabs_skip_seat(self):
        self.assertFalse(seats.seat_required_for_grab("remote"))
        self.assertTrue(seats.seat_required_for_grab("physical"))
        self.assertTrue(seats.seat_required_for_grab("hybrid"))
        self.assertTrue(seats.seat_required_for_grab(None))

    def test_extract_nested_and_flat_proof(self):
        sid, owner, secret, err = seats.extract_seat_proof({
            "seat": {"id": 7, "owner": "Dr. Aftab", "secret": "a" * 64},
        })
        self.assertEqual(sid, 7)
        self.assertEqual(owner, "Dr. Aftab")
        self.assertIsNone(err)
        sid, owner, secret, err = seats.extract_seat_proof({})
        self.assertIsNotNone(err)

    def test_verify_grab_proof_checks_owner_and_hash(self):
        phrase = seats.generate_phrase()
        rec = {
            "seat_id": 1,
            "owner": "Dr. Aftab",
            "phrase": phrase,
            "status": "active",
        }
        now = datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc)
        secret = seats.daily_proof(phrase, now.date())
        with patch("seats.get_seat_record", return_value=rec):
            ok, msg, got = seats.verify_grab_proof(
                {"seat": {"id": 1, "owner": "Dr. Aftab", "secret": secret}},
                now=now,
            )
            self.assertTrue(ok, msg)
            self.assertEqual(got["seat_id"], 1)
            ok, msg, _ = seats.verify_grab_proof(
                {"seat": {"id": 1, "owner": "Amanda Jean", "secret": secret}},
                now=now,
            )
            self.assertFalse(ok)
            self.assertIn("owner", msg.lower())
            ok, msg, _ = seats.verify_grab_proof(
                {"seat": {"id": 1, "owner": "Dr. Aftab", "secret": "0" * 64}},
                now=now,
            )
            self.assertFalse(ok)


class IssueSeatTests(unittest.TestCase):
    def _patches(self, store):
        def get_index(force_refresh=False):
            return store["index"]

        def get_rec(sid, force_refresh=False):
            return store["records"].get(int(sid))

        def save_rec(sid, rec):
            store["records"][int(sid)] = dict(rec)
            return True

        def save_index(index):
            store["index"] = index
            return True

        return (
            patch("seats.get_seats_index", side_effect=get_index),
            patch("seats.get_seat_record", side_effect=get_rec),
            patch("seats.save_seat_record", side_effect=save_rec),
            patch("seats.save_seats_index", side_effect=save_index),
            patch("seats._sync_account"),
        )

    def test_issue_is_free_identical_and_idempotent(self):
        store = {"index": {"seats": {}, "by_owner": {}, "next_id": 11002}, "records": {}}
        contexts = self._patches(store)
        for ctx in contexts:
            ctx.start()
        try:
            body, status = seats.issue_seat("ada")
            self.assertEqual(status, 200)
            self.assertTrue(body["issued"])
            self.assertEqual(body["price"], 0)
            self.assertEqual(body["currency"], "USD")
            self.assertEqual(body["access"], "free")
            self.assertEqual(body["seat"]["seat_id"], 11002)
            self.assertEqual(body["seat"]["price"], 0)
            self.assertEqual(body["seat"]["owner"], "ada")
            self.assertIn("phrase", body)
            self.assertEqual(store["records"][11002]["price"], 0)

            supply, status = seats.issue_seat("bot")
            self.assertEqual(status, 200)
            self.assertTrue(supply["issued"])
            self.assertEqual(supply["price"], 0)
            self.assertEqual(supply["seat"]["seat_id"], 11003)
            self.assertEqual(supply["seat"]["price"], body["seat"]["price"])

            again, status = seats.issue_seat("ada")
            self.assertEqual(status, 200)
            self.assertFalse(again["issued"])
            self.assertEqual(again["message"], "Seat already issued")
            self.assertEqual(again["seat"]["seat_id"], 11002)
            self.assertEqual(again["price"], 0)
            self.assertNotIn("phrase", again)
            self.assertEqual(len(store["records"]), 2)
        finally:
            for ctx in contexts:
                ctx.stop()

    def test_projection_forces_seat_price_to_zero(self):
        from handlers import _merge_projection_overrides

        params = _merge_projection_overrides("base", {"seatPrice": 100000, "takeRate": 0.05})
        self.assertEqual(params["seatPrice"], 0.0)
        self.assertEqual(params["takeRate"], 0.0)
        aggressive = _merge_projection_overrides("aggressive", None)
        self.assertEqual(aggressive["seatPrice"], 0.0)


class IssueSeatHandlerTests(unittest.TestCase):
    def test_demand_and_supply_both_issue_for_free(self):
        from handlers import issue_seat as handler_issue

        issued = {
            "message": "Seat issued",
            "issued": True,
            "price": 0,
            "seat": {"seat_id": 12, "owner": "ada", "price": 0},
        }
        with patch("handlers.get_account", return_value={"user_type": "demand"}), \
             patch("seats.issue_seat", return_value=(dict(issued), 200)):
            body, status = handler_issue("ada")
        self.assertEqual(status, 200)
        self.assertEqual(body["user_type"], "demand")
        self.assertEqual(body["price"], 0)
        self.assertEqual(body["access"], "free")

        with patch("handlers.get_account", return_value={"user_type": "supply"}), \
             patch("seats.issue_seat", return_value=(dict(issued), 200)):
            body, status = handler_issue("bot")
        self.assertEqual(status, 200)
        self.assertEqual(body["user_type"], "supply")
        self.assertEqual(body["price"], 0)

        with patch("handlers.get_account", return_value={"user_type": "observer"}):
            body, status = handler_issue("nope")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
