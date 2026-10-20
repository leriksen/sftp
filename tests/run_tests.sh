#!/usr/bin/env bash
# Runs both suites, one after the other, and fails if either fails:
#   account "01" -- SFTP local users      (tests/run_sftp_tests.sh)
#   account "02" -- Entra ID SFTP         (tests/entra/run_entra_tests.sh)
# Separate pytest sessions because each suite's conftest.py binds to its own
# account at import time.
TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"

EXIT=0
bash "$TESTS_DIR/run_sftp_tests.sh" "$@" || EXIT=$?
bash "$TESTS_DIR/entra/run_entra_tests.sh" "$@" || EXIT=$?
exit "$EXIT"
