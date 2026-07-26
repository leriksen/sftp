#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPORT="$SCRIPT_DIR/report.md"

bash "$SCRIPT_DIR/run_aad_tests.sh" "$@" &
AAD_PID=$!

bash "$SCRIPT_DIR/run_sftp_tests.sh" "$@" &
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

if [[ $AAD_EXIT -ne 0 || $SFTP_EXIT -ne 0 ]]; then
  echo "AAD tests exit: $AAD_EXIT  SFTP tests exit: $SFTP_EXIT" >&2
  exit 1
fi
