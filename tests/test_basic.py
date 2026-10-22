"""Basic smoke tests for SMHI Local."""
from pathlib import Path
import json


def test_manifest_version():
    manifest = Path("custom_components/smhi_local/manifest.json")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["domain"] == "smhi_local"
    assert data["config_flow"] is True
    assert "version" in data


def test_const_imports():
    from custom_components.smhi_local.const import DOMAIN, API_URL, SENSOR_TYPES

    assert DOMAIN == "smhi_local"
    assert "snow1g" in API_URL
    assert len(SENSOR_TYPES) > 5
