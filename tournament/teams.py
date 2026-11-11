"""
Module: tournament.teams
Description: Handles team registration, display name sanitization, case-insensitive 
             uniqueness checks, and sequential immutable ID generation (TM001..TM008).
Owned by: Engineer A (Shwarji Ishaku Khatang)
"""

MIN_NAME_LEN = 2
MAX_NAME_LEN = 30
MAX_TEAMS = 8


def validate_team_name(raw_name: str) -> str:
    """
    Validate and return a trimmed team display name.
    
    Args:
        raw_name (str): The raw user-supplied team name string.
        
    Returns:
        str: The sanitized, stripped team name.
        
    Raises:
        ValueError: If input is not a string or violates length bounds (2..30).
    """
    if not isinstance(raw_name, str):
        raise ValueError("Team name must be a valid string.")

    cleaned = raw_name.strip()
    if len(cleaned) < MIN_NAME_LEN or len(cleaned) > MAX_NAME_LEN:
        raise ValueError(
            f"Team name must be between {MIN_NAME_LEN} and {MAX_NAME_LEN} "
            f"characters after trimming (got {len(cleaned)} characters)."
        )
    return cleaned


def register_team(teams: list[dict], raw_name: str) -> dict:
    """
    Register a new team into the mutable `teams` collection after thorough validation.
    
    Enforces maximum league capacity (8 teams), character length bounds, and 
    case-insensitive uniqueness using full Unicode case-folding.
    
    Args:
        teams (list[dict]): The current list of registered team dictionaries.
        raw_name (str): The proposed team display name.
        
    Returns:
        dict: The newly created team record containing 'id' and 'name'.
        
    Raises:
        ValueError: On capacity overflow, invalid format, or duplicate casefolded name.
    """
    if not isinstance(teams, list):
        raise ValueError("Teams collection must be provided as a list.")

    # Sanitize and validate name bounds
    cleaned_name = validate_team_name(raw_name)

    # Check maximum league capacity invariant
    if len(teams) >= MAX_TEAMS:
        raise ValueError(f"Cannot register more than {MAX_TEAMS} teams in a single league season.")

    # Enforce case-insensitive uniqueness using .casefold() for robust Unicode compliance
    normalized_target = cleaned_name.casefold()
    for existing in teams:
        if existing.get("name", "").strip().casefold() == normalized_target:
            raise ValueError(f"Duplicate team name rejected: '{cleaned_name}' already exists.")

    # Generate deterministic, zero-padded surrogate ID (TM001, TM002, etc.)
    existing_ids = {t["id"] for t in teams}
    next_index = len(teams) + 1
    team_id = f"TM{next_index:03d}"
    
    # Ensure ID collision safety
    while team_id in existing_ids:
        next_index += 1
        team_id = f"TM{next_index:03d}"

    new_team = {
        "id": team_id,
        "name": cleaned_name,
    }
    
    # Mutate state only after all validations pass (atomic addition)
    teams.append(new_team)
    return new_team


def list_teams(teams: list[dict]) -> list[dict]:
    """
    Return a shallow copy of registered teams to prevent external list mutation.
    
    Args:
        teams (list[dict]): The active teams list.
        
    Returns:
        list[dict]: A safe copied list of team dictionaries.
    """
    return [dict(team) for team in teams]
