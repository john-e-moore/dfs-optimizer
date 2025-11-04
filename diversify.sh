#!/usr/bin/env bash
set -euo pipefail

bash run_diversify.sh \
  --input output/20251102_113751/small_u1k.xlsx \
  --input output/20251102_113751/medium_1k_3k.xlsx \
  --input output/20251102_113751/large_o3k.xlsx \
  --pick output/20251102_113751/small_u1k.xlsx:5 \
  --pick output/20251102_113751/medium_1k_3k.xlsx:6 \
  --pick output/20251102_113751/large_o3k.xlsx:5 \
  --out output/20251102_113751/diversified.xlsx