"""
Automated unit tests for Engineer B (Scoring, Standings & CLI / Champion Report).
Covers: Score validation (including bool rejection), atomic updates, 3/1/0 points,
multi-key tie-break sorting, derived standings, and champion status.
"""

import copy
import unittest

from tournament.teams import register_team
from tournament.fixtures import generate_fixtures
from tournament.standings import (
    record_result,
    compute_standings,
    get_season_status,
)


class TestScoringAndStandings(unittest.TestCase):
    """Tests for score recording, validation, standings derivation, and tie-breakers."""

    def setUp(self):
        self.teams = []
        for name in ["Thunder", "Comets", "Phoenix", "Rockets"]:
            register_team(self.teams, name)
        self.fixtures = generate_fixtures(self.teams, [])

    def test_01_reject_negative_float_string_none_and_boolean_scores(self):
        """Scenario 8: Strictly reject negative, float, str, None, and bool scores."""
        invalid_score_pairs = [
            (-1, 0),
            (0, -2),
            (1.5, 0),
            (0, 2.0),
            ("2", 1),
            (None, 0),
            (True, 0),    # Crucial check: isinstance(True, int) is True in Python!
            (0, False),   # Crucial check: isinstance(False, int) is True in Python!
            (True, False),
        ]
        fixture_snapshot = copy.deepcopy(self.fixtures)

        for home_s, away_s in invalid_score_pairs:
            with self.subTest(home_score=home_s, away_score=away_s):
                with self.assertRaises((ValueError, TypeError)):
                    record_result(self.fixtures, "M001", home_s, away_s)

                # Verify atomic rollback: M001 must remain pending with None scores
                self.assertEqual(self.fixtures, fixture_snapshot)

    def test_02_reject_unknown_fixture_id(self):
        """Scenario 9: Reject score submission for non-existent fixture ID."""
        fixture_snapshot = copy.deepcopy(self.fixtures)
        for bad_id in ("M999", "M000", "", "INVALID"):
            with self.subTest(fixture_id=bad_id):
                with self.assertRaises(ValueError):
                    record_result(self.fixtures, bad_id, 1, 0)
        self.assertEqual(self.fixtures, fixture_snapshot)

    def test_03_reject_duplicate_result_on_already_played_fixture(self):
        """Scenario 10: Reject second score submission on a completed fixture."""
        record_result(self.fixtures, "M001", 2, 1)

        with self.assertRaises(ValueError):
            record_result(self.fixtures, "M001", 0, 0)

        # Original score 2-1 must remain intact
        m001 = next(f for f in self.fixtures if f["id"] == "M001")
        self.assertEqual(m001["home_score"], 2)
        self.assertEqual(m001["away_score"], 1)
        self.assertEqual(m001["status"], "played")

    def test_04_award_correct_3_1_0_points_and_goal_metrics(self):
        """Scenario 11: Award 3 pts for win, 1 for draw, 0 for loss, and track GF/GA/GD."""
        # M001: TM001 (Thunder) vs TM002 (Comets) -> 3 - 2 (Thunder wins, Comets gets 2 GF)
        record_result(self.fixtures, "M001", 3, 2)
        # M006: TM003 (Phoenix) vs TM004 (Rockets) -> 0 - 0 (0-0 Draw gives 1 pt each)
        record_result(self.fixtures, "M006", 0, 0)

        table = {row["team_id"]: row for row in compute_standings(self.teams, self.fixtures)}

        # Winner: Thunder (TM001)
        self.assertEqual(table["TM001"]["played"], 1)
        self.assertEqual(table["TM001"]["wins"], 1)
        self.assertEqual(table["TM001"]["gf"], 3)
        self.assertEqual(table["TM001"]["ga"], 2)
        self.assertEqual(table["TM001"]["gd"], 1)
        self.assertEqual(table["TM001"]["points"], 3)

        # Loser: Comets (TM002) still gets 2 Goals For
        self.assertEqual(table["TM002"]["played"], 1)
        self.assertEqual(table["TM002"]["losses"], 1)
        self.assertEqual(table["TM002"]["gf"], 2)
        self.assertEqual(table["TM002"]["ga"], 3)
        self.assertEqual(table["TM002"]["gd"], -1)
        self.assertEqual(table["TM002"]["points"], 0)

        # 0-0 Draw: Phoenix (TM003) & Rockets (TM004)
        self.assertEqual(table["TM003"]["points"], 1)
        self.assertEqual(table["TM003"]["draws"], 1)
        self.assertEqual(table["TM004"]["points"], 1)
        self.assertEqual(table["TM004"]["draws"], 1)

    def test_05_multi_key_tie_break_sorting_order(self):
        """
        Scenario 12: Rank by Points DESC -> GD DESC -> GF DESC -> Normalized Name ASC.
        Craft a 6-team scenario testing every single tie-breaker level simultaneously.
        """
        teams = []
        # Register in reverse/scrambled alphabetical order to prove name sort isn't insertion order
        for name in ["Zulu", "alpha", "Bravo", "Charlie", "Delta", "Echo"]:
            register_team(teams, name)
        # IDs: TM001=Zulu, TM002=alpha, TM003=Bravo, TM004=Charlie, TM005=Delta, TM006=Echo

        # Construct controlled played fixtures to force specific ties:
        # 1. Zulu (TM001) & alpha (TM002) & Bravo (TM003) & Charlie (TM004) all get 3 points!
        #    - Charlie (TM004) beats Echo (TM006) 4-0 -> 3 pts, GD +4, GF 4 (Rank 1 by GD)
        #    - Bravo (TM003) beats Delta (TM005) 3-1  -> 3 pts, GD +2, GF 3 (Rank 2 by GF over Zulu/alpha)
        #    - Zulu (TM001) beats Delta (TM005) 2-0   -> 3 pts, GD +2, GF 2 (Tied Pts/GD/GF with alpha)
        #    - alpha (TM002) beats Echo (TM006) 2-0   -> 3 pts, GD +2, GF 2 (Beats Zulu alphabetically: 'alpha' < 'zulu')
        custom_fixtures = [
            {"id": "M001", "home_id": "TM004", "away_id": "TM006", "status": "played", "home_score": 4, "away_score": 0},
            {"id": "M002", "home_id": "TM003", "away_id": "TM005", "status": "played", "home_score": 3, "away_score": 1},
            {"id": "M003", "home_id": "TM001", "away_id": "TM005", "status": "played", "home_score": 2, "away_score": 0},
            {"id": "M004", "home_id": "TM002", "away_id": "TM006", "status": "played", "home_score": 2, "away_score": 0},
        ]

        standings = compute_standings(teams, custom_fixtures)
        ranked_names = [row["name"] for row in standings]

        expected_order = [
            "Charlie",  # 3 pts, GD +4, GF 4
            "Bravo",    # 3 pts, GD +2, GF 3
            "alpha",    # 3 pts, GD +2, GF 2 ('alpha' < 'zulu' casefolded)
            "Zulu",     # 3 pts, GD +2, GF 2
            "Delta",    # 0 pts, GD -4, GF 1
            "Echo",     # 0 pts, GD -6, GF 0
        ]
        self.assertEqual(ranked_names, expected_order)

    def test_06_standings_recomputed_ purely_from_matches_and_satisfy_invariants(self):
        """Scenario 13: Mutating a returned standings list never corrupts subsequent calls."""
        record_result(self.fixtures, "M001", 2, 0)
        record_result(self.fixtures, "M002", 1, 1)

        first_table = compute_standings(self.teams, self.fixtures)
        # Maliciously mutate the returned table in place
        first_table[0]["points"] = 9999
        first_table[0]["gf"] = 500

        # Recomputing from source of truth must yield clean, uncorrupted values
        second_table = compute_standings(self.teams, self.fixtures)
        self.assertEqual(second_table[0]["points"], 3)
        self.assertEqual(second_table[0]["gf"], 2)

        # Global League Invariants Check:
        # Total GF == Total GA; Total Points == 3*(non-draws) + 2*(draws)
        total_gf = sum(r["gf"] for r in second_table)
        total_ga = sum(r["ga"] for r in second_table)
        total_pts = sum(r["points"] for r in second_table)
        self.assertEqual(total_gf, total_ga)
        self.assertEqual(total_pts, 3 * 1 + 2 * 1)  # 1 decisive win + 1 draw = 5 pts

    def test_07_champion_shown_only_when_all_fixtures_played(self):
        """Scenario 16: Season is 'in_progress' until every fixture is played, then 'complete'."""
        # Before any match is played (but fixtures exist)
        status_initial = get_season_status(self.teams, self.fixtures)
        self.assertEqual(status_initial["status"], "in_progress")
        self.assertIsNone(status_initial["champion"])

        # Play 5 out of 6 matches
        for i in range(1, 6):
            record_result(self.fixtures, f"M00{i}", 1, 0)

        status_partial = get_season_status(self.teams, self.fixtures)
        self.assertEqual(status_partial["status"], "in_progress")
        self.assertIsNone(status_partial["champion"])

        # Play the final 6th match
        record_result(self.fixtures, "M006", 2, 2)
        status_complete = get_season_status(self.teams, self.fixtures)
        self.assertEqual(status_complete["status"], "complete")
        self.assertIsNotNone(status_complete["champion"])

        # Champion must match the 1st-place row of compute_standings
        top_team = compute_standings(self.teams, self.fixtures)[0]
        self.assertEqual(status_complete["champion"]["team_id"], top_team["team_id"])


if __name__ == "__main__":
    unittest.main()