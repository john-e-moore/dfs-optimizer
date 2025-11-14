The first objective with this branch will be to classify the contests I have entered based on the number of entrants.

(1) Download the day's contests json from s3
 - get environment variables from 'src/config.py' (file already done)
 - s3 URI: 's3://{s3_bucket}/{s3_prefix}/{date}/nfl/contests.json'
 - write to 'data/contests.json'
(2) Read 'data/DKEntries.csv' (local) into dataframe
(3) Look up each contest in contests.json using the 'Contest ID' (will be 'id' field in contests.json)
(4) These contests should all have the same value for "dg" -- this is the slate ID
(5) Download the players ('playables') for that slate -- {dg}.json from the same folder we got contests.json 
(6) Join number of entrants onto DKEntries dataframe ("m" field in contests.json)
  - 'num_entrants'
  - 'field_size_classification'