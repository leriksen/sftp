#!/usr/bin/env python3
"""Standalone safety-net sweep for the Entra suite -- deletes exactly the
artifacts this harness logged as created (tests/entra/.artifacts_created.jsonl)
and never got around to removing. Never touches pre-existing data.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conftest import _client, sweep_leftover_artifacts

if __name__ == "__main__":
    admin_client = _client(os.environ["ARM_CLIENT_ID"], os.environ["ARM_CLIENT_SECRET"])
    sweep_leftover_artifacts(admin_client)
