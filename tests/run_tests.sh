#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORT="$SCRIPT_DIR/report.md"

# --sweep=no: the two suites run concurrently below, so each one sweeping
# its own leftovers at exit could delete the sibling suite's still-in-flight
# artifacts. Sweep once, ourselves, after both have fully finished instead.
bash "$SCRIPT_DIR/run_aad_tests.sh" --sweep=no "$@" &
AAD_PID=$!

bash "$SCRIPT_DIR/run_sftp_tests.sh" --sweep=no "$@" &
SFTP_PID=$!

AAD_EXIT=0;  wait "$AAD_PID"  || AAD_EXIT=$?
SFTP_EXIT=0; wait "$SFTP_PID" || SFTP_EXIT=$?

# Merge reports
{
  echo "## AAD RBAC tests"
  echo ""
  cat "$SCRIPT_DIR/report_aad.md"
  echo ""
  echo "## SFTP tests"
  echo ""
  cat "$SCRIPT_DIR/report_sftp.md"
} > "$REPORT"

echo ""
echo "=== Combined report ==="
cat "$REPORT"

# Merge the two suites' JUnit XML into one <testsuites> document.
python3 "$SCRIPT_DIR/merge_junit.py" \
  "$SCRIPT_DIR/report_aad.xml" "$SCRIPT_DIR/report_sftp.xml" \
  "$SCRIPT_DIR/report.xml"

# Combined HTML report: a small wrapper embedding each suite's
# self-contained pytest-html report (source links + bytes sent/received
# columns, see conftest.py) side by side.
cat > "$SCRIPT_DIR/report.html" <<'HTML'
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>SFTP test report</title>
<style>
  body { font-family: sans-serif; margin: 0; }
  h2 { padding: 0.5em 1em; margin: 0; background: #f5f5f5; border-bottom: 1px solid #ddd; }
  iframe { width: 100%; height: 60vh; border: none; border-bottom: 2px solid #ccc; display: block; }
</style>
</head>
<body>
<h2>AAD RBAC tests</h2>
<iframe src="report_aad.html"></iframe>
<h2>SFTP tests</h2>
<iframe src="report_sftp.html"></iframe>
</body>
</html>
HTML

source "$REPO_ROOT/env-dev.sh"
source "$SCRIPT_DIR/env-test.sh"
source "$SCRIPT_DIR/.venv/bin/activate"
python3 "$SCRIPT_DIR/sweep_artifacts.py"

if [[ $AAD_EXIT -ne 0 || $SFTP_EXIT -ne 0 ]]; then
  echo "AAD tests exit: $AAD_EXIT  SFTP tests exit: $SFTP_EXIT" >&2
  exit 1
fi
