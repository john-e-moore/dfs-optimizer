from dfs_optimizer.models import Player, Parameters
from dfs_optimizer.optimizer import LineupResult
from dfs_optimizer.filters import filter_lineups


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
    )


def test_filter_by_sum_ownership():
    l1 = make_lineup(sum_own=0.5)
    l2 = make_lineup(sum_own=1.6)
    params = Parameters(min_sum_ownership=0.6, max_sum_ownership=1.5)
    out = filter_lineups([l1, l2], params)
    assert len(out.lineups) == 0
    assert out.dropped == 2


def test_filter_by_min_player_projection():
    # Create a lineup where one player is below threshold
    players = list(make_lineup().players)
    players[3] = make_player("WR_low", "WR", proj=0.1, own=0.05)
    bad = LineupResult(
        players=tuple(players),
        total_projection=sum(p.projection for p in players),
        total_salary=sum(p.salary for p in players),
        sum_ownership=1.0,
        product_ownership=1e-6,
        weighted_ownership=sum((p.salary/50000.0)*p.ownership for p in players),
        stack_positions=("WR",),
        max_game_stack=3,
        max_game_key="A-B",
        stack_count=1,
        all_game_stacks=(("A-B", 3),),
        rb_dst_stack=False,
    )
    good = make_lineup()
    params = Parameters(min_player_projection=1.0)
    out = filter_lineups([bad, good], params)
    assert len(out.lineups) == 1
    assert out.dropped == 1


def test_filter_by_product_ownership():
    low = make_lineup(prod_own=1e-12)
    high = make_lineup(prod_own=0.2)
    params = Parameters(min_product_ownership=1e-9, max_product_ownership=0.1)
    out = filter_lineups([low, high], params)
    assert len(out.lineups) == 0
    assert out.dropped == 2
