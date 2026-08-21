#!/usr/bin/env bash
# Entra ID SFTP suite (storage account "02"). Deliberately NOT wired into
# tests/run_tests.sh: that script runs the account "01" suites concurrently and
# merges their reports, and this experiment is still being evaluated -- keeping
# it standalone means a failure here can't be mistaken for a regression in the
# working local-user stack.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENTRA_DIR="$REPO_ROOT/tests/entra"
VENV="$REPO_ROOT/tests/.venv"

COLOR="yes"
SWEEP="yes"
for arg in "$@"; do
  case "$arg" in
    --color=*) COLOR="${arg#*=}" ;;
    --sweep=*) SWEEP="${arg#*=}" ;;
  esac
done

source "$REPO_ROOT/env-dev.sh"
source "$ENTRA_DIR/env-entra.sh"

if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"
pip install -q -r "$REPO_ROOT/tests/requirements.txt"

REPORT="$ENTRA_DIR/report_entra.md"

PYTEST_EXIT=0
# --confcutdir stops pytest walking up into tests/conftest.py, which is bound
# at import time to account "01" (SFTP_STORAGE_ACCOUNT, the .aad_* dotfiles)
# and would otherwise both demand env vars this suite doesn't set and shadow
# the `from conftest import ...` in these test modules.
pytest "$ENTRA_DIR" -v --color="$COLOR" \
  --confcutdir="$ENTRA_DIR" \
  --md-report \
  --md-report-output="$REPORT" \
  --md-report-verbose=1 \
  --junitxml="$ENTRA_DIR/report_entra.xml" \
  --html="$ENTRA_DIR/report_entra.html" --self-contained-html || PYTEST_EXIT=$?

cat "$REPORT"

if [[ "$SWEEP" == "yes" ]]; then
  python3 "$ENTRA_DIR/sweep_artifacts.py"
fi

exit "$PYTEST_EXIT"
