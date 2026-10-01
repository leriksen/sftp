#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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
source "$REPO_ROOT/tests/env-test.sh"

if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"
pip install -q -r "$REPO_ROOT/tests/requirements.txt"

REPORT="$REPO_ROOT/tests/report_sftp.md"

PYTEST_EXIT=0
pytest "$REPO_ROOT/tests/test_sftp_home.py" "$REPO_ROOT/tests/test_sftp_traverse_only.py" "$REPO_ROOT/tests/test_sftp_overlap.py" -v --color="$COLOR" \
  --md-report \
  --md-report-output="$REPORT" \
  --md-report-verbose=1 \
  --junitxml="$REPO_ROOT/tests/report_sftp.xml" \
  --html="$REPO_ROOT/tests/report_sftp.html" --self-contained-html || PYTEST_EXIT=$?

cat "$REPORT"

# --sweep=no skips the leftover-artifact sweep (see
# conftest.sweep_leftover_artifacts) when another pytest session is still
# using the account.
if [[ "$SWEEP" == "yes" ]]; then
  python3 "$REPO_ROOT/tests/sweep_artifacts.py"
fi

exit "$PYTEST_EXIT"
