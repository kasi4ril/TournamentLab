"""
Module: tournament.fixtures
Description: Handles single round-robin schedule generation using upper-triangle 
             combinatorics (N*(N-1)/2) to guarantee no self-matches or reversed duplicates.
Owned by: Engineer A (Shwarji Ishaku Khatang)
"""

MIN_TEAMS = 4
MAX_TEAMS = 8


def generate_fixtures(teams: list[dict], existing_fixtures: list[dict] | None = None) -> list[dict]:
    """
    Generate a deterministic single round-robin schedule for 4 to 8 unique teams.
    
    Enforces the combinatorial formula N*(N-1)/2. Guarantees every team plays 
    every other team exactly once without self-matches or duplicate reversed pairs.
    
    Args:
        teams (list[dict]): The validated list of registered team dictionaries.
        existing_fixtures (list[dict] | None): Optional list of current fixtures. 
                                              If non-empty, regeneration is rejected.
                                              
    Returns:
        list[dict]: A list of newly created pending fixture dictionaries.
        
    Raises:
        ValueError: If fixtures already exist, or team count is outside the 4..8 range,
                    or team records/IDs contain duplicates or invalid structure.
    """
    # Prevent mid-season schedule wipes or duplicate generation runs
    if existing_fixtures is not None and len(existing_fixtures) > 0:
        raise ValueError("Fixtures have already been generated for this season. Cannot regenerate.")

    if not isinstance(teams, list):
        raise ValueError("Teams must be provided as a list.")

    n = len(teams)
    if n < MIN_TEAMS or n > MAX_TEAMS:
        raise ValueError(
            f"Fixture generation requires between {MIN_TEAMS} and {MAX_TEAMS} teams (got {n})."
        )

    # Validate team structure and ensure team IDs are strictly unique
    seen_ids = set()
    for t in teams:
        if not isinstance(t, dict) or "id" not in t or "name" not in t:
            raise ValueError("Invalid team record structure encountered.")
        if t["id"] in seen_ids:
            raise ValueError(f"Duplicate team ID detected: {t['id']}")
        seen_ids.add(t["id"])

    fixtures = []
    match_counter = 1

    # Upper-triangle nested loop combinatorics:
    # Outer loop i goes from 0 to n-2; inner loop j goes from i+1 to n-1.
    # This mathematically guarantees:
    # 1. Self-matches are impossible (i == j is never evaluated).
    # 2. Reversed duplicate pairs are impossible (j > i strictly, so TM001 vs TM002 
    #    is generated, but TM002 vs TM001 is never revisited).
    for i in range(n):
        for j in range(i + 1, n):
            fixture = {
                "id": f"M{match_counter:03d}",
                "home_id": teams[i]["id"],
                "away_id": teams[j]["id"],
                "status": "pending",
                "home_score": None,
                "away_score": None,
            }
            fixtures.append(fixture)
            match_counter += 1

    return fixtures


def list_fixtures(fixtures: list[dict], status_filter: str | None = None) -> list[dict]:
    """
    Return a shallow copy of fixtures, optionally filtered by status ('pending' or 'played').
    
    Args:
        fixtures (list[dict]): The master list of fixtures.
        status_filter (str | None): Optional filter ('pending', 'played', or None for all).
        
    Returns:
        list[dict]: A copied list of matching fixture dictionaries.
        
    Raises:
        ValueError: If an unsupported status filter string is provided.
    """
    if status_filter is not None and status_filter not in ("pending", "played"):
        raise ValueError("status_filter must be 'pending', 'played', or None.")

    result = []
    for f in fixtures:
        if status_filter is None or f.get("status") == status_filter:
            result.append(dict(f))
    return result
