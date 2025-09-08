## Objective
Build a lineup optimizer for daily fantasy football that optimizes for maximum points ("Projection" column), subject to various constraints. 

The projection data is located at "data/DraftKings NFL DFS Projections -- Main Slate.csv".

## Constraints / Parameters
- Optimize for maximum lineup "Projection". That is the sum of the projection of each player in the lineup.
- Each lineup must have 1 QB, 2 RB, 3 WR, 1 TE, 1 DST, and 1 FLEX. The FLEX spot can contain either RB, WR, or TE.
- Total salary (sum of "Salary" for each player in the lineup) must sum to less than 50000. Maximum salary will always be 50000. Set the minimum salary to 45000, but allow the user to change this.
- Number of lineups generated - allow the user to specify, but default to 5000 for this initial run. 
- Allow lineups with QB and DST on opposing teams (default: False)
- "Stack" parameter - number of WR or TE to pair with QB from same team (default: 1)
- "Game stack" parameter - minimum number of players from the same game. You can figure out which two teams are playing in a game by looking at the "Team" and "Opponent" columns. For instance, ATL and TB play this week. If the game stack parameter is set to 5, we would need at least 5 players from that game in each lineup. (default: 0)

## Filters
- Minimum projection (defualt: None)
- Maximum sum ownership. Sum ownership is the "Ownership" of each player in the lineup summed. (default: None)
- Minimum sum ownership (default: None)
- Maximum product ownership. Product ownership is the "Ownership" of each player multiplied together (default: None)
- Minimum product ownership (default: None)

## Output
- Output an excel spreadsheet with 3 tabs: "Projections", "Lineups" and "Parameters"
- The "Projections" tab is a copy of the input projections sheet.
- The "Parameters" tab shows which parameters were used to run the optimization.
- The "Lineups" tab shows the optimal lineups in descending rank order, one lineup in each row. 
 - Column A: Rank
 - Column B: Projection - The sum of projected points of all players in the lineup
 - Column C: Sum Ownership - The sum of ownership of all players in the lineup
 - Column D: Product Ownership - The product of ownership of all players in the lineup in a human readable format (multiplied by a large number)
 - Column E: Stack - List the positions players who are stacked with the QB. For instance "WR", or "RB,WR".
 - Column F: Game Stack - List the maximum number of players in the same game in the lineup. 
 - The remaining columns are for player names with thier team in parentheses. The order: QB, RB, RB, WR, WR, WR, TE, FLEX, DST. For instance, column E might have "Patrick Mahomes (KC)". Column I might have "Courtland Sutton (DEN)".
 
 The optimizer will run with the given constraints and show results in descending order of total projection. Write this intermediate results to "output/unfiltered_lineups.xlsx". If the user enabled any filters, apply those and write to "output/filtered_lineups.xlsx"

 ## Code details
 - Use numpy/Pandas/scikitlearn ecosystem
 - Use classes or dataclasses when appropriate to encapsulate logic and make the components reuseable.
 - Keep the code clean, well-commented, and easy to understand. 
 - User verbose and easy to understand variable names.
 - Write intermediate output to the output folder whenever the data is transformed; we need visibility during development.