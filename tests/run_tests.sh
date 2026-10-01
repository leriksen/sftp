#!/usr/bin/env bash
# Single suite now (SFTP local users); kept as the stable entry point.
exec bash "$(cd "$(dirname "$0")" && pwd)/run_sftp_tests.sh" "$@"
