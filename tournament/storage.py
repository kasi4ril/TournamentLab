"""
Module: tournament.storage
Description: Handles JSON serialization, schema versioning (v1), and transactional 
             load validation (validate-before-swap) to prevent memory corruption.
Owned by: Engineer A (Shwarji Ishaku Khatang)
"""

import json
import pathlib
from tournament.teams import validate_team_name, MAX_TEAMS
from tournament.fixtures import MIN_TEAMS

SCHEMA_VERSION = 1


def _is_valid_nonnegative_int(value) -> bool:
    """
    Helper function to strictly validate true non-negative integers.
    
    Crucial Rule: In Python, `bool` is a subclass of `int` (e.g., isinstance(True, int) is True).
    We explicitly reject booleans here to prevent users injecting True/False as goals.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate_season_data(payload: dict) -> tuple[list[dict], list[dict]]:
    """
    Validate a raw dictionary against all TournamentLab schema and business invariants.
    
    Performs comprehensive checks on teams, fixture counts, referential integrity, 
    unordered pair uniqueness, and score/status consistency.
    
    Args:
        payload (dict): The raw dictionary parsed from a JSON save file.
        
    Returns:
        tuple[list[dict], list[dict]]: Clean, validated deep-copied (teams, fixtures).
        
    Raises:
        ValueError: On any structural, referential, or business rule violation.
    """
    if not isinstance(payload, dict):
        raise ValueError("Season data root must be a JSON object dictionary.")

    # 1. Enforce schema versioning compatibility
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported or missing schema_version (expected {SCHEMA_VERSION}, "
            f"got {payload.get('schema_version')!r})."
        )

    raw_teams = payload.get("teams")
    raw_fixtures = payload.get("fixtures")

    if not isinstance(raw_teams, list) or not isinstance(raw_fixtures, list):
        raise ValueError("Both 'teams' and 'fixtures' must be JSON arrays.")

    if len(raw_teams) > MAX_TEAMS:
        raise ValueError(f"Season data contains {len(raw_teams)} teams (max allowed is {MAX_TEAMS}).")

    # 2. Validate Teams: structure, surrogate ID format, name bounds, casefolded uniqueness
    validated_teams = []
    seen_team_ids = set()
    seen_team_names = set()

    for t in raw_teams:
        if not isinstance(t, dict) or set(t.keys()) != {"id", "name"}:
            raise ValueError("Each team record must contain exactly 'id' and 'name' keys.")

        team_id = t["id"]
        if not isinstance(team_id, str) or not team_id.startswith("TM") or len(team_id) < 3:
            raise ValueError(f"Invalid team ID format encountered: {team_id!r}")

        if team_id in seen_team_ids:
            raise ValueError(f"Duplicate team ID detected in payload: {team_id}")
        seen_team_ids.add(team_id)

        cleaned_name = validate_team_name(t["name"])
        folded_name = cleaned_name.casefold()
        if folded_name in seen_team_names:
            raise ValueError(f"Duplicate casefolded team name in payload: {cleaned_name!r}")
        seen_team_names.add(folded_name)

        validated_teams.append({"id": team_id, "name": cleaned_name})

    # 3. Validate Fixtures count against N*(N-1)/2 combinatorial invariant if fixtures exist
    n_teams = len(validated_teams)
    if len(raw_fixtures) > 0:
        if n_teams < MIN_TEAMS or n_teams > MAX_TEAMS:
            raise ValueError(
                f"Cannot have scheduled fixtures with {n_teams} teams (requires {MIN_TEAMS}..{MAX_TEAMS})."
            )
        expected_count = (n_teams * (n_teams - 1)) // 2
        if len(raw_fixtures) != expected_count:
            raise ValueError(
                f"Fixture count mismatch: expected {expected_count} fixtures for {n_teams} teams, "
                f"got {len(raw_fixtures)}."
            )

    # 4. Validate individual fixtures: keys, unique IDs, referential integrity, 
    #    unordered pair uniqueness via frozenset, and status/score consistency.
    validated_fixtures = []
    seen_fixture_ids = set()
    seen_unordered_pairs = set()
    required_fixture_keys = {"id", "home_id", "away_id", "status", "home_score", "away_score"}

    for f in raw_fixtures:
        if not isinstance(f, dict) or set(f.keys()) != required_fixture_keys:
            raise ValueError("Invalid fixture record keys structure.")

        fid = f["id"]
        if not isinstance(fid, str) or not fid.startswith("M") or len(fid) < 2:
            raise ValueError(f"Invalid fixture ID format: {fid!r}")
        if fid in seen_fixture_ids:
            raise ValueError(f"Duplicate fixture ID detected: {fid}")
        seen_fixture_ids.add(fid)

        home_id = f["home_id"]
        away_id = f["away_id"]

        # Referential Integrity Check: ensure referenced team IDs actually exist in teams list
        if home_id not in seen_team_ids or away_id not in seen_team_ids:
            raise ValueError(f"Fixture {fid} references unknown team ID(s): {home_id}, {away_id}")

        # Self-match check
        if home_id == away_id:
            raise ValueError(f"Fixture {fid} is an invalid self-match ({home_id} vs {away_id}).")

        # Unordered pair uniqueness check using frozenset 
        # (order-independent: frozenset({'TM001', 'TM002'}) == frozenset({'TM002', 'TM001'}))
        pair = frozenset({home_id, away_id})
        if pair in seen_unordered_pairs:
            raise ValueError(f"Duplicate unordered team pair in fixture {fid}: {home_id} vs {away_id}")
        seen_unordered_pairs.add(pair)

        # Status & Score Consistency Check
        status = f["status"]
        home_score = f["home_score"]
        away_score = f["away_score"]

        if status == "pending":
            if home_score is not None or away_score is not None:
                raise ValueError(f"Pending fixture {fid} must have None scores.")
        elif status == "played":
            if not _is_valid_nonnegative_int(home_score) or not _is_valid_nonnegative_int(away_score):
                raise ValueError(
                    f"Played fixture {fid} must have valid non-negative integer scores (booleans rejected)."
                )
        else:
            raise ValueError(f"Invalid fixture status string {status!r} in fixture {fid}.")

        validated_fixtures.append({
            "id": fid,
            "home_id": home_id,
            "away_id": away_id,
            "status": status,
            "home_score": home_score,
            "away_score": away_score,
        })

    return validated_teams, validated_fixtures


def save_season(filepath: str | pathlib.Path, teams: list[dict], fixtures: list[dict]) -> None:
    """
    Validate current in-memory state invariants and serialize to a JSON file.
    
    Args:
        filepath (str | Path): Destination file path.
        teams (list[dict]): Active teams list.
        fixtures (list[dict]): Active fixtures list.
        
    Raises:
        ValueError: If state invariants fail validation prior to writing.
    """
    payload = {
        "schema_version": SCHEMA_VERSION,
        "teams": teams,
        "fixtures": fixtures,
    }
    clean_teams, clean_fixtures = validate_season_data(payload)

    path = pathlib.Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema_version": SCHEMA_VERSION,
                "teams": clean_teams,
                "fixtures": clean_fixtures,
            },
            f,
            indent=2,
        )


def load_season(filepath: str | pathlib.Path) -> tuple[list[dict], list[dict]]:
    """
    Read JSON file from disk, validate all schema and business invariants in temporary 
    memory (validate-before-swap), and return data only if 100% valid.
    
    Args:
        filepath (str | Path): Path to the saved season JSON file.
        
    Returns:
        tuple[list[dict], list[dict]]: The validated (teams, fixtures) tuple.
        
    Raises:
        ValueError: On file read failure, bad JSON syntax, or any invariant violation.
    """
    path = pathlib.Path(filepath)
    if not path.exists() or not path.is_file():
        raise ValueError(f"Season save file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_payload = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Failed to parse JSON file structure: {exc}") from exc

    # Validate entirely before returning (protects memory state from corruption)
    return validate_season_data(raw_payload)
