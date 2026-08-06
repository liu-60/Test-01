#!/bin/sh
set -u

mkdir -p /logs/verifier
reward=0.0

if PYTHONDONTWRITEBYTECODE=1 python3 /tests/test_behavior.py; then
  reward=1.0
fi

printf '%s\n' "$reward" > /logs/verifier/reward.txt
test "$reward" = "1.0"
