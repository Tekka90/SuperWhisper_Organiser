#!/usr/bin/env bash
# run_tests.sh — Run the SuperWhisper Organiser unit-test suite.
#
# Usage:
#   ./run_tests.sh           # run all tests
#   ./run_tests.sh -k db     # run only tests whose name matches "db"
#   ./run_tests.sh --cov     # run with coverage report (requires pytest-cov)
#
# The script activates the project virtualenv automatically if it exists.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# ── Activate virtualenv if present ──────────────────────────────────────────
if [[ -d "venv" ]]; then
    # shellcheck source=/dev/null
    source venv/bin/activate
    echo "✓ Activated virtualenv"
fi

# ── Install test dependencies if not already present ────────────────────────
python -m pip install --quiet pytest pytest-cov 2>/dev/null || true

# ── Parse optional --cov flag ───────────────────────────────────────────────
EXTRA_ARGS=()
COVERAGE=false
for arg in "$@"; do
    if [[ "$arg" == "--cov" ]]; then
        COVERAGE=true
    else
        EXTRA_ARGS+=("$arg")
    fi
done

# ── Build pytest command ────────────────────────────────────────────────────
CMD=(python -m pytest)

if $COVERAGE; then
    CMD+=(
        --cov=.
        --cov-report=term-missing
        --cov-omit="tests/*,venv/*,setup.py"
    )
fi

CMD+=("${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}")

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Running SuperWhisper Organiser unit tests"
echo "═══════════════════════════════════════════════════"
echo ""

"${CMD[@]}"
