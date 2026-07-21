import json

from collector.str_race import load_pool_configs


def test_legacy_pool_defaults_to_sv1(tmp_path):
    path = tmp_path / "pools.json"
    path.write_text(json.dumps([{"name": "legacy", "host": "localhost", "port": 3333}]))
    config = load_pool_configs(str(path))
    assert config[0].protocol == "sv1"
    assert config[0].cohort == "public-reference"


def test_central_config_loads_sv2_metadata(tmp_path):
    path = tmp_path / "pools.json"
    path.write_text(json.dumps({"pools": [{
        "name": "native_sv2",
        "host": "localhost",
        "port": 34265,
        "protocol": "sv2",
        "authority_pubkey": "public-key",
        "cohort": "gridpool-local",
        "groups": ["study"]
    }]}))
    config = load_pool_configs(None, str(path), "study")
    assert config[0].protocol == "sv2"
    assert config[0].authority_pubkey == "public-key"
    assert config[0].cohort == "gridpool-local"

