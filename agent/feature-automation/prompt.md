The first objective with this branch will be to classify the contests I have entered based on the number of entrants.

Let's make a script 'scripts/get_contests.py' that does the following. I will pass the {date} parameter in the format 'YYYY-MM-DD' when running the script.

The S3 files to be downloaded from 

(1) Download the day's contests json from s3
 - env variables:
    - s3_bucket=os.getenv("DK_CONTESTS_S3_BUCKET", ""),
    - s3_prefix=os.getenv("DK_CONTESTS_S3_PREFIX", ""),
    - aws_region=os.getenv("DK_CONTESTS_AWS_REGION", "us-east-2")
 - if bucket or prefix are empty, throw an error
 - s3 URI: 's3://{s3_bucket}/{s3_prefix}/{date}/nfl/contests.json'
 - write to 'data/contests.json'
(2) Read 'data/DKEntries.csv' (local) columns A through N into dataframe
(3) Look up each contest in contests.json using the 'Contest ID' (will be 'id' field in contests.json)
(4) These contests should all have the same value for "dg" -- this is the slate ID
(5) Download the players ('playables') for that slate -- {dg}.json from the same folder we got contests.json. dg will be a number, so the file name should be something like "136970.json" from 's3://{s3_bucket}/{s3_prefix}/{date}/nfl/136716.json. This file won't be used in this script.
(6) Join number of entrants onto DKEntries dataframe ("m" field in contests.json)
  - 'num_entrants'
  - 'field_size_classification' - get this from contests.yaml. for instance, if the contest has 1500 entries, it would be 'medium'.
(7) Write DKEntriesClassified.csv to the 'data/' folder.
