#!/usr/bin/env bash
# Dry-run the full analysis pipeline on the latest recording folder (verbose, no DB writes).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Activate virtualenv
source "$PROJECT_ROOT/venv/bin/activate"

# Read recordings path from config.yaml, expand ~
RECORDINGS_DIR=$(python3 -c "
import yaml, os
with open('$PROJECT_ROOT/config.yaml') as f:
    cfg = yaml.safe_load(f)
print(os.path.expanduser(cfg['paths']['recordings']))
")

if [[ ! -d "$RECORDINGS_DIR" ]]; then
    echo "ERROR: Recordings directory not found: $RECORDINGS_DIR" >&2
    exit 1
fi

# Find the latest recording folder (most recent by name, which is date-based)
LATEST=$(find "$RECORDINGS_DIR" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)

if [[ -z "$LATEST" ]]; then
    echo "ERROR: No recording folders found in $RECORDINGS_DIR" >&2
    exit 1
fi

echo "Latest recording: $LATEST"
echo ""

exec python3 "$SCRIPT_DIR/test_analysis.py" --verbose "$LATEST"
