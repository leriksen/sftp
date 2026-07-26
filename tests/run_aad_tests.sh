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

REPORT="$REPO_ROOT/tests/report_aad.md"

PYTEST_EXIT=0
pytest "$REPO_ROOT/tests/test_aad_rbac.py" -v --color="$COLOR" \
  --md-report \
  --md-report-output="$REPORT" \
  --md-report-verbose=1 \
  --junitxml="$REPO_ROOT/tests/report_aad.xml" \
  --html="$REPO_ROOT/tests/report_aad.html" --self-contained-html || PYTEST_EXIT=$?

cat "$REPORT"

# --sweep=no when run under run_tests.sh: the AAD and SFTP suites run
# concurrently there, and sweeping here could delete the sibling suite's
# still-in-flight artifacts (see conftest.sweep_leftover_artifacts).
if [[ "$SWEEP" == "yes" ]]; then
  python3 "$REPO_ROOT/tests/sweep_artifacts.py"
fi

exit "$PYTEST_EXIT"
