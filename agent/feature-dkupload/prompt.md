# DKUpload

I need to add an additional tab to all of the output that gives the lineups in a form that I can upload to DraftKings. That is, each player name must be in the form of "{player_name} ({player_id})". For example, "Justin Herbert (40058159)". Player names and ID's can be found in the file 'data/DKEntries.csv' in column P starting in the 8th row. Match the ID to the player name in 'DraftKings NFL DFS Projections -- Main Slate.csv'. If any of the players in that .csv cannot be found in DKEntries.csv, write that in the log.

Any time I run run.sh, run_game_stacks.sh, or run_qb_stacks.sh, the final output spreadsheet needs a tab identical to the 'Lineups' tab but with the player names formatted as I have specified above. No ownership percentages. Bad: "{player_name} ({ownership_pct})". Good: "{player_name} ({player_id})". Call the new tab 'DK Lineups'. We need this tab in 'lineups.xlsx', 'qb_stacks.xlsx, and 'game_stacks.xlsx'. 

Write a spec to implement this to 'agent/feature-dkupload/spec.md'. 

