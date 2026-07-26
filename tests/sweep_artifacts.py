#!/usr/bin/env python3
"""Standalone safety-net sweep -- deletes exactly the artifacts the test
harness itself logged as created (tests/.artifacts_created.jsonl) and never
got around to removing. Never touches pre-existing data in the storage
account. Only safe to run once all pytest sessions touching this storage
account have finished; see conftest.sweep_leftover_artifacts for why this
isn't a pytest fixture.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conftest import _client, sweep_leftover_artifacts

if __name__ == "__main__":
    admin_client = _client(os.environ["ARM_CLIENT_ID"], os.environ["ARM_CLIENT_SECRET"])
    sweep_leftover_artifacts(admin_client)
