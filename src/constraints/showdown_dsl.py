from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml  # type: ignore


@dataclass(frozen=True)
class Selector:
    slot: Optional[str] = None
    team: Optional[str] = None
    pos: Optional[str] = None
    pos_in: Optional[List[str]] = None
    type: Optional[str] = None


@dataclass(frozen=True)
class CountCondition:
    selector: Selector
    min: Optional[int] = None
    max: Optional[int] = None


@dataclass(frozen=True)
class ForbidCondition:
    left: Selector
    right: Selector


ConstraintClause = Union["CountCondition", "ForbidCondition", "AnyOf"]


@dataclass(frozen=True)
class AnyOf:
    options: List[ConstraintClause]


@dataclass(frozen=True)
class ConstraintRule:
    name: str
    when: Optional[CountCondition]
    enforce: List[ConstraintClause]


def _parse_selector(data: Any) -> Selector:
    if not isinstance(data, dict):
        raise ValueError(f"selector must be a mapping, got {type(data).__name__}")
    pos_in_raw = data.get("pos_in")
    pos_in: Optional[List[str]] = None
    if pos_in_raw is not None:
        if isinstance(pos_in_raw, list):
            pos_in = [str(x).upper() for x in pos_in_raw]
        else:
            raise ValueError("selector.pos_in must be a list if provided")
    return Selector(
        slot=str(data["slot"]).upper() if "slot" in data and data["slot"] is not None else None,
        team=str(data["team"]).upper() if "team" in data and data["team"] is not None else None,
        pos=str(data["pos"]).upper() if "pos" in data and data["pos"] is not None else None,
        pos_in=pos_in,
        type=str(data["type"]).upper() if "type" in data and data["type"] is not None else None,
    )


def _parse_int_or_none(value: Any, field_name: str) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"{field_name} must be an integer if provided") from exc


def _parse_count_condition(data: Any) -> CountCondition:
    if not isinstance(data, dict):
        raise ValueError("count condition must be a mapping")
    if "selector" not in data:
        raise ValueError("count condition missing required 'selector'")
    selector = _parse_selector(data["selector"])
    min_v = _parse_int_or_none(data.get("min"), "min")
    max_v = _parse_int_or_none(data.get("max"), "max")
    return CountCondition(selector=selector, min=min_v, max=max_v)


def _parse_forbid_condition(data: Any) -> ForbidCondition:
    if not isinstance(data, dict):
        raise ValueError("forbid condition must be a mapping")
    if "left" not in data or "right" not in data:
        raise ValueError("forbid condition requires 'left' and 'right' selectors")
    left_raw = data["left"]
    right_raw = data["right"]
    # Allow either direct selector fields or nested {"selector": {...}}
    if isinstance(left_raw, dict) and "selector" in left_raw:
        left_raw = left_raw["selector"]
    if isinstance(right_raw, dict) and "selector" in right_raw:
        right_raw = right_raw["selector"]
    left = _parse_selector(left_raw)
    right = _parse_selector(right_raw)
    return ForbidCondition(left=left, right=right)


def _parse_any_of(data: Any) -> AnyOf:
    if not isinstance(data, list):
        raise ValueError("any_of must be a list")
    options: List[ConstraintClause] = []
    for entry in data:
        options.append(_parse_enforce_clause(entry))
    if not options:
        raise ValueError("any_of requires at least one option")
    return AnyOf(options=options)


def _parse_enforce_clause(data: Any) -> ConstraintClause:
    if not isinstance(data, dict):
        raise ValueError("enforce clause must be a mapping")
    if "count" in data:
        return _parse_count_condition(data["count"])
    if "forbid" in data:
        return _parse_forbid_condition(data["forbid"])
    if "any_of" in data:
        return _parse_any_of(data["any_of"])
    raise ValueError("enforce clause must contain one of: 'count', 'forbid', 'any_of'")


def parse_rule(name: str, data: Any) -> ConstraintRule:
    if not isinstance(data, dict):
        raise ValueError(f"rule '{name}' must be a mapping")
    when_raw = data.get("when")
    when: Optional[CountCondition] = None
    if when_raw is not None:
        # Currently support only 'count' in when
        if not isinstance(when_raw, dict) or "count" not in when_raw:
            raise ValueError(f"rule '{name}': 'when' must be of the form {{count: ...}}")
        when = _parse_count_condition(when_raw["count"])

    enforce_raw = data.get("enforce")
    if not isinstance(enforce_raw, list) or not enforce_raw:
        raise ValueError(f"rule '{name}' must have a non-empty 'enforce' list")
    enforce: List[ConstraintClause] = [_parse_enforce_clause(entry) for entry in enforce_raw]
    return ConstraintRule(name=name, when=when, enforce=enforce)


def parse_rules_mapping(rules: Dict[str, Any]) -> Dict[str, ConstraintRule]:
    """
    Parse a mapping of rule-name -> rule-config into ConstraintRule objects.
    """
    out: Dict[str, ConstraintRule] = {}
    for name, cfg in rules.items():
        if not isinstance(name, str):
            raise ValueError("rule names must be strings")
        out[name] = parse_rule(name, cfg)
    return out


def load_rules_for_label_from_yaml(yaml_path: str | Path, label: str) -> Dict[str, ConstraintRule]:
    """
    Load and parse showdown rules for a specific field-size label from a contests-showdown YAML file.
    Returns an empty dict if no rules are defined for that label.
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Showdown rules YAML not found at {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected YAML structure in {path}; expected a mapping")
    cfg = data.get(label)
    if not isinstance(cfg, dict):
        return {}
    constraints = cfg.get("constraints") or {}
    if not isinstance(constraints, dict):
        return {}
    raw_rules = constraints.get("rules") or {}
    if not isinstance(raw_rules, dict) or not raw_rules:
        return {}
    return parse_rules_mapping(raw_rules)



