## Constraints

Implement the following constraints or changes to constraints:
- Change: Change min_player_projection to min_sum_projection; I want the user to be able to specify the minimum lineups projection, not for each player.
- Pruning: exclude specific players. Allow user to specify one or multiple players (e.g. "Joe Burrow" or ["Joe Burrow", "Patrick Mahomes"]) and remove those players from the players pool.
- Pruning: include specific players. Allow user to specify one or multiple players who must be included in all lineups.
- Pruning: Exclude team. Allow the player to enter a team, and then exclude all players on that team from the player pool (e.g. "CAR" or ["BUF", "CAR"])
- Constraint: Include minimum number of players on team. If user enters, for instance, "CAR: 3" then all lineups must contain at least 3 players on team CAR.
- Constraint: RB/DST stack. If True, all lineups must contain an RB on the same team as the DST in the lineup.