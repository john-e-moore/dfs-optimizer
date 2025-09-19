# Sabersim

This branch will enable us to read players, projections, and ownerships from a different data file. 

Enable the user to pass flag '-ss' to read from the most recent .xlsx file in the 'data/' folder with prefix 'NFL_' instead of reading from 'data/DraftKings NFL DFS Projections -- Main Slate.csv'.

Player name is in column B ("Name"). projection is in column I ("SS Proj"). ownership is in column N ("Adj Own").

If this flag is passed, instead of looking in 'data/DKEntries.csv' for player ID's, instead fetch it from column A "DFS ID" of this new data source.

Create a spec for this feature and write it to agent/feature-sabersim/spec.md.