from __future__ import annotations

from typing import Dict

from src.constraints import parse_rules_mapping, ConstraintRule
from src.models import Parameters
from src.showdown import ShowdownEntry, generate_lineups_showdown


def _make_entry(name: str, team: str, opponent: str, position: str, role: str) -> ShowdownEntry:
    # Keep salaries well under 50k cap even with 6 players; projections arbitrary.
    return ShowdownEntry(
        name=name,
        team=team.upper(),
        opponent=opponent.upper(),
        position=position.upper(),
        role=role.upper(),
        salary=7500,
        projection=10.0,
        ownership=0.1,
    )


def _build_min_5_from_one_team_rule() -> Dict[str, ConstraintRule]:
    raw_rules = {
        "min_5_from_one_team": {
            "enforce": [
                {
                    "any_of": [
                        {
                            "count": {
                                "selector": {"team": "TEAM_A"},
                                "min": 5,
                            }
                        },
                        {
                            "count": {
                                "selector": {"team": "TEAM_B"},
                                "min": 5,
                            }
                        },
                    ]
                }
            ]
        }
    }
    return parse_rules_mapping(raw_rules)


def test_generate_lineups_respects_min_5_from_one_team_rule():
    # Build a synthetic pool: enough CPT/FLEX variants from both teams to satisfy the rule.
    entries = []
    # TEAM_A CPT + FLEX
    entries.append(_make_entry("A_CPT", "TEAM_A", "TEAM_B", "WR", "CPT"))
    for i in range(1, 6):
        entries.append(_make_entry(f"A_FLEX{i}", "TEAM_A", "TEAM_B", "WR", "FLEX"))
    # TEAM_B CPT + FLEX
    entries.append(_make_entry("B_CPT", "TEAM_B", "TEAM_A", "WR", "CPT"))
    for i in range(1, 6):
        entries.append(_make_entry(f"B_FLEX{i}", "TEAM_B", "TEAM_A", "WR", "FLEX"))

    params = Parameters(
        lineup_count=5,
        min_salary=0,  # keep salary constraint loose for synthetic test
        solver_threads=1,
    )
    rules = _build_min_5_from_one_team_rule()

    lineups = generate_lineups_showdown(entries, params, rules=rules)

    # We expect some lineups (at least one) and each must satisfy the rule:
    # at least 5 players from TEAM_A or TEAM_B.
    assert len(lineups) >= 1
    for lu in lineups:
        teams = [e.team for e in lu.entries]
        count_a = sum(1 for t in teams if t == "TEAM_A")
        count_b = sum(1 for t in teams if t == "TEAM_B")
        assert (
            count_a >= 5 or count_b >= 5
        ), f"Lineup violates min_5_from_one_team: TEAM_A={count_a}, TEAM_B={count_b}"


