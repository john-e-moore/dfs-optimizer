from src.models import Player, Parameters
from src.optimizer import LineupResult


def make_player(name: str, pos: str, team: str = "A", opp: str = "B", salary: int = 5000, proj: float = 10.0, own: float = 0.1):
    return Player(name=name, team=team, opponent=opp, position=pos, salary=salary, projection=proj, ownership=own)


def make_lineup(sum_own: float = 1.0, prod_own: float = 1e-6, min_proj: float = 5.0):
    players = (
        make_player("QB1", "QB", proj=max(10.0, min_proj), own=sum_own / 9),
        make_player("RB1", "RB", own=sum_own / 9),
        make_player("RB2", "RB", own=sum_own / 9),
        make_player("WR1", "WR", own=sum_own / 9),
        make_player("WR2", "WR", own=sum_own / 9),
        make_player("WR3", "WR", own=sum_own / 9),
        make_player("TE1", "TE", own=sum_own / 9),
        make_player("FLEX", "WR", own=sum_own / 9),
        make_player("DST1", "DST", opp="A", team="B", own=sum_own / 9),
    )
    return LineupResult(
        players=players,
        total_projection=sum(p.projection for p in players),
        total_salary=sum(p.salary for p in players),
        sum_ownership=sum_own,
        product_ownership=prod_own,
        weighted_ownership=sum((p.salary/50000.0)*p.ownership for p in players),
        stack_positions=("WR",),
        max_game_stack=3,
        max_game_key="A-B",
        stack_count=1,
        all_game_stacks=(("A-B", 3),),
        rb_dst_stack=False,
        bringback_stack=False,
    )


def test_lineup_result_fields_present():
    lu = make_lineup(sum_own=1.0)
    assert lu.total_projection > 0
    assert 0 <= lu.sum_ownership <= 9.0
    assert lu.product_ownership > 0


def test_lineup_projection_and_ownership_computed():
    lu = make_lineup(sum_own=1.8, prod_own=1e-6)
    assert isinstance(lu.total_projection, float)
    assert isinstance(lu.total_salary, int)


def test_lineup_product_ownership_range():
    low = make_lineup(prod_own=1e-12)
    high = make_lineup(prod_own=0.2)
    assert 0 < low.product_ownership <= 1
    assert 0 < high.product_ownership <= 1
