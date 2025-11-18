For showdown slates, there are a lot of team- and position-specific optimization constraints that I need to be able to specify for contests of different sizes. Keep in mind showdown slates allow players from just a single NFL game.

For example, I might want to disallow having a QB from team A in the captain (CPT) spot while also rostering DST from team B. I might want to force at least two (RB, WR, TE) from team A any time I have the QB of that team as CPT. I might want to specify minimum of 4 players from team A OR a minimum of 4 players from team B. so on and so forth. 

I want to specify these constraints in contests-showdown.yaml. We need to come up with a syntax or language I can use to enter each custom constraint I want for the contests of various sizes. Then, of course, the optimizer will need to understand that synax and apply the constraints when lineups are being generated.

Describe how you would want to implement this and show me what the constraint syntax would look like in contests-showdown.yaml. After that, we can refine your idea before moving on to planning implementation steps.