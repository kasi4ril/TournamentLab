"""
Automated unit tests for Engineer A (Scheduling & Reliable Data Layer).
Covers: Team registration, round-robin combinatorics, and JSON persistence/validation.
"""

import json
import pathlib
import tempfile
import unittest

from tournament.teams import register_team
from tournament.fixtures import generate_fixtures
from tournament.storage import save_season, load_season


class TestTeamRegistration(unittest.TestCase):
    """Tests for team registration, trimming, ID sequencing, and name constraints."""

    def setUp(self):
        self.teams = []

    def test_01_register_valid_team_trims_and_assigns_sequential_id(self):
        """Valid names are trimmed and assigned sequential TM001, TM002 IDs."""
        t1 = register_team(self.teams, "  Jos Highlanders  ")
        t2 = register_team(self.teams, "Abuja Titans")

        self.assertEqual(t1, {"id": "TM001", "name": "Jos Highlanders"})
        self.assertEqual(t2, {"id": "TM002", "name": "Abuja Titans"})
        self.assertEqual(len(self.teams), 2)

    def test_02_reject_duplicate_casefolded_team_name(self):
        """Scenario 1: Reject duplicate casefolded team names with surrounding spaces."""
        register_team(self.teams, "Red Comets")

        duplicate_variants = [
            "Red Comets",
            "red comets",
            "RED COMETS",
            "   rEd CoMeTs   ",
        ]
        for variant in duplicate_variants:
            with self.subTest(variant=variant):
                with self.assertRaises(ValueError):
                    register_team(self.teams, variant)

        self.assertEqual(len(self.teams), 1)

    def test_03_reject_blank_too_short_too_long_or_non_string_names(self):
        """Scenario 2: Reject blank, <2 chars, >30 chars, or non-string names."""
        invalid_names = [
            "",
            "   ",
            "A",
            "  Z  ",
            "X" * 31,
            "   " + ("Y" * 31) + "   ",
            None,
            12345,
        ]
        for bad_name in invalid_names:
            with self.subTest(bad_name=bad_name):
                with self.assertRaises((ValueError, TypeError)):
                    register_team(self.teams, bad_name)

        self.assertEqual(len(self.teams), 0)

    def test_04_boundary_name_lengths_2_and_30_accepted(self):
        """Exact boundary lengths of 2 characters and 30 characters are accepted."""
        t_min = register_team(self.teams, "FC")
        t_max = register_team(self.teams, "A" * 30)
        self.assertEqual(len(t_min["name"]), 2)
        self.assertEqual(len(t_max["name"]), 30)

    def test_05_reject_more_than_8_teams(self):
        """Ensure maximum league capacity of 8 teams cannot be exceeded."""
        for i in range(1, 9):
            register_team(self.teams, f"Club {i}")
        self.assertEqual(len(self.teams), 8)

        with self.assertRaises(ValueError):
            register_team(self.teams, "Club 9 Overflow")
        self.assertEqual(len(self.teams), 8)


