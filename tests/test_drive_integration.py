"""Unit and integration tests for Google Drive & Cloud Drive integration."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from core.drive_adapter import DriveAdapter
from core.ui_server import app
from core.models import HumanAssetRequest
from core.asset_planner import AssetPlanner
from core.scheduler_engine import AgencyScheduler


@pytest.fixture
def workspace_temp(tmp_path):
    """Provides an isolated workspace directory with required structure."""
    assets_dir = tmp_path / "assets" / "user_submissions"
    assets_dir.mkdir(parents=True, exist_ok=True)
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    lifecycle_dir = tmp_path / "lifecycle" / "human_asset_requests"
    lifecycle_dir.mkdir(parents=True, exist_ok=True)
    approvals_dir = tmp_path / "approvals" / "signed"
    approvals_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_file_id_extraction():
    """Test extracting Google Drive file IDs across URL formats."""
    # Standard file URL
    u1 = "https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/view?usp=sharing"
    assert DriveAdapter.extract_file_id(u1) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    # Query param URL
    u2 = "https://drive.google.com/open?id=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    assert DriveAdapter.extract_file_id(u2) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    # Folder URL
    u3 = "https://drive.google.com/drive/folders/1w7jK9Z3xY_v4N2mP5q8rT1s0U_AbCdEf"
    assert DriveAdapter.extract_file_id(u3) == "1w7jK9Z3xY_v4N2mP5q8rT1s0U_AbCdEf"

    # Raw file ID
    raw = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    assert DriveAdapter.extract_file_id(raw) == raw

    # Invalid input
    assert DriveAdapter.extract_file_id("") is None
    assert DriveAdapter.extract_file_id("https://google.com") is None
    assert DriveAdapter.extract_file_id("abc") is None


def test_drive_configuration_persistence(workspace_temp):
    """Test reading and writing Drive configuration."""
    da = DriveAdapter(workspace_temp)
    cfg = da.get_config()
    assert cfg["enabled"] is True
    assert cfg["drive_type"] == "google_drive"

    # Update config
    updated = da.save_config({
        "folder_url": "https://drive.google.com/drive/folders/123456789012345678",
        "local_sync_path": str(workspace_temp / "local_drop"),
        "auto_sync_on_morning_run": True
    })
    assert updated["folder_url"] == "https://drive.google.com/drive/folders/123456789012345678"
    assert updated["local_sync_path"] == str(workspace_temp / "local_drop")

    # Re-instantiate to verify persistence on disk
    da2 = DriveAdapter(workspace_temp)
    cfg2 = da2.get_config()
    assert cfg2["folder_url"] == "https://drive.google.com/drive/folders/123456789012345678"
    assert cfg2["local_sync_path"] == str(workspace_temp / "local_drop")


def test_import_from_google_drive_mock(workspace_temp):
    """Test importing a file from Google Drive via mock HTTP download."""
    da = DriveAdapter(workspace_temp)
    fake_content = b"\x89PNG\r\n\x1a\nFakePngContentWorkbenchOscilloscopeTrace"

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_content
    mock_resp.headers = {
        "Content-Disposition": 'attachment; filename="oscilloscope_trace.png"',
        "Content-Type": "image/png"
    }
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = da.import_from_google_drive(
            url_or_id="https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/view",
            candidate_id="cand_usb_01",
            project="usb-display"
        )

    assert res["success"] is True
    assert res["candidate_id"] == "cand_usb_01"
    assert res["project"] == "usb-display"
    assert "oscilloscope_trace.png" in res["filename"]
    assert res["size_bytes"] == len(fake_content)

    # Verify file written to disk
    dest_file = workspace_temp / "assets" / "user_submissions" / res["filename"]
    assert dest_file.exists()
    assert dest_file.read_bytes() == fake_content


def test_local_drive_sync_and_auto_fulfillment(workspace_temp):
    """Test scanning a local synced drive folder and auto-fulfilling pending requests."""
    # Setup pending request for cand_3dprinter_01
    req = HumanAssetRequest(
        request_id="req_test_3dprinter_01",
        candidate_id="cand_3dprinter_01",
        target_platforms=["instagram", "linkedin"],
        requested_asset_title="TMC2209 Stepper Driver Scope Trace",
        specific_instructions="Empirical proof of current wave shaping",
        why_needed="Physical mechatronics evidence",
        recommended_shots=["Close up of motor coil current on oscilloscope"],
        status="PENDING",
        created_at="2026-09-11T00:00:00Z"
    )
    req_file = workspace_temp / "lifecycle" / "human_asset_requests" / f"{req.request_id}.json"
    with open(req_file, "w", encoding="utf-8") as f:
        json.dump(req.model_dump(), f, indent=2)

    assert req.status == "PENDING"

    # Setup local synced folder
    local_sync_dir = workspace_temp / "synced_cloud_drive"
    local_sync_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy photo with matching candidate name
    test_photo = local_sync_dir / "cand_3dprinter_01_tmc2209_trace.png"
    test_photo.write_bytes(b"\x89PNG\r\n\x1a\nRealHardwareStepperTraceData")

    da = DriveAdapter(workspace_temp)
    sync_res = da.sync_local_drive(str(local_sync_dir))

    assert sync_res["success"] is True
    assert sync_res["synced_count"] == 1
    assert sync_res["items"][0]["candidate_id"] == "cand_3dprinter_01"

    # Verify request was fulfilled
    with open(req_file, "r", encoding="utf-8") as f:
        fulfilled_req = HumanAssetRequest.model_validate(json.load(f))
    assert fulfilled_req.status == "FULFILLED"
    assert fulfilled_req.fulfilled_asset_path is not None
    assert (workspace_temp / fulfilled_req.fulfilled_asset_path).exists()

    # Second sync should deduplicate and return 0
    sync_res2 = da.sync_local_drive(str(local_sync_dir))
    assert sync_res2["synced_count"] == 0


def test_drive_api_endpoints(monkeypatch, workspace_temp):
    """Test FastAPI /api/drive/* endpoints."""
    monkeypatch.setattr("core.ui_server.get_workspace_root", lambda: workspace_temp)
    client = TestClient(app)

    # 1. GET /api/drive/status
    res = client.get("/api/drive/status")
    assert res.status_code == 200
    data = res.json()
    assert "enabled" in data
    assert "drive_type" in data

    # 2. POST /api/drive/configure (form)
    conf_res = client.post(
        "/api/drive/configure",
        data={
            "folder_url": "https://drive.google.com/drive/folders/123456789012345678",
            "local_sync_path": str(workspace_temp),
            "auto_sync_on_morning_run": "true",
            "enabled": "true"
        }
    )
    assert conf_res.status_code == 200
    cdata = conf_res.json()
    assert cdata["success"] is True
    assert cdata["config"]["folder_url"] == "https://drive.google.com/drive/folders/123456789012345678"

    # 3. POST /api/drive/sync
    sync_res = client.post("/api/drive/sync")
    assert sync_res.status_code == 200
    sdata = sync_res.json()
    assert sdata["success"] is True

    # 4. POST /api/drive/import-url (with mocked download)
    fake_bytes = b"MockGoogleDriveImageContent"
    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_bytes
    mock_resp.headers = {"Content-Type": "image/png"}
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        imp_res = client.post(
            "/api/drive/import-url",
            data={
                "url": "https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/view",
                "candidate_id": "cand_jarvis_01",
                "project": "JARVIS"
            }
        )
    assert imp_res.status_code == 200
    idata = imp_res.json()
    assert idata["success"] is True
    assert idata["candidate_id"] == "cand_jarvis_01"
    assert idata["project"] == "JARVIS"


def test_morning_intelligence_runs_drive_sync(workspace_temp):
    """Test that AgencyScheduler morning run triggers Drive sync."""
    da = DriveAdapter(workspace_temp)
    da.save_config({
        "enabled": True,
        "auto_sync_on_morning_run": True,
        "local_sync_path": str(workspace_temp)
    })

    scheduler = AgencyScheduler(workspace_temp)
    briefing = scheduler.run_morning_intelligence()

    assert "drive_sync" in briefing
    assert briefing["drive_sync"] is not None


def test_three_layer_architecture_and_status_distinctions(workspace_temp):
    """Test that DriveAssetSource coordinates all 3 adapters and reports exact status distinctions."""
    from core.drive_adapter import DriveAssetSource, LocalSyncAdapter, ShareLinkAdapter, GoogleDriveOAuthAdapter

    source = DriveAssetSource(workspace_temp)
    assert isinstance(source.local_sync, LocalSyncAdapter)
    assert isinstance(source.share_link, ShareLinkAdapter)
    assert isinstance(source.oauth, GoogleDriveOAuthAdapter)

    # Initial state: unconfigured OAuth and unconfigured local path
    status = source.get_status()
    assert status["oauth_status"] == "GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED"
    assert status["local_sync_status"] == "LOCAL_SYNC_NOT_CONFIGURED"
    assert status["share_link_status"] == "SHARE_LINK_IMPORT_AVAILABLE"
    # Prime requirement: Do NOT claim Drive is connected!
    assert status["overall_status_label"] == "SHARE LINK IMPORT AVAILABLE"

    # Configure local path only
    local_dir = workspace_temp / "my_local_sync"
    local_dir.mkdir()
    source.save_config({"local_sync_path": str(local_dir)})
    status2 = source.get_status()
    assert status2["local_sync_status"] == "LOCAL_SYNC_CONNECTED"
    assert status2["oauth_status"] == "GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED"
    # Reports LOCAL SYNC CONNECTED, still distinguishes OAuth as unconfigured
    assert status2["overall_status_label"] == "LOCAL SYNC CONNECTED"

    # Configure OAuth tokens
    source.oauth.set_tokens(
        access_token="mock_access_ya29_xyz",
        account_email="serhat@example.com",
        account_name="Serhat Builder"
    )
    status3 = source.get_status()
    assert status3["oauth_status"] == "GOOGLE_DRIVE_ACCOUNT_CONNECTED"
    assert status3["overall_status_label"] == "GOOGLE DRIVE ACCOUNT CONNECTED"
    assert status3["oauth"]["account_email"] == "serhat@example.com"


def test_google_drive_oauth_adapter_lifecycle(workspace_temp):
    """Test OAuth credentials configuration, token storage, and disconnection."""
    from core.drive_adapter import GoogleDriveOAuthAdapter

    oauth = GoogleDriveOAuthAdapter(workspace_temp)
    assert oauth.is_connected() is False
    assert oauth.get_status_label() == "GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED"

    # Save credentials
    creds = oauth.save_credentials({
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-client-secret-12345",
        "redirect_uri": "http://localhost:8765/api/drive/oauth/callback",
        "root_folder_id": "folder_root_123"
    })
    assert creds["client_id"] == "test-client-id.apps.googleusercontent.com"
    assert creds["client_secret"] == "test-client-secret-12345"

    # Authorization URL generation
    auth_url = oauth.get_authorization_url(state="custom_state_token")
    assert "https://accounts.google.com/o/oauth2/v2/auth" in auth_url
    assert "client_id=test-client-id.apps.googleusercontent.com" in auth_url
    assert "state=custom_state_token" in auth_url

    # Store tokens
    tok_res = oauth.set_tokens(
        access_token="ya29.test_valid_token",
        refresh_token="1//refresh_token_xyz",
        account_email="developer@serhat.engineer",
        account_name="Serhat"
    )
    assert tok_res["connected"] is True
    assert tok_res["status"] == "GOOGLE_DRIVE_ACCOUNT_CONNECTED"
    assert oauth.is_connected() is True

    # Disconnect
    oauth.disconnect()
    assert oauth.is_connected() is False
    assert oauth.get_status_label() == "GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED"


def test_google_drive_oauth_file_operations_and_import(workspace_temp):
    """Test listing, searching, and importing private files via GoogleDriveOAuthAdapter."""
    from core.drive_adapter import GoogleDriveOAuthAdapter

    oauth = GoogleDriveOAuthAdapter(workspace_temp)
    oauth.set_tokens(
        access_token="mock_valid_token",
        account_email="serhat@example.com",
        root_folder_id="root_folder_xyz"
    )

    # Mock list_files response from Google Drive REST API
    mock_list_payload = json.dumps({
        "files": [
            {
                "id": "drive_file_001",
                "name": "cad_frame_render.png",
                "mimeType": "image/png",
                "size": "1048576",
                "modifiedTime": "2026-09-11T12:00:00Z"
            },
            {
                "id": "drive_file_002",
                "name": "benchmark_data.csv",
                "mimeType": "text/csv",
                "size": "2048",
                "modifiedTime": "2026-09-11T11:00:00Z"
            }
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_list_payload
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        list_res = oauth.list_files()
        assert len(list_res["files"]) == 2
        assert list_res["files"][0]["name"] == "cad_frame_render.png"

        # Test search_files
        search_res = oauth.search_files(name_contains="cad")
        assert len(search_res["files"]) == 2

    # Mock download & import of drive_file_001
    file_bytes = b"\x89PNG\r\n\x1a\nCadRenderMockData3DPrinterFrame"
    mock_dl_resp = MagicMock()
    mock_dl_resp.read.return_value = file_bytes
    mock_dl_resp.headers = {
        "Content-Disposition": 'attachment; filename="cad_frame_render.png"',
        "Content-Type": "image/png"
    }
    mock_dl_resp.__enter__.return_value = mock_dl_resp

    # Also mock get_file_metadata
    mock_meta_payload = json.dumps({
        "id": "drive_file_001",
        "name": "cad_frame_render.png",
        "mimeType": "image/png",
        "size": str(len(file_bytes)),
        "modifiedTime": "2026-09-11T12:00:00Z"
    }).encode("utf-8")
    mock_meta_resp = MagicMock()
    mock_meta_resp.read.return_value = mock_meta_payload
    mock_meta_resp.__enter__.return_value = mock_meta_resp

    def mock_urlopen_router(req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "alt=media" in url:
            return mock_dl_resp
        return mock_meta_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen_router):
        import_res = oauth.import_file(
            file_id="drive_file_001",
            candidate_id="cand_3dprinter_02",
            project="3dprinter"
        )

    assert import_res["success"] is True
    assert import_res["file_id"] == "drive_file_001"
    assert import_res["candidate_id"] == "cand_3dprinter_02"
    assert import_res["project"] == "3dprinter"
    assert import_res["size_bytes"] == len(file_bytes)
    assert import_res["provenance"]["drive_name"] == "cad_frame_render.png"
    assert import_res["provenance"]["account_email"] == "serhat@example.com"

    # Verify asset file created on disk
    saved_file = workspace_temp / "assets" / "user_submissions" / import_res["filename"]
    assert saved_file.exists()
    assert saved_file.read_bytes() == file_bytes

    # Second import must deduplicate
    with patch("urllib.request.urlopen", side_effect=mock_urlopen_router):
        import_res2 = oauth.import_file(file_id="drive_file_001")
    assert import_res2["deduplicated"] is True


def test_drive_oauth_fastapi_endpoints(monkeypatch, workspace_temp):
    """Test all FastAPI /api/drive/oauth/* endpoints."""
    monkeypatch.setattr("core.ui_server.get_workspace_root", lambda: workspace_temp)
    client = TestClient(app)

    # 1. GET /api/drive/oauth/status (initial unconfigured)
    s_res = client.get("/api/drive/oauth/status")
    assert s_res.status_code == 200
    assert s_res.json()["status"] == "GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED"

    # 2. POST /api/drive/oauth/configure
    c_res = client.post(
        "/api/drive/oauth/configure",
        json={
            "client_id": "test_id_123",
            "client_secret": "test_sec_456",
            "redirect_uri": "http://localhost:8765/api/drive/oauth/callback",
            "root_folder_id": "root_999"
        }
    )
    assert c_res.status_code == 200
    assert c_res.json()["success"] is True

    # 3. GET /api/drive/oauth/auth-url
    a_res = client.get("/api/drive/oauth/auth-url")
    assert a_res.status_code == 200
    assert "https://accounts.google.com/o/oauth2/v2/auth" in a_res.json()["authorization_url"]

    # 4. POST /api/drive/oauth/set-tokens
    t_res = client.post(
        "/api/drive/oauth/set-tokens",
        json={
            "access_token": "ya29_mock_test_token",
            "account_email": "serhat@engineer.com",
            "account_name": "Serhat"
        }
    )
    assert t_res.status_code == 200
    assert t_res.json()["oauth"]["status"] == "GOOGLE_DRIVE_ACCOUNT_CONNECTED"

    # 5. GET /api/drive/oauth/files (with mock)
    mock_files_json = json.dumps({
        "files": [{"id": "fid_101", "name": "thermal_bench.jpg", "mimeType": "image/jpeg", "size": "4096"}]
    }).encode("utf-8")
    mock_f_resp = MagicMock()
    mock_f_resp.read.return_value = mock_files_json
    mock_f_resp.__enter__.return_value = mock_f_resp

    with patch("urllib.request.urlopen", return_value=mock_f_resp):
        f_res = client.get("/api/drive/oauth/files")
    assert f_res.status_code == 200
    fdata = f_res.json()
    assert fdata["success"] is True
    assert len(fdata["files"]) == 1
    assert fdata["files"][0]["name"] == "thermal_bench.jpg"

    # 6. POST /api/drive/oauth/disconnect
    d_res = client.post("/api/drive/oauth/disconnect")
    assert d_res.status_code == 200
    assert d_res.json()["oauth"]["status"] == "GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED"


def test_drive_browser_root_boundary_enforcement(workspace_temp):
    """Test that GoogleDriveOAuthAdapter strictly enforces root_folder_id boundary."""
    from core.drive_adapter import GoogleDriveOAuthAdapter

    oauth = GoogleDriveOAuthAdapter(workspace_temp)
    oauth.set_tokens(
        access_token="mock_token",
        root_folder_id="agency_root_123",
        root_folder_name="POSTASSEST"
    )

    # 1. Root folder itself is within root
    assert oauth.verify_within_root("agency_root_123") is True
    assert oauth.verify_within_root(None) is True

    # 2. Child folder having agency_root_123 in parents
    child_meta = {"id": "child_folder_456", "name": "hardware_tests", "parents": ["agency_root_123"]}
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(child_meta).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert oauth.verify_within_root("child_folder_456") is True

    # 3. Outside folder (e.g. parent of root or unconnected root)
    outside_meta = {"id": "outside_drive_999", "name": "Other Personal Drive", "parents": ["root"]}
    mock_resp_out = MagicMock()
    mock_resp_out.read.return_value = json.dumps(outside_meta).encode("utf-8")
    mock_resp_out.__enter__.return_value = mock_resp_out

    with patch("urllib.request.urlopen", return_value=mock_resp_out):
        assert oauth.verify_within_root("outside_drive_999") is False

        # Attempting browse_folder outside root raises PermissionError
        with pytest.raises(PermissionError) as exc_info:
            oauth.browse_folder("outside_drive_999")
        assert "outside the configured agency root folder" in str(exc_info.value)


def test_drive_browser_breadcrumbs_and_browsing(workspace_temp):
    """Test hierarchical breadcrumb calculation and folder browsing."""
    from core.drive_adapter import GoogleDriveOAuthAdapter

    oauth = GoogleDriveOAuthAdapter(workspace_temp)
    oauth.set_tokens(
        access_token="mock_token",
        root_folder_id="agency_root_123",
        root_folder_name="POSTASSEST"
    )

    # Breadcrumbs at root
    bc_root = oauth.get_breadcrumbs("agency_root_123")
    assert len(bc_root) == 1
    assert bc_root[0]["id"] == "agency_root_123"
    assert bc_root[0]["name"] == "POSTASSEST"

    # Breadcrumbs in nested child folder
    child_meta = {"id": "sub_usb_display", "name": "usb-display", "parents": ["agency_root_123"]}
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(child_meta).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        bc_child = oauth.get_breadcrumbs("sub_usb_display")
        assert len(bc_child) == 2
        assert bc_child[0]["name"] == "POSTASSEST"
        assert bc_child[1]["name"] == "usb-display"

    # Browse folder contents
    files_payload = json.dumps({
        "files": [
            {
                "id": "sub_folder_01",
                "name": "firmware",
                "mimeType": "application/vnd.google-apps.folder",
                "modifiedTime": "2026-09-11T12:00:00Z"
            },
            {
                "id": "file_photo_01",
                "name": "tmc2209_driver.jpg",
                "mimeType": "image/jpeg",
                "size": "524288",
                "modifiedTime": "2026-09-11T11:00:00Z",
                "thumbnailLink": "https://lh3.googleusercontent.com/test_thumb"
            }
        ]
    }).encode("utf-8")
    mock_files_resp = MagicMock()
    mock_files_resp.read.return_value = files_payload
    mock_files_resp.__enter__.return_value = mock_files_resp

    with patch("urllib.request.urlopen", return_value=mock_files_resp):
        browse_res = oauth.browse_folder("agency_root_123")
        assert browse_res["success"] is True
        assert browse_res["is_root"] is True
        assert browse_res["folder_count"] == 1
        assert browse_res["file_count"] == 1
        assert browse_res["items"][0]["isFolder"] is True
        assert browse_res["items"][1]["name"] == "tmc2209_driver.jpg"
        assert browse_res["items"][1]["hasThumbnail"] is True


def test_drive_browser_candidate_attachment_and_cascading(workspace_temp):
    """Test attaching a Drive file to a candidate and cascading fulfillment across platforms."""
    from core.drive_adapter import GoogleDriveOAuthAdapter
    from core.models import HumanAssetRequest
    from core.asset_planner import AssetPlanner

    oauth = GoogleDriveOAuthAdapter(workspace_temp)
    oauth.set_tokens(
        access_token="mock_token",
        root_folder_id="agency_root_123",
        root_folder_name="POSTASSEST"
    )

    # Create pending human asset request in workspace_temp
    req1 = HumanAssetRequest(
        request_id="req_usb_99_main",
        candidate_id="cand_usb_99",
        requested_asset_title="NVENC Latency Graph",
        specific_instructions="Provide screenshot of NVENC latency monitor",
        why_needed="Empirical latency evidence",
        recommended_shots=["0ms render latency frame"],
        status="PENDING",
        created_at="2026-09-11T00:00:00Z"
    )
    req_file1 = workspace_temp / "lifecycle" / "human_asset_requests" / f"{req1.request_id}.json"
    with open(req_file1, "w", encoding="utf-8") as f:
        json.dump(req1.model_dump(), f, indent=2)

    # Also create Instagram pending request for cand_usb_99 to test cascading
    req2 = HumanAssetRequest(
        request_id="req_usb_ig",
        candidate_id="cand_usb_99",
        requested_asset_title="NVENC Latency Graph IG",
        specific_instructions="Square crop of latency",
        why_needed="Instagram asset requirements",
        target_platforms=["instagram"],
        status="PENDING",
        created_at="2026-09-11T00:00:00Z"
    )
    req_file2 = workspace_temp / "lifecycle" / "human_asset_requests" / "req_usb_ig.json"
    with open(req_file2, "w", encoding="utf-8") as f:
        json.dump(req2.model_dump(), f, indent=2)

    # Mock metadata and download
    file_meta = {
        "id": "drive_img_123",
        "name": "nvenc_latency_graph.png",
        "mimeType": "image/png",
        "size": 1024
    }
    file_bytes = b"\x89PNG\r\n\x1a\nNVENCTestLatencyContentGraph"

    def mock_urlopen_handler(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        m = MagicMock()
        if "alt=media" in url:
            m.read.return_value = file_bytes
        else:
            m.read.return_value = json.dumps(file_meta).encode("utf-8")
        m.__enter__.return_value = m
        return m

    with patch("urllib.request.urlopen", side_effect=mock_urlopen_handler):
        res = oauth.attach_to_candidate(
            file_id="drive_img_123",
            candidate_id="cand_usb_99",
            request_id=req1.request_id,
            project="usb-display"
        )

        assert res["success"] is True
        assert res["candidate_id"] == "cand_usb_99"
        assert res["sha256"] is not None
        assert res["fulfilled_request_id"] == req1.request_id
        assert len(res["cascaded_requests"]) >= 1

        # Verify on disk that req1 is FULFILLED
        with open(workspace_temp / "lifecycle" / "human_asset_requests" / f"{req1.request_id}.json") as f:
            d1 = json.load(f)
            assert d1["status"] == "FULFILLED"
            assert d1["asset_sha256"] == res["sha256"]

        # Verify req2 cascaded to FULFILLED
        with open(req_file2) as f:
            d2 = json.load(f)
            assert d2["status"] == "FULFILLED"


def test_drive_browser_api_routes_and_security(workspace_temp):
    """Test the FastAPI UI routes for Google Drive browser."""
    from core.drive_adapter import GoogleDriveOAuthAdapter

    oauth = GoogleDriveOAuthAdapter(workspace_temp)
    oauth.set_tokens(
        access_token="mock_token",
        root_folder_id="agency_root_123",
        root_folder_name="POSTASSEST"
    )

    client = TestClient(app)

    # 1. GET /api/drive/oauth/browse (root)
    browse_payload = json.dumps({
        "files": [
            {"id": "f_1", "name": "hardware.log", "mimeType": "text/plain", "size": "100"}
        ]
    }).encode("utf-8")
    m_resp = MagicMock()
    m_resp.read.return_value = browse_payload
    m_resp.__enter__.return_value = m_resp

    with patch("urllib.request.urlopen", return_value=m_resp), \
         patch("core.ui_server.get_workspace_root", return_value=workspace_temp):
        res = client.get("/api/drive/oauth/browse")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["is_root"] is True
        assert len(data["items"]) == 1

        # 2. GET /api/drive/oauth/browse with outside folder -> 403 Forbidden
        outside_meta = {"id": "hacker_folder_666", "parents": ["root"]}
        m_resp_out = MagicMock()
        m_resp_out.read.return_value = json.dumps(outside_meta).encode("utf-8")
        m_resp_out.__enter__.return_value = m_resp_out

        with patch("urllib.request.urlopen", return_value=m_resp_out):
            res_bad = client.get("/api/drive/oauth/browse?folder_id=hacker_folder_666")
            assert res_bad.status_code == 403
            assert "outside the configured agency root folder" in res_bad.json()["detail"]


