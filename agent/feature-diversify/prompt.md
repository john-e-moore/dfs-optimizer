My run_bundle_multiple.sh script combines lineups from multiple runs into a single excel spreadsheet. For instance, my last bundle run for small-field tournaments looked like this:

# Small (<1k)
bash run.sh --ss --lineups 250 --stack 2 --max-weighted-ownership 23 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 23 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 24 --min-salary 49600 --game-stack 5

I need a way to maximize lineup diversification in an arbitrary number of lineups from each of these spreadsheets. For instance, I might want to pick 10 linups and have the diversification algorithm spit out the 10 that diversify me the most. Come up with a plan for this, then write a spec to 'agent/feature-diversify/spec.md'. 