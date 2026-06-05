"""Integration tests — require a running MongoDB on localhost:27017."""
from __future__ import annotations
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def mongo_client():
    from db.client import MongoDBClient
    client = MongoDBClient("mongodb://localhost:27017")
    yield client
    # Clean up test data
    client.db.drop_collection("_test_col")
    client.close()


def test_ping(mongo_client):
    result = mongo_client._client.admin.command("ping")
    assert result.get("ok") == 1.0


def test_database_name(mongo_client):
    assert mongo_client.db.name == "hf_ai_engine"


def test_indexes_created(mongo_client):
    index_info = mongo_client.runs.index_information()
    index_keys = [list(v["key"]) for v in index_info.values()]
    assert any("run_id" in str(k) for k in index_keys)


def test_insert_and_read_run(mongo_client):
    from datetime import datetime, timezone
    doc = {
        "run_id": "test_run_phase1",
        "run_type": "analysis",
        "tickers": ["AAPL"],
        "status": "success",
        "started_at": datetime.now(tz=timezone.utc),
    }
    mongo_client.runs.insert_one(doc)
    found = mongo_client.runs.find_one({"run_id": "test_run_phase1"})
    assert found is not None
    assert found["tickers"] == ["AAPL"]
    mongo_client.runs.delete_one({"run_id": "test_run_phase1"})


def test_wrong_uri_raises():
    from db.client import MongoDBClient
    with pytest.raises(RuntimeError, match="Cannot connect"):
        MongoDBClient("mongodb://localhost:19999")
