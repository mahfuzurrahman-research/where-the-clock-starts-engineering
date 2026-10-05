from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from event_stream.contracts import load_policy, timestamp, validate_inputs
from event_stream.generator import synthetic_tables
from event_stream.pipeline import run
from event_stream.replay import replay


@pytest.fixture
def tables():
    return synthetic_tables()


@pytest.fixture
def policy():
    return load_policy()


@pytest.fixture
def log(tables):
    return validate_inputs(tables[0], tables[1])


@pytest.fixture
def snapshot(log, policy):
    return replay(log, timestamp(policy["observed_at"]), policy["allowed_lateness_hours"])


@pytest.fixture(scope="session")
def completed_run(tmp_path_factory):
    destination = tmp_path_factory.mktemp("completed_stream") / "stream"
    run(destination)
    return destination
