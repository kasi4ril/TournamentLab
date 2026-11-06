# TournamentLab — Architecture & Design Decisions

**Project:** TournamentLab (Esports League Manager CLI)  
**Engineers:** Shwarji Khatang (Engineer A — Scheduling & Data Layer) & Wealth Ibe (Engineer B — Scoring, Standings & CLI)  
**Schema Version:** `1`  
**Standard Library Target:** Python 3.10+ (`json`, `pathlib`, `unittest`, `tempfile`, `random`)

---

## 1. Architectural Philosophy: Explicit State & Pure Domain Logic

### Context
Beginner CLI programs often mix `input()`/`print()` calls with business logic and rely on mutable global variables. This makes automated unit testing with `unittest` brittle and creates hidden side effects during error recovery.

### Decision
We enforce a strict **two-layer separation**:
1. **Domain Layer (`teams.py`, `fixtures.py`, `standings.py`, `storage.py`):** Contains zero `input()` or `print()` statements. Functions accept explicit state structures (`teams`, `fixtures`), validate all preconditions first, and either return/mutate data atomically or raise a descriptive `ValueError`.
2. **Presentation Layer (`cli.py`, `main.py`):** Handles terminal menus, string formatting, user prompts, and `try/except ValueError` blocks.

### Consequences
* **Testability:** Every business rule (16+ test scenarios) can be tested directly in memory without mocking `sys.stdin` or `sys.stdout`.
* **Auditability:** Any state transition can be traced solely through function arguments and return values.

---

## 2. ADR-001: Immutable Surrogate IDs vs. Display Names

### Context
Teams register with human-readable display names (e.g., `"Red Comets"`). Users may submit names with leading/trailing whitespace or varying letter cases (`"  red comets "`).

### Decision
1. **Normalization on Entry:** Display names are trimmed via `.strip()` upon registration. Length must be strictly $2 \le \text{len(name)} \le 30$.
2. **Case-Insensitive Uniqueness:** Uniqueness is enforced by comparing `name.casefold()` against all existing registered teams. Unlike `.lower()`, `.casefold()` handles full Unicode case-folding reliably.
3. **Immutable Sequential IDs:** Each registered team receives a deterministic, zero-padded identifier (`TM001`, `TM002`, ..., `TM008`).
4. **Referential Integrity:** All fixtures reference teams exclusively via `home_id` and `away_id` (`TM001`), never by display name.

### Rationale & Defence Proof
If a future feature allows a team to update its display label, zero match records need to be rewritten, and historical fixtures cannot become orphaned.

---

## 3. ADR-002: Deterministic Round-Robin Combinatorics

### Context
A single round-robin tournament requires every registered team to play every other registered team once. Self-matches (`TM001` vs `TM001`) and reverse duplicates (`TM001` vs `TM002` followed by `TM002` vs `TM001`) must be impossible.

### Decision
We generate fixtures using bounded nested index iteration over the ordered `teams` list of length $N$ (where $4 \le N \le 8$):
* Outer loop index $i$ runs from $0$ to $N - 2$.
* Inner loop index $j$ runs from $i + 1$ to $N - 1$.
* Each pair `(teams[i]["id"], teams[j]["id"])` is assigned sequential match ID `M001`, `M002`, etc.

### Mathematical Invariant
For $N$ teams, the exact number of generated fixtures is:
$$\text{Fixtures}(N) = \frac{N(N - 1)}{2}$$
* $N = 4 \implies \frac{4 \times 3}{2} = 6$ fixtures
* $N = 6 \implies \frac{6 \times 5}{2} = 15$ fixtures
* $N = 8 \implies \frac{8 \times 7}{2} = 28$ fixtures

Because $j > i$ strictly holds in every iteration, self-pairing ($i = j$) and reversed duplicates ($j < i$) are mathematically excluded by construction. Furthermore, `generate_fixtures()` rejects execution if `existing_fixtures` is non-empty, preventing mid-season schedule resets.

---

## 4. ADR-003: Strict Integer Validation & The Python Boolean Trap

### Context
In Python's type hierarchy, `bool` is a subclass of `int` (`issubclass(bool, int) == True` and `isinstance(True, int) == True`). A naive score check such as `isinstance(score, int) and score >= 0` will accept `True` as `1` goal and `False` as `0` goals.

### Decision
We implement a dedicated helper `validate_score(value)` that enforces:
```python
if isinstance(value, bool) or not isinstance(value, int) or value < 0:
    raise ValueError("Score must be a non-negative integer (booleans are not allowed).")