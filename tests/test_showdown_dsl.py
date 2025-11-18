from __future__ import annotations

from typing import Dict

from src.constraints import parse_rules_mapping, ConstraintRule
from src.showdown import ShowdownEntry, _violated_rules


def _make_entry(name: str, team: str, opponent: str, position: str, role: str) -> ShowdownEntry:
    # Salary / projection / ownership values are irrelevant for DSL selector logic
    return ShowdownEntry(
        name=name,
        team=team.upper(),
        opponent=opponent.upper(),
        position=position.upper(),
        role=role.upper(),
        salary=5000,
        projection=10.0,
        ownership=0.1,
    )


def _build_example_rules() -> Dict[str, ConstraintRule]:
    raw_rules = {
        "no_cpt_qbA_with_dstB": {
            "enforce": [
                {
                    "forbid": {
                        "left": {
                            "selector": {
                                "slot": "CPT",
                                "pos": "QB",
                                "team": "TEAM_A",
                            }
                        },
                        "right": {
                            "selector": {
                                "type": "DST",
                                "team": "TEAM_B",
                            }
                        },
                    }
                }
            ]
        },
        "qbA_cpt_requires_2_rb_wr_te_A": {
            "when": {
                "count": {
                    "selector": {
                        "slot": "CPT",
                        "pos": "QB",
                        "team": "TEAM_A",
                    },
                    "min": 1,
                }
            },
            "enforce": [
                {
                    "count": {
                        "selector": {
                            "team": "TEAM_A",
                            "pos_in": ["RB", "WR", "TE"],
                        },
                        "min": 2,
                    }
                }
            ],
        },
        "min_4_from_one_team": {
            "enforce": [
                {
                    "any_of": [
                        {
                            "count": {
                                "selector": {"team": "TEAM_A"},
                                "min": 4,
                            }
                        },
                        {
                            "count": {
                                "selector": {"team": "TEAM_B"},
                                "min": 4,
                            }
                        },
                    ]
                }
            ]
        },
    }
    return parse_rules_mapping(raw_rules)


def test_forbid_cpt_qb_with_opposing_dst():
    rules = _build_example_rules()
    lineup = [
        _make_entry("QB_A_CPT", "TEAM_A", "TEAM_B", "QB", "CPT"),
        _make_entry("RB_A", "TEAM_A", "TEAM_B", "RB", "FLEX"),
        _make_entry("WR_A", "TEAM_A", "TEAM_B", "WR", "FLEX"),
        _make_entry("WR_B", "TEAM_B", "TEAM_A", "WR", "FLEX"),
        _make_entry("TE_B", "TEAM_B", "TEAM_A", "TE", "FLEX"),
        _make_entry("DST_B", "TEAM_B", "TEAM_A", "DST", "FLEX"),
    ]
    violated, names = _violated_rules(lineup, rules)
    assert violated
    assert "no_cpt_qbA_with_dstB" in names

    # Removing DST_B should satisfy that rule
    lineup_no_dst = lineup[:-1]
    violated2, names2 = _violated_rules(lineup_no_dst, rules)
    assert "no_cpt_qbA_with_dstB" not in names2


def test_qb_cpt_requires_two_skill_players_from_team():
    rules = _build_example_rules()

    # Only one RB/WR/TE from TEAM_A -> violates rule when QB_A is CPT
    lineup_bad = [
        _make_entry("QB_A_CPT", "TEAM_A", "TEAM_B", "QB", "CPT"),
        _make_entry("WR_A", "TEAM_A", "TEAM_B", "WR", "FLEX"),
        _make_entry("WR_B1", "TEAM_B", "TEAM_A", "WR", "FLEX"),
        _make_entry("WR_B2", "TEAM_B", "TEAM_A", "WR", "FLEX"),
        _make_entry("TE_B", "TEAM_B", "TEAM_A", "TE", "FLEX"),
        _make_entry("DST_B", "TEAM_B", "TEAM_A", "DST", "FLEX"),
    ]
    violated_bad, names_bad = _violated_rules(lineup_bad, rules)
    assert violated_bad
    assert "qbA_cpt_requires_2_rb_wr_te_A" in names_bad

    # Two skill players from TEAM_A -> rule satisfied
    lineup_good = [
        _make_entry("QB_A_CPT", "TEAM_A", "TEAM_B", "QB", "CPT"),
        _make_entry("WR_A1", "TEAM_A", "TEAM_B", "WR", "FLEX"),
        _make_entry("WR_A2", "TEAM_A", "TEAM_B", "WR", "FLEX"),
        _make_entry("WR_B", "TEAM_B", "TEAM_A", "WR", "FLEX"),
        _make_entry("TE_B", "TEAM_B", "TEAM_A", "TE", "FLEX"),
        _make_entry("DST_B", "TEAM_B", "TEAM_A", "DST", "FLEX"),
    ]
    violated_good, names_good = _violated_rules(lineup_good, rules)
    # May still violate no_cpt_qbA_with_dstB because DST_B is present, but should not
    # violate the 2-skill-player rule.
    assert "qbA_cpt_requires_2_rb_wr_te_A" not in names_good


def test_min_4_from_one_team_any_of_logic():
    rules = _build_example_rules()

    # 3 vs 3 split -> violates min_4_from_one_team
    lineup_split = [
        _make_entry("CPT_A", "TEAM_A", "TEAM_B", "WR", "CPT"),
        _make_entry("A1", "TEAM_A", "TEAM_B", "WR", "FLEX"),
        _make_entry("A2", "TEAM_A", "TEAM_B", "RB", "FLEX"),
        _make_entry("B1", "TEAM_B", "TEAM_A", "WR", "FLEX"),
        _make_entry("B2", "TEAM_B", "TEAM_A", "RB", "FLEX"),
        _make_entry("B3", "TEAM_B", "TEAM_A", "TE", "FLEX"),
    ]
    violated_split, names_split = _violated_rules(lineup_split, rules)
    assert violated_split
    assert "min_4_from_one_team" in names_split

    # 4 from TEAM_A -> satisfies any_of
    lineup_four_a = [
        _make_entry("CPT_A", "TEAM_A", "TEAM_B", "WR", "CPT"),
        _make_entry("A1", "TEAM_A", "TEAM_B", "WR", "FLEX"),
        _make_entry("A2", "TEAM_A", "TEAM_B", "RB", "FLEX"),
        _make_entry("A3", "TEAM_A", "TEAM_B", "TE", "FLEX"),
        _make_entry("B1", "TEAM_B", "TEAM_A", "WR", "FLEX"),
        _make_entry("B2", "TEAM_B", "TEAM_A", "RB", "FLEX"),
    ]
    violated_four_a, names_four_a = _violated_rules(lineup_four_a, rules)
    assert not violated_four_a or "min_4_from_one_team" not in names_four_a


