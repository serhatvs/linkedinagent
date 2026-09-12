"""Tests for the interactive visual UI (Web FastAPI and native desktop GUI)."""

import io
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from core.ui_server import app
from core.models import HumanAssetRequest
from core.asset_planner import AssetPlanner


@pytest.fixture
def client():
    return TestClient(app)


def test_ui_html_endpoint(client):
    """Verify that GET / serves the complete single-page interactive UI."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Serhat — Autonomous Media Agency" in resp.text
    assert "Evidence-First Asset Requests" in resp.text
    assert "Asset Storage" in resp.text
    assert "Distribution Matrix" in resp.text
    assert "Killswitch" in resp.text


def test_ui_status_endpoint(client):
    """Verify that /api/status returns live agency pipeline and killswitch metrics."""
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "operational_status" in data
    assert "killswitch_mode" in data
    assert "pipeline_stages" in data
    assert "pending_assets_count" in data


def test_ui_asset_requests_listing_and_upload(client):
    """Verify listing requests and fulfilling a request via file upload."""
    ws = Path(__file__).resolve().parent.parent
    planner = AssetPlanner(ws)

    # Ensure at least one pending test request exists
    from core.models import Candidate, CandidateDecision, MVTSEvaluation
    dummy_cand = Candidate(
        candidate_id="cand_test_ui_upload",
        idea_id="idea_ui_test",
        pillar="pillar_low_level_systems_and_graphics",
        target_audience=["Developers"],
        angle="UI Test Angle",
        mvts_evaluation=MVTSEvaluation(grounding_score=3.0, technical_artifact_score=3.0, engineering_tradeoff_score=2.0, actionable_takeaway_score=1.5, total_score=9.5),
        decision=CandidateDecision.PROCEED_TO_DRAFT
    )
    req = planner.create_human_asset_request(
        candidate=dummy_cand,
        target_platform="instagram",
        title="UI Workbench Test Photo",
        instructions="Take a photo for UI test",
        why_needed="Testing UI upload",
        recommended_shots=["Top-down view"]
    )

    # List requests
    resp = client.get("/api/asset-requests")
    assert resp.status_code == 200
    reqs = resp.json()["requests"]
    assert any(r["request_id"] == req.request_id for r in reqs)

    # Upload mock image
    file_bytes = io.BytesIO(b"MOCK_IMAGE_FILE_DATA_FOR_UI_TEST")
    up_resp = client.post(
        f"/api/asset-requests/{req.request_id}/upload",
        files={"file": ("test_shot.png", file_bytes, "image/png")}
    )
    assert up_resp.status_code == 200
    res_data = up_resp.json()
    assert res_data["success"] is True
    assert res_data["status"] == "FULFILLED"
    assert "asset_sha256" in res_data
    assert len(res_data["asset_sha256"]) == 64


def test_ui_asset_storage_endpoints(client):
    """Verify /api/asset-storage lists assets and /api/asset-storage/upload accepts uploads."""
    resp = client.get("/api/asset-storage")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total_count" in data
    assert "total_size_bytes" in data
    assert isinstance(data["items"], list)

    # Test direct upload
    test_data = io.BytesIO(b"MOCK_STORAGE_DATA_FOR_TEST")
    up_resp = client.post(
        "/api/asset-storage/upload",
        files={"file": ("unit_test_trace.png", test_data, "image/png")},
        data={"candidate_id": "cand_test_storage", "project": "test-project"}
    )
    assert up_resp.status_code == 200
    res_data = up_resp.json()
    assert res_data["success"] is True
    assert "sha256" in res_data
    assert len(res_data["sha256"]) == 64

    # Verify item now listed in storage
    resp2 = client.get("/api/asset-storage")
    assert any(i["filename"] == res_data["filename"] for i in resp2.json()["items"])

    # Clean up uploaded test file
    ws = Path(__file__).resolve().parent.parent
    up_file = ws / "assets" / "user_submissions" / res_data["filename"]
    if up_file.exists():
        up_file.unlink()


def test_ui_distribution_matrix_endpoint(client):
    """Verify distribution matrix endpoint returns backlog candidates with channel breakdown."""
    resp = client.get("/api/distribution-matrix")
    assert resp.status_code == 200
    data = resp.json()
    assert "candidates" in data
    assert isinstance(data["candidates"], list)


def test_ui_killswitch_toggle(client):
    """Verify killswitch mode can be toggled via API."""
    resp = client.post("/api/killswitch", data={"mode": "AUTONOMY_PAUSED", "reason": "Test toggle"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "AUTONOMY_PAUSED"

    # Reset back to enabled
    resp2 = client.post("/api/killswitch", data={"mode": "AUTONOMY_ENABLED", "reason": "Test restored"})
    assert resp2.status_code == 200
    assert resp2.json()["mode"] == "AUTONOMY_ENABLED"


def test_pyside6_desktop_gui_initialization():
    """Verify PySide6 desktop GUI instantiates without error."""
    from PySide6.QtWidgets import QApplication
    from core.agency_gui import AgencyGUI

    app = QApplication.instance() or QApplication([])
    ws = Path(__file__).resolve().parent.parent
    gui = AgencyGUI(ws)
    assert gui.windowTitle() == "Serhat — Autonomous Personal Media Agency"
    assert gui.tabs.count() == 4
