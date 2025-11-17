Objective: Incorporate a flag to the cli "--showdown" that optimizes lineups for DraftKings showdown captain-mode. 

Details
- Same lineups.xlsx output as our normal runs ("classic" mode rather than showdown).
- The projections will be Sabersim projections in the 'data' directory with the same 'NFL_*.csv' pattern as usual.
- In showdown DFS, we have the same $50,000 salary cap for six players: CPT, FLEX, FLEX, FLEX, FLEX, FLEX. Positions do not matter; any player can be played in any roster spot. The captain (CPT) costs 1.5x his regular salary and scores 1.5x as many points.
- In the Sabersim projections CSV, each player will be present in 2 rows. The one with the greater salary is that player's CPT row and the other one is that player's FLEX row. When you read in the projections, you will need to add a column with those labels ('CPT', 'FLEX') for every row.
- When creating lineups, each FLEX spot should be treated the same. Moving a player from the first FLEX spot to the fourth does not make it a different lineup, similar to how moving the WR to a different WR spot does not change things.
- When reading in the projections, drop rows where the player's point projection is zero.
- When creating your plan, read the projections .csv in the 'data/' directory to make sure you know how to handle it.
- Be sure that in addition to changing the source code you also change the run.sh script to accomodate the '--showdown' flag. For instance I might execute 'bash run.sh --sabersim --showdown' in the terminal.