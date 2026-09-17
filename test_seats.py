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


if __name__ == "__main__":
    unittest.main()
