#!/usr/bin/env bash
# Quick test runner for WEIS
# Usage:
#   ./test.sh          — run everything
#   ./test.sh phase-b  — just the 10 rate validation targets
#   ./test.sh new      — just Phase A + Phase B tests (skip v1.3)
#   ./test.sh fast     — everything, stop on first failure

set -e
cd "$(dirname "$0")"

# Activate venv if not already active
if [[ -z "$VIRTUAL_ENV" ]]; then
    source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate 2>/dev/null || true
fi

case "${1:-all}" in
    phase-b|b|rates)
        echo "=== Phase B: Rate Validation (10 targets) ==="
        python -m pytest tests/test_phase_b_validation.py -v
        ;;
    new|ab)
        echo "=== Phase A + B Tests Only ==="
        python -m pytest tests/test_transform.py tests/test_hcss_client.py tests/test_phase_b_validation.py -v
        ;;
    fast|f)
        echo "=== All Tests (stop on first failure) ==="
        python -m pytest tests/ -v -x
        ;;
    all|"")
        echo "=== All Tests ==="
        python -m pytest tests/ -v
        ;;
    *)
        echo "Usage: ./test.sh [phase-b | new | fast | all]"
        exit 1
        ;;
esac
