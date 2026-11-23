"""Basic smoke tests for SMHI Local."""
from pathlib import Path
import json


def test_manifest_version():
    manifest = Path("custom_components/smhi_local/manifest.json")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["domain"] == "smhi_local"
    assert data["config_flow"] is True
    assert data["version"] == "1.5.2"


def test_const_imports():
    from custom_components.smhi_local.const import (
        API_URL,
        CACHE_MAX_AGE_MINUTES,
        DATA_STATUS_SENSOR_TYPES,
        DOMAIN,
        SENSOR_TYPES,
    )

    assert DOMAIN == "smhi_local"
    assert "snow1g" in API_URL
    assert len(SENSOR_TYPES) > 5
    assert CACHE_MAX_AGE_MINUTES > 0
    assert DATA_STATUS_SENSOR_TYPES[0]["key"] == "data_status"
