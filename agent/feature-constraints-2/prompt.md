## Constraints 2

I want the below filters to be implemented as constraints instead of filters. That is, the optimizer should not output any lineups that do not satisfy the constraints. 

```
# Filters
p.add_argument("--min-player-projection", type=float, default=None, help=argparse.SUPPRESS)
p.add_argument("--min-sum-projection", type=float, default=None,
                help="Minimum total projection per lineup (replaces --min-player-projection)")
p.add_argument("--min-sum-ownership", type=float, default=None,
                help="Fraction 0..1")
p.add_argument("--max-sum-ownership", type=float, default=None,
                help="Fraction 0..1")
p.add_argument("--min-product-ownership", type=float, default=None)
p.add_argument("--max-product-ownership", type=float, default=None)
```

Because we are porting filters over to constraints, we can stop writing outputs for both "filtered" and "unfiltered". The output files can now just be called lineups.json and lineups.xlsx.

I can do any necessary filtering after I download the output, so you can remove any functionality related to that. Everything should be an optimizer constraint.

Convert this prompt into a spec and write to spec.md in the same folder.