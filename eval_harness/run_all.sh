#!/usr/bin/env bash
# Full harness: real data pull -> correlation engine -> TimesFM zero-shot test.
# Setup: uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python pandas numpy scipy statsmodels requests torch "jax[cpu]" \
#   "timesfm[torch,xreg] @ https://github.com/google-research/timesfm/archive/refs/heads/master.zip"
set -euo pipefail
cd "$(dirname "$0")"
.venv/bin/python fetch_data.py
.venv/bin/python check_correlation.py | tee results/correlation_stdout.txt
.venv/bin/python test_timesfm.py | tee results/timesfm_stdout.txt
echo "see REPORT.md"