class TestFixtureGeneration(unittest.TestCase):
    """Tests for single round-robin schedule generation and combinatorial invariants."""

    def _create_teams(self, count: int) -> list[dict]:
        teams = []
        for i in range(1, count + 1):
            register_team(teams, f"Team {i}")
        return teams

    def test_06_reject_fixture_generation_outside_4_to_8_teams(self):
        """Scenario 3: Reject fixture generation when team count is < 4 or > 8."""
        for count in (0, 1, 2, 3):
            teams = self._create_teams(count)
            with self.subTest(team_count=count):
                with self.assertRaises(ValueError):
                    generate_fixtures(teams, [])

        nine_teams = [{"id": f"TM00{i}", "name": f"Team {i}"} for i in range(1, 10)]
        with self.assertRaises(ValueError):
            generate_fixtures(nine_teams, [])

    def test_07_four_teams_produce_six_fixtures(self):
        """Scenario 4: 4 teams produce N*(N-1)/2 = 6 fixtures with sequential IDs."""
        teams = self._create_teams(4)
        fixtures = generate_fixtures(teams, [])

        self.assertEqual(len(fixtures), 6)
        expected_ids = [f"M{i:03d}" for i in range(1, 7)]
        self.assertEqual([f["id"] for f in fixtures], expected_ids)

        for f in fixtures:
            self.assertEqual(f["status"], "pending")
            self.assertIsNone(f["home_score"])
            self.assertIsNone(f["away_score"])

    def test_08_six_teams_produce_fifteen_fixtures(self):
        """Scenario 5: 6 teams produce N*(N-1)/2 = 15 fixtures."""
        teams = self._create_teams(6)
        fixtures = generate_fixtures(teams, [])
        self.assertEqual(len(fixtures), 15)

    def test_09_no_self_matches_and_no_duplicate_unordered_pairs(self):
        """Scenarios 6 & 7: No team plays itself; every unordered pair appears once."""
        teams = self._create_teams(6)
        fixtures = generate_fixtures(teams, [])

        seen_pairs = set()
        games_per_team = {t["id"]: 0 for t in teams}

        for f in fixtures:
            home, away = f["home_id"], f["away_id"]
            self.assertNotEqual(home, away, f"Self-match detected in {f['id']}")

            pair = frozenset({home, away})
            self.assertNotIn(pair, seen_pairs, f"Duplicate pair detected: {pair}")
            seen_pairs.add(pair)

            games_per_team[home] += 1
            games_per_team[away] += 1

        for team_id, count in games_per_team.items():
            self.assertEqual(count, 5, f"Team {team_id} played {count} games instead of 5")

    def test_10_deterministic_generation_and_reject_regeneration(self):
        """Schedule generation is deterministic and cannot be run twice in a season."""
        teams = self._create_teams(4)
        first_run = generate_fixtures(teams, [])
        second_fresh_run = generate_fixtures(teams, [])
        self.assertEqual(first_run, second_fresh_run)

        with self.assertRaises(ValueError):
            generate_fixtures(teams, first_run)


class TestStoragePersistence(unittest.TestCase):
    """Tests for JSON serialization, schema checking, and transactional load validation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.save_path = pathlib.Path(self.temp_dir.name) / "season.json"

        self.teams = []
        for name in ["Thunder", "Comets", "Phoenix", "Rockets"]:
            register_team(self.teams, name)
        self.fixtures = generate_fixtures(self.teams, [])
        self.fixtures[0]["status"] = "played"
        self.fixtures[0]["home_score"] = 2
        self.fixtures[0]["away_score"] = 0

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_11_save_and_reload_preserves_teams_and_fixtures(self):
        """Scenario 15: Saving and reloading restores exact teams and fixtures."""
        save_season(self.save_path, self.teams, self.fixtures)
        loaded_teams, loaded_fixtures = load_season(self.save_path)

        self.assertEqual(loaded_teams, self.teams)
        self.assertEqual(loaded_fixtures, self.fixtures)

    def test_12_reject_corrupt_json_and_bad_references(self):
        """Scenario 14: Malformed JSON or bad references raise ValueError before state mutation."""
        save_season(self.save_path, self.teams, self.fixtures)
        with open(self.save_path, "r", encoding="utf-8") as f:
            baseline_payload = json.load(f)

        active_teams_snapshot = [dict(t) for t in self.teams]
        bad_payloads = []

        p_schema = json.loads(json.dumps(baseline_payload))
        p_schema["schema_version"] = 99
        bad_payloads.append(("wrong_schema_version", p_schema))

        p_phantom = json.loads(json.dumps(baseline_payload))
        p_phantom["fixtures"][0]["away_id"] = "TM999"
        bad_payloads.append(("phantom_team_reference", p_phantom))

        p_bool_score = json.loads(json.dumps(baseline_payload))
        p_bool_score["fixtures"][0]["home_score"] = True
        bad_payloads.append(("boolean_score_in_json", p_bool_score))

        for label, payload in bad_payloads:
            with self.subTest(case=label):
                bad_file = pathlib.Path(self.temp_dir.name) / f"{label}.json"
                with open(bad_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f)

                with self.assertRaises(ValueError):
                    load_season(bad_file)

                self.assertEqual(self.teams, active_teams_snapshot)


if __name__ == "__main__":
    unittest.main()
