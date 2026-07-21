import json

from starlette.testclient import TestClient

from lib.local_store import LocalStorage
from standalone.server import StandaloneServer


TOKEN = "a" * 48


def make_server(tmp_path):
    data_dir = tmp_path / "data"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text("ok", encoding="utf-8")
    storage = LocalStorage(data_dir)
    storage.ensure_initial_files()
    server = StandaloneServer(
        data_dir=data_dir,
        frontend_dir=frontend_dir,
        host="127.0.0.1",
        storage=storage,
        ingest_tokens={TOKEN: "evomining-texas"},
    )
    return server, storage


def race_payload():
    return {
        "version": 1,
        "vantage": "spoofed",
        "block_height": 900001,
        "prevhash": "00" * 32,
        "first_epoch": 1_700_000_000.0,
        "first_utc": "2023-11-14T22:13:20Z",
        "arrivals_offset_ms": {"ocean": 0.0, "local": 12.5},
        "nonempty_arrivals_offset_ms": {"ocean": 0.0, "local": 12.5},
        "empty_first_pools": [],
        "missed_pools": [],
    }


def test_ingest_requires_authentication(tmp_path):
    server, _ = make_server(tmp_path)
    response = TestClient(server.app).post("/api/ingest/races", json=race_payload())
    assert response.status_code == 401


def test_ingest_binds_vantage_to_token(tmp_path):
    server, storage = make_server(tmp_path)
    response = TestClient(server.app).post(
        "/api/ingest/races",
        json=race_payload(),
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 202
    race_file = storage.api_dir / "races" / "2023" / "11" / "14" / "900001-evomining-texas.json"
    assert json.loads(race_file.read_text())["vantage"] == "evomining-texas"


def test_ingest_heartbeat_updates_status(tmp_path):
    server, storage = make_server(tmp_path)
    response = TestClient(server.app).post(
        "/api/ingest/heartbeat",
        json={"connected_pools": 4, "eligible_pools": 3, "collector_version": "test"},
        headers={"X-API-Key": TOKEN},
    )
    assert response.status_code == 202
    status = json.loads((storage.api_dir / "status" / "vantages.json").read_text())
    assert status["vantages"]["evomining-texas"]["connected_pools"] == 4

