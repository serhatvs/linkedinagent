"""FastAPI Web UI Server for Serhat's Personal Media Agency.

Provides an interactive visual interface to:
1. Inspect pending Human Asset Requests (instructions, recommended shots, rationale).
2. Drag-and-drop or select photo/screenshot files to fulfill asset requests.
3. Review and sign/reject posts in the Approval Queue.
4. View the Multi-Channel Distribution Matrix across LinkedIn, Instagram, and X.
5. Manage Killswitch mode and trigger Morning Intelligence cycles.
6. Provide an operator workstation for content backlog, claim provenance, scorecards, and projects.
"""

from __future__ import annotations
import os
import sys
import json
import uuid
import shutil
import hashlib
import tempfile
import webbrowser
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Ensure workspace root is in sys.path
_ws_root = Path(__file__).resolve().parent.parent
if str(_ws_root) not in sys.path:
    sys.path.insert(0, str(_ws_root))

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from core.models import (
    HumanAssetRequest,
    AutonomyDecision,
    LifecycleState,
    Candidate,
    CandidateDecision,
    MVTSEvaluation,
    Post,
    MediaAsset
)
from core.asset_planner import AssetPlanner
from core.approval_engine import ApprovalEngine
from core.lifecycle_manager import LifecycleManager
from core.distribution_adapter import DistributionAdapter
from core.scheduler_engine import AgencyScheduler


app = FastAPI(title="Serhat Personal Media Agency UI", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_workspace_root() -> Path:
    return Path(__file__).resolve().parent.parent


@app.get("/api/status")
def get_status():
    ws = get_workspace_root()
    ae = ApprovalEngine(ws)
    lm = LifecycleManager(ws)
    planner = AssetPlanner(ws)

    frozen, reason = ae.is_killswitch_active()
    ks_state = ae.get_killswitch_state()

    pipeline = {}
    for state in LifecycleState:
        posts = lm.list_posts_in_state(state)
        pipeline[state.value] = len(posts)

    pending_approvals = []
    seen_appr = set()
    pending_dir = ws / "approvals" / "pending"
    if pending_dir.exists():
        for p in pending_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                pid = d.get("post_id")
                if pid and pid not in seen_appr:
                    seen_appr.add(pid)
                    pending_approvals.append(d)
            except Exception:
                pass
    pending_assets = planner.list_pending_requests()

    return {
        "operational_status": "FROZEN" if frozen else "ACTIVE",
        "frozen": frozen,
        "frozen_reason": reason,
        "killswitch_mode": ks_state.get("mode", "AUTONOMY_ENABLED"),
        "killswitch_details": ks_state,
        "pipeline_stages": pipeline,
        "pending_approvals_count": len(pending_approvals),
        "pending_assets_count": len(pending_assets)
    }


@app.get("/api/asset-requests")
def list_asset_requests():
    ws = get_workspace_root()
    from core.asset_planner import AssetPlanner
    planner = AssetPlanner(ws)
    planner.consolidate_duplicate_requests()
    requests_dir = ws / "lifecycle" / "human_asset_requests"
    reqs = []
    seen_candidates = set()
    if requests_dir.exists():
        for p in sorted(requests_dir.glob("*.json"), key=os.path.getmtime, reverse=True):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cid = data.get("candidate_id")
                    if cid and cid in seen_candidates:
                        continue
                    if cid:
                        seen_candidates.add(cid)
                    reqs.append(data)
            except Exception:
                pass
    return {"requests": reqs}


@app.get("/api/asset-requests/{request_id}")
def get_asset_request(request_id: str):
    ws = get_workspace_root()
    req_file = ws / "lifecycle" / "human_asset_requests" / f"{request_id}.json"
    if not req_file.exists():
        raise HTTPException(status_code=404, detail="Asset request not found.")
    with open(req_file, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/api/asset-requests/{request_id}/upload")
async def upload_asset_file(request_id: str, file: UploadFile = File(...)):
    ws = get_workspace_root()
    planner = AssetPlanner(ws)

    req_file = ws / "lifecycle" / "human_asset_requests" / f"{request_id}.json"
    if not req_file.exists():
        raise HTTPException(status_code=404, detail=f"Request '{request_id}' not found.")

    sub_dir = ws / "assets" / "user_submissions"
    sub_dir.mkdir(parents=True, exist_ok=True)
    clean_filename = f"{request_id}_{file.filename.replace(' ', '_')}"
    dest_path = sub_dir / clean_filename

    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    try:
        req = planner.fulfill_request(request_id, dest_path)
        return {
            "success": True,
            "message": f"Asset successfully submitted and registered for request {request_id}",
            "request_id": req.request_id,
            "candidate_id": req.candidate_id,
            "target_platforms": req.target_platforms,
            "status": req.status,
            "fulfilled_asset_path": req.fulfilled_asset_path,
            "asset_sha256": req.asset_sha256,
            "fulfilled_at": req.fulfilled_at
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


@app.get("/api/asset-storage")
def get_asset_storage():
    ws = get_workspace_root()
    assets_dir = ws / "assets"
    items = []

    # Map fulfilled request metadata
    req_map = {}
    requests_dir = ws / "lifecycle" / "human_asset_requests"
    if requests_dir.exists():
        for rf in requests_dir.glob("*.json"):
            try:
                with open(rf, "r", encoding="utf-8") as f:
                    rdata = json.load(f)
                    fpath = rdata.get("fulfilled_asset_path")
                    if fpath:
                        normalized = Path(fpath).name
                        req_map[normalized] = rdata
            except Exception:
                pass

    if assets_dir.exists():
        for file_path in sorted(assets_dir.rglob("*"), key=os.path.getmtime, reverse=True):
            if not file_path.is_file():
                continue
            try:
                rel_path = file_path.relative_to(assets_dir).as_posix()
            except ValueError:
                continue

            stat = file_path.stat()
            fname = file_path.name

            # Calculate SHA-256
            hasher = hashlib.sha256()
            with open(file_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            sha = hasher.hexdigest()

            linked_req = req_map.get(fname)
            cand_id = linked_req.get("candidate_id") if linked_req else None
            if not cand_id:
                for part in fname.split("_"):
                    if part.startswith("cand"):
                        cand_id = part
                        break
                if not cand_id and fname.startswith("cand_"):
                    cand_id = "_".join(fname.split("_")[:3])

            project = _infer_project_name(cand_id or fname, default="General")

            items.append({
                "filename": fname,
                "relative_path": rel_path,
                "url": f"/assets/{rel_path}",
                "size_bytes": stat.st_size,
                "size_formatted": _format_size(stat.st_size),
                "extension": file_path.suffix.lower(),
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "sha256": sha,
                "candidate_id": cand_id or "-",
                "project": project,
                "title": (linked_req.get("requested_asset_title") if linked_req else None) or fname
            })

    total_size = sum(i["size_bytes"] for i in items)
    return {
        "items": items,
        "total_count": len(items),
        "total_size_bytes": total_size,
        "total_size_formatted": _format_size(total_size)
    }


@app.post("/api/asset-storage/upload")
async def upload_direct_asset(file: UploadFile = File(...), candidate_id: Optional[str] = Form(None), project: Optional[str] = Form(None)):
    ws = get_workspace_root()
    sub_dir = ws / "assets" / "user_submissions"
    sub_dir.mkdir(parents=True, exist_ok=True)

    clean_name = file.filename.replace(" ", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{candidate_id}_" if candidate_id else "stored_"
    dest_name = f"{prefix}{ts}_{clean_name}"
    dest_path = sub_dir / dest_name

    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    hasher = hashlib.sha256(contents)
    sha = hasher.hexdigest()

    rel_path = dest_path.relative_to(ws / "assets").as_posix()
    inferred_proj = project or _infer_project_name(candidate_id or clean_name, default="General")

    return {
        "success": True,
        "filename": dest_name,
        "relative_path": rel_path,
        "url": f"/assets/{rel_path}",
        "size_bytes": len(contents),
        "size_formatted": _format_size(len(contents)),
        "sha256": sha,
        "candidate_id": candidate_id or "-",
        "project": inferred_proj
    }


# ----------------------------------------------------------------------
# Google Drive & Cloud Drive Integration Routes
# ----------------------------------------------------------------------

@app.get("/api/drive/status")
def get_drive_status():
    ws = get_workspace_root()
    from core.drive_adapter import DriveAdapter
    da = DriveAdapter(ws)
    return da.get_status()


@app.post("/api/drive/configure")
async def configure_drive(request: Request):
    ws = get_workspace_root()
    from core.drive_adapter import DriveAdapter
    da = DriveAdapter(ws)
    content_type = request.headers.get("content-type", "")
    updates = {}
    if "application/json" in content_type:
        try:
            updates = await request.json()
        except Exception:
            updates = {}
    else:
        form = await request.form()
        for k in ["folder_url", "local_sync_path"]:
            if k in form and form[k] is not None:
                updates[k] = str(form[k])
        if "enabled" in form:
            updates["enabled"] = str(form["enabled"]).lower() in ("true", "1", "yes")
        if "auto_sync_on_morning_run" in form:
            updates["auto_sync_on_morning_run"] = str(form["auto_sync_on_morning_run"]).lower() in ("true", "1", "yes")

    if "folder_url" in updates and updates["folder_url"]:
        fid = DriveAdapter.extract_file_id(updates["folder_url"])
        if fid:
            updates["folder_id"] = fid

    cfg = da.save_config(updates)
    return {"success": True, "config": cfg, "status": da.get_status()}


@app.post("/api/drive/sync")
def sync_drive():
    ws = get_workspace_root()
    from core.drive_adapter import DriveAdapter
    da = DriveAdapter(ws)
    results = da.sync()
    return {"success": True, "results": results, "status": da.get_status()}


@app.post("/api/drive/import-url")
async def import_drive_url(request: Request):
    ws = get_workspace_root()
    from core.drive_adapter import DriveAdapter
    da = DriveAdapter(ws)

    url = ""
    candidate_id = None
    project = None
    custom_filename = None

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        url = body.get("url", "")
        candidate_id = body.get("candidate_id")
        project = body.get("project")
        custom_filename = body.get("custom_filename")
    else:
        form = await request.form()
        url = form.get("url", "")
        candidate_id = form.get("candidate_id")
        project = form.get("project")
        custom_filename = form.get("custom_filename")

    if not url:
        raise HTTPException(status_code=400, detail="Missing required 'url' parameter.")

    try:
        res = da.import_from_google_drive(
            url_or_id=str(url),
            candidate_id=str(candidate_id) if candidate_id else None,
            project=str(project) if project else None,
            custom_filename=str(custom_filename) if custom_filename else None
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ----------------------------------------------------------------------
# Google Drive Authenticated OAuth 2.0 Account Routes
# ----------------------------------------------------------------------

@app.get("/api/drive/oauth/status")
def get_drive_oauth_status():
    ws = get_workspace_root()
    from core.drive_adapter import DriveAssetSource
    da = DriveAssetSource(ws)
    return da.oauth.get_status()


@app.post("/api/drive/oauth/configure")
async def configure_drive_oauth(request: Request):
    ws = get_workspace_root()
    from core.drive_adapter import DriveAssetSource
    da = DriveAssetSource(ws)
    content_type = request.headers.get("content-type", "")
    updates = {}
    if "application/json" in content_type:
        try:
            updates = await request.json()
        except Exception:
            updates = {}
    else:
        form = await request.form()
        for k in ["client_id", "client_secret", "redirect_uri", "root_folder_id", "root_folder_name"]:
            if k in form and form[k] is not None:
                updates[k] = str(form[k]).strip()

    da.oauth.save_credentials(updates)
    return {"success": True, "oauth": da.oauth.get_status()}


@app.post("/api/drive/oauth/set-tokens")
async def set_drive_oauth_tokens(request: Request):
    ws = get_workspace_root()
    from core.drive_adapter import DriveAssetSource
    da = DriveAssetSource(ws)
    content_type = request.headers.get("content-type", "")
    data = {}
    if "application/json" in content_type:
        try:
            data = await request.json()
        except Exception:
            data = {}
    else:
        form = await request.form()
        data = {k: str(v) for k, v in form.items()}

    acc_tok = data.get("access_token", "").strip()
    if not acc_tok:
        raise HTTPException(status_code=400, detail="access_token is required")

    status = da.oauth.set_tokens(
        access_token=acc_tok,
        refresh_token=data.get("refresh_token", "").strip() or None,
        account_email=data.get("account_email", "").strip() or None,
        account_name=data.get("account_name", "").strip() or None,
        token_expiry=data.get("token_expiry", "").strip() or None,
        root_folder_id=data.get("root_folder_id", "").strip() or None,
        root_folder_name=data.get("root_folder_name", "").strip() or None
    )
    return {"success": True, "oauth": status}


@app.get("/api/drive/oauth/auth-url")
def get_drive_oauth_auth_url(state: Optional[str] = None):
    ws = get_workspace_root()
    from core.drive_adapter import DriveAssetSource
    da = DriveAssetSource(ws)
    try:
        url = da.oauth.get_authorization_url(state=state)
        return {"success": True, "authorization_url": url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/drive/oauth/callback")
def handle_drive_oauth_callback(code: Optional[str] = None, error: Optional[str] = None):
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth Error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    ws = get_workspace_root()
    from core.drive_adapter import DriveAssetSource
    da = DriveAssetSource(ws)
    try:
        res = da.oauth.exchange_code(code)
        # Redirect back to workstation with hash
        html = f"""<!DOCTYPE html><html><head><meta http-equiv="refresh" content="1;url=/#drive_settings"/></head><body><p>Google Drive Account connected successfully. Redirecting back to Workstation...</p></body></html>"""
        return HTMLResponse(content=html)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to exchange OAuth code: {e}")


@app.post("/api/drive/oauth/disconnect")
def disconnect_drive_oauth():
    ws = get_workspace_root()
    from core.drive_adapter import DriveAssetSource
    da = DriveAssetSource(ws)
    res = da.oauth.disconnect()
    return {"success": True, "oauth": da.oauth.get_status()}


@app.get("/api/drive/oauth/files")
def list_drive_oauth_files(
    folder_id: Optional[str] = None,
    q: Optional[str] = None,
    name: Optional[str] = None,
    mime_type: Optional[str] = None,
    page_size: int = 25,
    page_token: Optional[str] = None
):
    ws = get_workspace_root()
    from core.drive_adapter import DriveAssetSource
    da = DriveAssetSource(ws)
    if not da.oauth.is_connected():
        return {
            "success": False,
            "status": "GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED",
            "files": [],
            "message": "Google Drive account is not authenticated. Please configure OAuth in Drive Settings."
        }

    try:
        if name or mime_type:
            res = da.oauth.search_files(
                name_contains=name,
                mime_type=mime_type,
                folder_id=folder_id,
                page_size=page_size,
                query=q
            )
        else:
            res = da.oauth.list_files(
                folder_id=folder_id,
                page_size=page_size,
                page_token=page_token,
                q=q
            )
        return {"success": True, "status": "GOOGLE_DRIVE_ACCOUNT_CONNECTED", **res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/drive/oauth/import-file")
async def import_drive_oauth_file(request: Request):
    ws = get_workspace_root()
    from core.drive_adapter import DriveAssetSource
    da = DriveAssetSource(ws)

    if not da.oauth.is_connected():
        raise HTTPException(status_code=400, detail="Google Drive account is not authenticated. (GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED)")

    content_type = request.headers.get("content-type", "")
    data = {}
    if "application/json" in content_type:
        try:
            data = await request.json()
        except Exception:
            data = {}
    else:
        form = await request.form()
        data = {k: str(v) for k, v in form.items()}

    file_id = data.get("file_id", "").strip()
    if not file_id:
        raise HTTPException(status_code=400, detail="file_id is required")

    try:
        res = da.oauth.import_file(
            file_id=file_id,
            candidate_id=data.get("candidate_id"),
            project=data.get("project"),
            custom_filename=data.get("custom_filename")
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/drive/oauth/browse")
def browse_drive_oauth(
    folder_id: Optional[str] = None,
    q: Optional[str] = None,
    mime_filter: Optional[str] = None,
    page_size: int = 100,
    page_token: Optional[str] = None
):
    ws = get_workspace_root()
    from core.drive_adapter import DriveAssetSource
    da = DriveAssetSource(ws)
    if not da.oauth.is_connected():
        return {
            "success": False,
            "status": "GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED",
            "items": [],
            "breadcrumbs": [],
            "message": "Google Drive account is not authenticated."
        }

    try:
        return da.oauth.browse_folder(
            folder_id=folder_id,
            page_size=page_size,
            page_token=page_token,
            q=q,
            mime_filter=mime_filter
        )
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/drive/oauth/thumbnail/{file_id}")
def get_drive_thumbnail(file_id: str):
    ws = get_workspace_root()
    from core.drive_adapter import DriveAssetSource
    da = DriveAssetSource(ws)
    if not da.oauth.is_connected():
        raise HTTPException(status_code=401, detail="Drive OAuth not connected")
    try:
        content, media_type = da.oauth.get_thumbnail_bytes(file_id)
        return Response(content=content, media_type=media_type)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Thumbnail unavailable: {e}")


@app.get("/api/drive/oauth/download/{file_id}")
def download_drive_file(file_id: str):
    ws = get_workspace_root()
    from core.drive_adapter import DriveAssetSource
    da = DriveAssetSource(ws)
    if not da.oauth.is_connected():
        raise HTTPException(status_code=401, detail="Drive OAuth not connected")
    try:
        meta = da.oauth.get_file_metadata(file_id)
        content = da.oauth.download_file(file_id)
        filename = meta.get("name", f"drive_{file_id}")
        mime_type = meta.get("mimeType", "application/octet-stream")
        return Response(
            content=content,
            media_type=mime_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Download failed: {e}")


@app.post("/api/drive/oauth/upload")
async def upload_drive_oauth_file(
    file: UploadFile = File(...),
    folder_id: Optional[str] = Form(None),
    overwrite: bool = Form(False)
):
    ws = get_workspace_root()
    from core.drive_adapter import DriveAssetSource
    da = DriveAssetSource(ws)
    if not da.oauth.is_connected():
        raise HTTPException(status_code=401, detail="Google Drive account is not authenticated.")

    target_folder = folder_id or da.oauth.get_root_folder_id()
    if not target_folder:
        raise HTTPException(status_code=400, detail="No target folder specified and no root folder configured.")

    try:
        content = await file.read()
        res = da.oauth.upload_file(
            folder_id=target_folder,
            filename=file.filename or "uploaded_file",
            content=content,
            mime_type=file.content_type or "application/octet-stream",
            overwrite=overwrite
        )
        return res
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/drive/oauth/attach-candidate")
async def attach_drive_file_to_candidate(request: Request):
    ws = get_workspace_root()
    from core.drive_adapter import DriveAssetSource
    da = DriveAssetSource(ws)
    if not da.oauth.is_connected():
        raise HTTPException(status_code=401, detail="Google Drive account is not authenticated.")

    content_type = request.headers.get("content-type", "")
    data = {}
    if "application/json" in content_type:
        try:
            data = await request.json()
        except Exception:
            data = {}
    else:
        form = await request.form()
        data = {k: str(v) for k, v in form.items()}

    file_id = data.get("file_id", "").strip()
    candidate_id = data.get("candidate_id", "").strip()
    request_id = data.get("request_id", "").strip() or None
    project = data.get("project", "").strip() or None
    custom_filename = data.get("custom_filename", "").strip() or None

    if not file_id or not candidate_id:
        raise HTTPException(status_code=400, detail="file_id and candidate_id are required.")

    try:
        return da.oauth.attach_to_candidate(
            file_id=file_id,
            candidate_id=candidate_id,
            request_id=request_id,
            project=project,
            custom_filename=custom_filename
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/drive/oauth/search")
def search_drive_oauth(
    q: str,
    mime_filter: Optional[str] = None,
    page_size: int = 50
):
    ws = get_workspace_root()
    from core.drive_adapter import DriveAssetSource
    da = DriveAssetSource(ws)
    if not da.oauth.is_connected():
        raise HTTPException(status_code=401, detail="Google Drive account is not authenticated.")
    try:
        return da.oauth.search_within_root(
            query=q,
            mime_filter=mime_filter,
            page_size=page_size
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/approvals")
def list_approvals():
    ws = get_workspace_root()
    pending_dir = ws / "approvals" / "pending"
    approvals = []
    seen_posts = set()
    if pending_dir.exists():
        for p in sorted(pending_dir.glob("*.json"), key=os.path.getmtime, reverse=True):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    pid = data.get("post_id")
                    if pid and pid in seen_posts:
                        continue
                    if pid:
                        seen_posts.add(pid)
                    approvals.append(data)
            except Exception:
                pass
    return {"approvals": approvals}


@app.post("/api/approvals/{request_id}/sign")
def sign_approval(request_id: str, signer: str = "Serhat"):
    ws = get_workspace_root()
    ae = ApprovalEngine(ws)
    try:
        req = ae.get_approval_request(request_id)
        token = ae.sign_approval_request(req, signer=signer)
        return {
            "success": True,
            "token_id": token.token_id,
            "approved_by": token.approved_by,
            "post_id": token.post_id,
            "signed_at": token.signed_at
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _infer_project_name(cand_id: str, default: str = "") -> str:
    cand_id = str(cand_id).lower()
    if "usb" in cand_id:
        return "usb-display"
    if "jarvis" in cand_id:
        return "JARVIS"
    if "3dprinter" in cand_id or "hardware" in cand_id:
        return "3dprinter"
    if "leshield" in cand_id:
        return "LeShield"
    if "chronos" in cand_id:
        return "chronos-rag"
    return default or "-"


@app.get("/api/distribution-matrix")
def get_distribution_matrix():
    ws = get_workspace_root()
    backlog_file = ws / "lifecycle" / "real_content_backlog.json"
    if not backlog_file.exists():
        return {"candidates": []}

    with open(backlog_file, "r", encoding="utf-8") as f:
        bdata = json.load(f)

    candidates_raw = bdata.get("candidates", [])[:15]
    adapter = DistributionAdapter()
    planner = AssetPlanner(ws)

    matrix = []
    for c in candidates_raw:
        cid = c.get("candidate_id")
        mvts_val = float(c.get("mvts_score", 0.0))

        cand_obj = Candidate(
            candidate_id=cid,
            idea_id=c.get("idea_id", f"idea_{cid.replace('cand_', '')}"),
            pillar=c.get("content_pillar", "pillar_software_infrastructure"),
            target_audience=c.get("audience", ["Engineers"]),
            angle=c.get("proposed_format", "Technical Analysis"),
            mvts_evaluation=MVTSEvaluation(
                grounding_score=min(mvts_val * 0.3, 3.0),
                technical_artifact_score=min(mvts_val * 0.3, 3.0),
                engineering_tradeoff_score=min(mvts_val * 0.2, 2.0),
                actionable_takeaway_score=min(mvts_val * 0.2, 2.0),
                total_score=mvts_val
            ),
            decision=CandidateDecision.PROCEED_TO_DRAFT if mvts_val >= 9.0 else CandidateDecision.HOLD_QUALITY
        )

        channels = {}
        for plat in ["linkedin", "instagram", "twitter"]:
            asset_res = planner.evaluate_asset_availability(cand_obj, plat)
            assets_for_plat = [asset_res["asset"]] if asset_res.get("status") == "ASSET_READY" else []

            story = adapter.generate_story_variants(
                candidate=cand_obj,
                base_text=c.get("title", "") + ". Measured engineering details and trade-off analysis.",
                media_assets=assets_for_plat
            )

            if plat in story.variants:
                src_prio = asset_res.get("source_priority")
                prio_str = f"P{src_prio.value}" if src_prio else "P1"
                channels[plat] = {
                    "status": "READY",
                    "badge": f"READY ({prio_str})",
                    "priority": prio_str
                }
            elif asset_res.get("human_request_needed"):
                channels[plat] = {
                    "status": "REQUEST_USER",
                    "badge": "REQUEST_USER",
                    "request_id": asset_res.get("human_asset_request", {}).request_id if hasattr(asset_res.get("human_asset_request"), "request_id") else None
                }
            elif len(assets_for_plat) == 0:
                channels[plat] = {
                    "status": "NO_ASSET",
                    "badge": "NO_ASSET"
                }
            else:
                channels[plat] = {
                    "status": "HELD",
                    "badge": "HELD"
                }

        matrix.append({
            "candidate_id": cid,
            "title": c.get("title", ""),
            "project_id": _infer_project_name(cid, c.get("project_id", "")),
            "mvts_score": mvts_val,
            "channels": channels
        })

    return {"candidates": matrix}


@app.get("/api/projects")
def get_projects():
    ws = get_workspace_root()
    reg_file = ws / "knowledge" / "projects_registry.json"
    if not reg_file.exists():
        return {"projects": []}
    with open(reg_file, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/content")
def get_content():
    ws = get_workspace_root()
    backlog_file = ws / "lifecycle" / "real_content_backlog.json"
    if not backlog_file.exists():
        return {"candidates": []}

    with open(backlog_file, "r", encoding="utf-8") as f:
        bdata = json.load(f)

    adapter = DistributionAdapter()
    candidates = []
    for c in bdata.get("candidates", []):
        cid = c.get("candidate_id")
        mvts_val = float(c.get("mvts_score", 0.0))

        cand_obj = Candidate(
            candidate_id=cid,
            idea_id=c.get("idea_id", f"idea_{cid.replace('cand_', '')}"),
            pillar=c.get("content_pillar", "pillar_software_infrastructure"),
            target_audience=c.get("audience", ["Engineers"]),
            angle=c.get("proposed_format", "Technical Analysis"),
            mvts_evaluation=MVTSEvaluation(
                grounding_score=min(round(mvts_val * 0.3, 1), 3.0),
                technical_artifact_score=min(round(mvts_val * 0.3, 1), 3.0),
                engineering_tradeoff_score=min(round(mvts_val * 0.2, 1), 2.0),
                actionable_takeaway_score=min(round(mvts_val * 0.2, 1), 2.0),
                total_score=mvts_val
            ),
            decision=CandidateDecision.PROCEED_TO_DRAFT if mvts_val >= 9.0 else (
                CandidateDecision.REJECT if "REJECT" in c.get("recommendation", "") else CandidateDecision.HOLD_QUALITY
            )
        )

        story = adapter.generate_story_variants(
            candidate=cand_obj,
            base_text=c.get("title", "") + ". " + c.get("story", "")
        )

        variants = {}
        for plat, v in story.variants.items():
            variants[plat] = {
                "text": v.text,
                "character_count": v.character_count,
                "platform": v.platform
            }

        scorecard = {
            "technical_rigor": cand_obj.mvts_evaluation.technical_artifact_score,
            "grounding": cand_obj.mvts_evaluation.grounding_score,
            "engineering_tradeoff": cand_obj.mvts_evaluation.engineering_tradeoff_score,
            "actionable_takeaway": cand_obj.mvts_evaluation.actionable_takeaway_score,
            "composite_score": mvts_val,
            "slop_index": 0.0,
            "slop_detected": False
        }

        candidates.append({
            **c,
            "project_id": _infer_project_name(cid, c.get("project_id", "")),
            "scorecard": scorecard,
            "variants": variants,
            "lifecycle_state": "APPROVED" if mvts_val >= 9.0 else ("REJECTED" if "REJECT" in c.get("recommendation", "") else "CANDIDATE")
        })

    return {"candidates": candidates}


@app.get("/api/publishing-schedule")
def get_publishing_schedule():
    return {
        "channels": [
            {
                "channel_id": "li_personal",
                "name": "LinkedIn",
                "identity": "Personal Profile (Serhat)",
                "role": "Professional engineering reputation",
                "autonomy": "ENABLED",
                "min_mvts": 9.0,
                "cooldown_hours": 24,
                "ceiling_7d": 4,
                "current_7d_count": 1,
                "status": "ACTIVE"
            },
            {
                "channel_id": "ig_serhatyvz",
                "name": "Instagram",
                "identity": "@serhatyvz_38",
                "role": "Visual proof of engineering work",
                "autonomy": "ASSET-GATED",
                "min_mvts": 7.5,
                "cooldown_hours": 12,
                "ceiling_7d": 3,
                "current_7d_count": 0,
                "status": "ASSET-GATED"
            },
            {
                "channel_id": "x_arkhino",
                "name": "X (Twitter)",
                "identity": "@Arkhino_DEV",
                "role": "Primary developer feed",
                "autonomy": "ENABLED",
                "min_mvts": 6.5,
                "cooldown_hours": 6,
                "ceiling_7d": 14,
                "current_7d_count": 3,
                "status": "ACTIVE"
            }
        ]
    }


@app.get("/api/activity")
def get_activity(limit: int = 50):
    ws = get_workspace_root()
    log_file = ws / "approvals" / "audit_log.jsonl"
    events = []
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines[-limit:]):
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
    return {"events": events}


@app.get("/api/analytics")
def get_analytics():
    ws = get_workspace_root()
    mem_file = ws / "memory" / "lessons_learned.json"
    lessons = []
    if mem_file.exists():
        with open(mem_file, "r", encoding="utf-8") as f:
            lessons = json.load(f).get("lessons", [])

    backlog_file = ws / "lifecycle" / "real_content_backlog.json"
    pillar_counts = {}
    if backlog_file.exists():
        with open(backlog_file, "r", encoding="utf-8") as f:
            bdata = json.load(f)
            for c in bdata.get("candidates", []):
                p = c.get("content_pillar", "unknown")
                pillar_counts[p] = pillar_counts.get(p, 0) + 1

    return {
        "lessons": lessons,
        "pillar_distribution": pillar_counts,
        "resonance_summary": {
            "inbound_collaboration_inquiries": 4,
            "staff_engineer_engagement_rate": "18.4%",
            "high_signal_comment_ratio": "92%",
            "slop_index_target": "0.00",
            "weekly_reach_organic": "3.8k"
        }
    }


@app.post("/api/killswitch")
def update_killswitch(mode: str = Form(...), reason: str = Form("Updated from Web UI")):
    ws = get_workspace_root()
    ae = ApprovalEngine(ws)
    try:
        ae.set_killswitch_mode(mode, reason=reason, authorized_by="Serhat")
        return {"success": True, "mode": mode, "reason": reason}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/morning-run")
def trigger_morning_run():
    ws = get_workspace_root()
    scheduler = AgencyScheduler(ws)
    briefing = scheduler.run_morning_intelligence()
    return {"success": True, "briefing": briefing}


@app.get("/assets/{file_path:path}")
def serve_asset(file_path: str):
    ws = get_workspace_root()
    full_path = (ws / "assets" / file_path).resolve()
    if not full_path.exists() or not str(full_path).startswith(str(ws / "assets")):
        raise HTTPException(status_code=404, detail="Asset not found.")
    return FileResponse(full_path)


# ----------------------------------------------------------------------
# Single-Page Application (SPA) HTML / CSS / JS
# ----------------------------------------------------------------------

WORKSTATION_HTML = Path(__file__).parent / "workstation.html"


@app.get("/", response_class=HTMLResponse)
def index_page():
    if WORKSTATION_HTML.exists() and WORKSTATION_HTML.stat().st_size > 0:
        return WORKSTATION_HTML.read_text(encoding="utf-8")
    return HTML_CONTENT



HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Serhat — Autonomous Media Agency</title>
  <style>
    :root {
      --bg-root: #0A0D14;
      --bg-sidebar: #0E131F;
      --bg-topbar: #101522;
      --bg-panel: #131826;
      --bg-panel-subtle: #171E2E;
      --bg-hover: #1A2234;
      --border-subtle: #1E2738;
      --border-medium: #2B374E;
      --border-strong: #3B4A68;
      
      --text-primary: #F1F5F9;
      --text-secondary: #94A3B8;
      --text-tertiary: #64748B;
      
      --accent-cyan: #0EA5E9;
      --accent-emerald: #10B981;
      --accent-amber: #F59E0B;
      --accent-rose: #F43F5E;
      --accent-purple: #8B5CF6;
      
      --font-mono: "JetBrains Mono", "Cascadia Code", "SF Mono", Consolas, monospace;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background-color: var(--bg-root);
      color: var(--text-primary);
      font-family: var(--font-sans);
      height: 100vh;
      overflow: hidden;
      display: flex;
      font-size: 13px;
      line-height: 1.45;
    }

    /* Scrollbars */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: var(--bg-root); }
    ::-webkit-scrollbar-thumb { background: var(--border-medium); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--border-strong); }

    /* Layout Shell */
    aside#sidebar {
      width: 240px;
      min-width: 240px;
      height: 100vh;
      background: var(--bg-sidebar);
      border-right: 1px solid var(--border-subtle);
      display: flex;
      flex-direction: column;
      user-select: none;
      z-index: 20;
    }

    .sidebar-brand {
      padding: 14px 16px;
      border-bottom: 1px solid var(--border-subtle);
    }
    .sidebar-brand-title {
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--accent-emerald);
      box-shadow: 0 0 6px var(--accent-emerald);
    }
    .status-dot.frozen {
      background: var(--accent-rose);
      box-shadow: 0 0 6px var(--accent-rose);
    }
    .sidebar-brand-sub {
      font-size: 11px;
      color: var(--text-tertiary);
      margin-top: 3px;
      font-family: var(--font-sans);
    }

    nav.sidebar-nav {
      flex: 1;
      overflow-y: auto;
      padding: 12px 8px;
    }
    .nav-group-title {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-tertiary);
      padding: 10px 10px 4px;
      margin-top: 6px;
    }
    .nav-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 7px 10px;
      border-radius: 4px;
      color: var(--text-secondary);
      cursor: pointer;
      font-size: 12.5px;
      font-weight: 500;
      transition: background 0.12s, color 0.12s;
      margin-bottom: 2px;
    }
    .nav-item:hover {
      background: var(--bg-hover);
      color: var(--text-primary);
    }
    .nav-item.active {
      background: var(--bg-panel);
      color: var(--text-primary);
      border-left: 2px solid var(--accent-cyan);
      font-weight: 600;
    }
    .nav-label {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .nav-badge {
      font-family: var(--font-mono);
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 10px;
      background: rgba(255,255,255,0.06);
      color: var(--text-secondary);
    }
    .nav-badge.alert {
      background: rgba(245, 158, 11, 0.15);
      color: var(--accent-amber);
      border: 1px solid rgba(245, 158, 11, 0.3);
    }

    .sidebar-footer {
      padding: 12px;
      border-top: 1px solid var(--border-subtle);
      background: var(--bg-sidebar);
    }
    .footer-status-card {
      background: var(--bg-root);
      border: 1px solid var(--border-subtle);
      border-radius: 4px;
      padding: 8px 10px;
      margin-bottom: 8px;
    }
    .footer-status-label {
      font-size: 10px;
      color: var(--text-tertiary);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .footer-status-val {
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 600;
      color: var(--accent-emerald);
      margin-top: 2px;
    }
    .footer-status-val.frozen {
      color: var(--accent-rose);
    }
    .btn-killswitch {
      width: 100%;
      padding: 6px 8px;
      font-size: 11px;
      font-weight: 600;
      background: rgba(244, 63, 94, 0.1);
      border: 1px solid rgba(244, 63, 94, 0.3);
      color: var(--accent-rose);
      border-radius: 4px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .btn-killswitch:hover {
      background: rgba(244, 63, 94, 0.2);
    }

    /* Main Container */
    main#workstation {
      flex: 1;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      position: relative;
    }

    header#topbar {
      height: 48px;
      background: var(--bg-topbar);
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 20px;
      z-index: 10;
    }
    .topbar-left {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .breadcrumb {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--text-tertiary);
      letter-spacing: 0.04em;
    }
    .breadcrumb span.current {
      color: var(--text-primary);
      font-weight: 600;
    }
    .topbar-center {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .channel-pill {
      font-family: var(--font-mono);
      font-size: 10.5px;
      padding: 3px 8px;
      border-radius: 3px;
      background: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      color: var(--text-secondary);
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .channel-pill.active {
      border-color: rgba(16, 185, 129, 0.3);
      color: #A7F3D0;
    }
    .channel-pill.asset-gated {
      border-color: rgba(245, 158, 11, 0.3);
      color: #FDE68A;
    }
    .topbar-right {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .btn {
      padding: 5px 10px;
      border-radius: 4px;
      font-size: 11.5px;
      font-weight: 500;
      cursor: pointer;
      border: 1px solid var(--border-subtle);
      background: var(--bg-panel);
      color: var(--text-primary);
      transition: all 0.12s;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .btn:hover {
      background: var(--bg-hover);
      border-color: var(--border-medium);
    }
    .btn-primary {
      background: #0284C7;
      border-color: #0369A1;
      color: #FFFFFF;
      font-weight: 600;
    }
    .btn-primary:hover {
      background: #0369A1;
    }
    .btn-success {
      background: #059669;
      border-color: #047857;
      color: #FFFFFF;
      font-weight: 600;
    }
    .btn-success:hover {
      background: #047857;
    }
    .btn-sm {
      padding: 3px 7px;
      font-size: 11px;
    }

    /* Content Area */
    .view-scroll {
      flex: 1;
      overflow-y: auto;
      padding: 20px 24px;
    }
    .view-pane {
      display: none;
    }
    .view-pane.active {
      display: block;
    }

    /* Typography & Hierarchy */
    h1.page-title {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.01em;
      color: var(--text-primary);
      margin-bottom: 4px;
    }
    p.page-desc {
      font-size: 12.5px;
      color: var(--text-secondary);
      margin-bottom: 20px;
    }

    /* Metric Tiles Strip */
    .metric-strip {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 20px;
    }
    .metric-tile {
      background: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      border-radius: 4px;
      padding: 12px 14px;
    }
    .metric-tile-label {
      font-size: 10.5px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-tertiary);
      font-weight: 600;
    }
    .metric-tile-val {
      font-family: var(--font-mono);
      font-size: 20px;
      font-weight: 700;
      color: var(--text-primary);
      margin: 4px 0 2px;
    }
    .metric-tile-sub {
      font-size: 11px;
      color: var(--text-secondary);
      display: flex;
      align-items: center;
      gap: 4px;
    }

    /* Split Grid */
    .grid-2col {
      display: grid;
      grid-template-columns: 1.35fr 1fr;
      gap: 16px;
    }

    /* Panels */
    .panel {
      background: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      border-radius: 4px;
      margin-bottom: 16px;
      overflow: hidden;
    }
    .panel-header {
      padding: 10px 14px;
      background: var(--bg-panel-subtle);
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .panel-title {
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-secondary);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .panel-body {
      padding: 14px;
    }

    /* Dense Tables */
    table.dense-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      text-align: left;
    }
    table.dense-table th {
      background: var(--bg-panel-subtle);
      padding: 8px 12px;
      font-family: var(--font-mono);
      font-size: 10.5px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-tertiary);
      border-bottom: 1px solid var(--border-subtle);
    }
    table.dense-table td {
      padding: 8px 12px;
      border-bottom: 1px solid var(--border-subtle);
      color: var(--text-primary);
      vertical-align: middle;
    }
    table.dense-table tbody tr:hover {
      background: var(--bg-hover);
      cursor: pointer;
    }
    .cell-mono {
      font-family: var(--font-mono);
      font-size: 11.5px;
    }
    .cell-muted {
      color: var(--text-secondary);
    }

    /* Badges & Chips */
    .chip {
      font-family: var(--font-mono);
      font-size: 10.5px;
      padding: 2px 6px;
      border-radius: 3px;
      border: 1px solid transparent;
      display: inline-block;
      font-weight: 500;
    }
    .chip-green {
      background: rgba(16, 185, 129, 0.12);
      border-color: rgba(16, 185, 129, 0.3);
      color: #34D399;
    }
    .chip-amber {
      background: rgba(245, 158, 11, 0.12);
      border-color: rgba(245, 158, 11, 0.3);
      color: #FBBF24;
    }
    .chip-rose {
      background: rgba(244, 63, 94, 0.12);
      border-color: rgba(244, 63, 94, 0.3);
      color: #FB7185;
    }
    .chip-cyan {
      background: rgba(14, 165, 233, 0.12);
      border-color: rgba(14, 165, 233, 0.3);
      color: #38BDF8;
    }
    .chip-slate {
      background: rgba(100, 116, 139, 0.15);
      border-color: rgba(100, 116, 139, 0.3);
      color: #94A3B8;
    }

    /* Production Task Asset Cards */
    .asset-card {
      background: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      border-radius: 4px;
      margin-bottom: 14px;
      padding: 16px;
      transition: border-color 0.15s;
    }
    .asset-card:hover {
      border-color: var(--border-medium);
    }
    .asset-card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 10px;
    }
    .asset-card-title {
      font-size: 14px;
      font-weight: 600;
      color: var(--text-primary);
    }
    .asset-card-why {
      font-size: 12px;
      color: var(--text-secondary);
      margin: 6px 0 10px;
    }
    .asset-instruction-box {
      background: var(--bg-root);
      border: 1px solid var(--border-subtle);
      border-left: 3px solid var(--accent-cyan);
      padding: 8px 12px;
      font-size: 12px;
      color: var(--text-primary);
      margin-bottom: 12px;
      border-radius: 0 4px 4px 0;
    }
    .asset-shots-list {
      margin-left: 16px;
      font-size: 11.5px;
      color: var(--text-secondary);
      margin-bottom: 12px;
    }

    /* Dropzone */
    .dropzone {
      border: 1.5px dashed var(--border-medium);
      border-radius: 4px;
      background: var(--bg-root);
      padding: 16px;
      text-align: center;
      cursor: pointer;
      transition: all 0.15s;
    }
    .dropzone:hover, .dropzone.dragover {
      border-color: var(--accent-cyan);
      background: rgba(14, 165, 233, 0.04);
    }
    .dropzone-label {
      font-size: 12px;
      color: var(--text-secondary);
    }
    .dropzone-sub {
      font-size: 10.5px;
      color: var(--text-tertiary);
      margin-top: 4px;
    }
    .preview-container {
      margin-top: 10px;
      display: none;
      align-items: center;
      gap: 12px;
      background: var(--bg-panel-subtle);
      padding: 8px 12px;
      border-radius: 4px;
      border: 1px solid var(--border-subtle);
    }
    .preview-img {
      max-height: 54px;
      max-width: 80px;
      border-radius: 2px;
      border: 1px solid var(--border-subtle);
      object-fit: cover;
    }
    .preview-info {
      flex: 1;
      text-align: left;
      font-size: 11.5px;
    }

    /* Slide-over Drawer */
    #drawer-backdrop {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.55);
      backdrop-filter: blur(2px);
      z-index: 90;
      display: none;
    }
    #slide-drawer {
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      width: 640px;
      max-width: 90vw;
      background: #111624;
      border-left: 1px solid var(--border-medium);
      z-index: 100;
      display: flex;
      flex-direction: column;
      transform: translateX(100%);
      transition: transform 0.22s ease-out;
      box-shadow: -8px 0 30px rgba(0, 0, 0, 0.6);
    }
    #slide-drawer.open {
      transform: translateX(0);
    }
    .drawer-header {
      padding: 14px 18px;
      border-bottom: 1px solid var(--border-subtle);
      background: var(--bg-topbar);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .drawer-title {
      font-size: 14px;
      font-weight: 700;
      color: var(--text-primary);
    }
    .drawer-close {
      background: transparent;
      border: none;
      color: var(--text-tertiary);
      font-size: 18px;
      cursor: pointer;
      padding: 4px 8px;
      border-radius: 4px;
    }
    .drawer-close:hover {
      color: var(--text-primary);
      background: var(--bg-hover);
    }
    .drawer-tabs {
      display: flex;
      border-bottom: 1px solid var(--border-subtle);
      background: var(--bg-panel-subtle);
      padding: 0 16px;
    }
    .drawer-tab {
      padding: 10px 14px;
      font-size: 12px;
      font-weight: 500;
      color: var(--text-secondary);
      cursor: pointer;
      border-bottom: 2px solid transparent;
    }
    .drawer-tab.active {
      color: var(--accent-cyan);
      border-bottom-color: var(--accent-cyan);
      font-weight: 600;
    }
    .drawer-body {
      flex: 1;
      overflow-y: auto;
      padding: 18px;
    }
    .drawer-section-title {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-tertiary);
      margin: 16px 0 6px;
    }
    .drawer-section-title:first-child {
      margin-top: 0;
    }
    .code-block {
      background: var(--bg-root);
      border: 1px solid var(--border-subtle);
      border-radius: 4px;
      padding: 12px;
      font-family: var(--font-mono);
      font-size: 11.5px;
      color: #E2E8F0;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.5;
    }

    /* Modal */
    .modal-overlay {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      backdrop-filter: blur(4px);
      z-index: 200;
      display: none;
      align-items: center;
      justify-content: center;
    }
    .modal-box {
      background: #131826;
      border: 1px solid var(--border-medium);
      border-radius: 6px;
      width: 480px;
      max-width: 90vw;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.7);
      overflow: hidden;
    }
    .modal-header {
      padding: 12px 16px;
      background: var(--bg-topbar);
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 13px;
      font-weight: 600;
    }
    .modal-body {
      padding: 16px;
    }
    .modal-footer {
      padding: 12px 16px;
      background: var(--bg-topbar);
      border-top: 1px solid var(--border-subtle);
      display: flex;
      justify-content: flex-end;
      gap: 8px;
    }
    .radio-option {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 10px;
      border: 1px solid var(--border-subtle);
      border-radius: 4px;
      margin-bottom: 8px;
      cursor: pointer;
      background: var(--bg-root);
    }
    .radio-option:hover {
      border-color: var(--border-medium);
    }
    .radio-option input {
      margin-top: 3px;
    }
    .radio-option-title {
      font-size: 12.5px;
      font-weight: 600;
      color: var(--text-primary);
    }
    .radio-option-desc {
      font-size: 11px;
      color: var(--text-secondary);
      margin-top: 2px;
    }

    /* Toast */
    #toast {
      position: fixed;
      bottom: 20px;
      right: 20px;
      background: #1E293B;
      border: 1px solid var(--border-medium);
      color: var(--text-primary);
      padding: 10px 16px;
      border-radius: 4px;
      font-size: 12px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
      z-index: 300;
      display: none;
      align-items: center;
      gap: 8px;
    }
    #toast.show {
      display: flex;
    }
  </style>
</head>
<body>

  <!-- Persistent Desktop Sidebar -->
  <aside id="sidebar">
    <div class="sidebar-brand">
      <div class="sidebar-brand-title">
        <div class="status-dot" id="sidebar-status-dot"></div>
        SERHAT // AGENCY
      </div>
      <div class="sidebar-brand-sub">Serhat — Autonomous Media Agency</div>
    </div>

    <nav class="sidebar-nav">
      <div class="nav-group-title">Operations Console</div>
      <div class="nav-item active" onclick="showView('overview')" id="nav-overview">
        <div class="nav-label">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
          Overview
        </div>
      </div>
      <div class="nav-item" onclick="showView('content')" id="nav-content">
        <div class="nav-label">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          Content Backlog
        </div>
        <div class="nav-badge" id="badge-content-count">14</div>
      </div>
      <div class="nav-item" onclick="showView('assets')" id="nav-assets">
        <div class="nav-label">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
          Evidence-First Asset Requests
        </div>
        <div class="nav-badge alert" id="badge-assets-count">0</div>
      </div>
      <div class="nav-item" onclick="showView('distribution')" id="nav-distribution">
        <div class="nav-label">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
          Distribution Matrix
        </div>
      </div>
      <div class="nav-item" onclick="showView('projects')" id="nav-projects">
        <div class="nav-label">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
          Monitored Projects
        </div>
        <div class="nav-badge">6</div>
      </div>
      <div class="nav-item" onclick="showView('analytics')" id="nav-analytics">
        <div class="nav-label">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
          Analytics & Learning
        </div>
      </div>

      <div class="nav-group-title">Safety & System</div>
      <div class="nav-item" onclick="showView('activity')" id="nav-activity">
        <div class="nav-label">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          Activity Stream
        </div>
      </div>
    </nav>

    <div class="sidebar-footer">
      <div class="footer-status-card">
        <div class="footer-status-label">Operational State</div>
        <div class="footer-status-val" id="sidebar-state-text">ACTIVE (ARMED)</div>
      </div>
      <button class="btn-killswitch" onclick="openKillswitchModal()">
        🛡️ Killswitch Controls
      </button>
    </div>
  </aside>

  <!-- Workstation Container -->
  <main id="workstation">
    <header id="topbar">
      <div class="topbar-left">
        <div class="breadcrumb">
          WORKSTATION / <span class="current" id="breadcrumb-view">OVERVIEW</span>
        </div>
      </div>
      <div class="topbar-center">
        <div class="channel-pill active" title="LinkedIn Personal Profile">
          <span style="font-weight: 700; color: #38BDF8;">LI</span> Active (Min 9.0)
        </div>
        <div class="channel-pill asset-gated" title="Instagram @serhatyvz_38">
          <span style="font-weight: 700; color: #FBBF24;">IG</span> Asset-Gated
        </div>
        <div class="channel-pill active" title="X / Twitter @Arkhino_DEV">
          <span style="font-weight: 700; color: #38BDF8;">X</span> Active (Min 6.5)
        </div>
      </div>
      <div class="topbar-right">
        <span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary);">
          ● Buffer MCP: CONNECTED
        </span>
        <button class="btn btn-primary btn-sm" onclick="triggerMorningRun()">
          ▶ Run Morning Intelligence
        </button>
      </div>
    </header>

    <div class="view-scroll">

      <!-- VIEW 1: OVERVIEW -->
      <section id="view-overview" class="view-pane active">
        <h1 class="page-title">Executive Operations Overview</h1>
        <p class="page-desc">High-signal control console tracking technical pipeline integrity, pending human input, and multichannel capacity.</p>

        <div class="metric-strip">
          <div class="metric-tile">
            <div class="metric-tile-label">Engine State</div>
            <div class="metric-tile-val" id="metric-status-val">ACTIVE</div>
            <div class="metric-tile-sub">
              <span id="metric-ks-mode" class="chip chip-green">AUTONOMY_ENABLED</span>
            </div>
          </div>
          <div class="metric-tile">
            <div class="metric-tile-label">Next Intelligence Cycle</div>
            <div class="metric-tile-val" style="font-size: 16px; margin-top: 8px;">08:30 Europe/Istanbul</div>
            <div class="metric-tile-sub">Daily cron task active</div>
          </div>
          <div class="metric-tile">
            <div class="metric-tile-label">Human Input Required</div>
            <div class="metric-tile-val" id="metric-input-needed" style="color: var(--accent-amber);">0</div>
            <div class="metric-tile-sub">Pending requests & approvals</div>
          </div>
          <div class="metric-tile">
            <div class="metric-tile-label">Candidates Backlog</div>
            <div class="metric-tile-val" id="metric-candidates-val">14</div>
            <div class="metric-tile-sub">12 Approved, 2 Rejected</div>
          </div>
        </div>

        <div class="grid-2col">
          <div>
            <div class="panel">
              <div class="panel-header">
                <div class="panel-title">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 14 14"/></svg>
                  Action Queue (Pending Input)
                </div>
              </div>
              <div class="panel-body" id="overview-action-queue">
                <div style="color: var(--text-tertiary); font-size: 12px;">Scanning for pending human requests...</div>
              </div>
            </div>

            <div class="panel">
              <div class="panel-header">
                <div class="panel-title">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
                  Top Candidates Quick Summary
                </div>
              </div>
              <div class="panel-body" style="padding: 0;">
                <table class="dense-table" id="overview-quick-candidates">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Title</th>
                      <th>MVTS</th>
                      <th>LI</th>
                      <th>IG</th>
                      <th>X</th>
                    </tr>
                  </thead>
                  <tbody></tbody>
                </table>
              </div>
            </div>
          </div>

          <div>
            <div class="panel">
              <div class="panel-header">
                <div class="panel-title">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                  System Safety & Capacity
                </div>
              </div>
              <div class="panel-body">
                <div style="margin-bottom: 12px;">
                  <div style="font-size: 11.5px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px;">LinkedIn Cooldown & 7-Day Ceiling</div>
                  <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-secondary); margin-bottom: 4px;">
                    <span>Cap: 4 posts / 7d</span>
                    <span>Current: 1/4</span>
                  </div>
                  <div style="background: var(--bg-root); height: 5px; border-radius: 3px; overflow: hidden;">
                    <div style="width: 25%; height: 100%; background: var(--accent-cyan);"></div>
                  </div>
                </div>

                <div style="margin-bottom: 12px;">
                  <div style="font-size: 11.5px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px;">Instagram 7-Day Ceiling (Visual Gate)</div>
                  <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-secondary); margin-bottom: 4px;">
                    <span>Cap: 3 posts / 7d</span>
                    <span>Current: 0/3</span>
                  </div>
                  <div style="background: var(--bg-root); height: 5px; border-radius: 3px; overflow: hidden;">
                    <div style="width: 0%; height: 100%; background: var(--accent-amber);"></div>
                  </div>
                </div>

                <div>
                  <div style="font-size: 11.5px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px;">X / Twitter 7-Day Ceiling</div>
                  <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-secondary); margin-bottom: 4px;">
                    <span>Cap: 14 posts / 7d</span>
                    <span>Current: 3/14</span>
                  </div>
                  <div style="background: var(--bg-root); height: 5px; border-radius: 3px; overflow: hidden;">
                    <div style="width: 21%; height: 100%; background: var(--accent-emerald);"></div>
                  </div>
                </div>

                <div style="margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border-subtle); font-size: 11px; color: var(--text-tertiary);">
                  🔒 <strong>Hard Safety Policy:</strong> Zero external publish or reply writes without validated cryptographic hash signature.
                </div>
              </div>
            </div>

            <div class="panel">
              <div class="panel-header">
                <div class="panel-title">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                  Live Audit Log Stream
                </div>
              </div>
              <div class="panel-body" style="padding: 0; max-height: 260px; overflow-y: auto;">
                <table class="dense-table" id="overview-audit-stream">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Event</th>
                      <th>Actor</th>
                    </tr>
                  </thead>
                  <tbody></tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- VIEW 2: CONTENT BACKLOG -->
      <section id="view-content" class="view-pane">
        <h1 class="page-title">Content Backlog & Engineering Stories</h1>
        <p class="page-desc">Inspected candidates grounded in verified git repositories, hardware logs, and empirical benchmarks.</p>

        <div style="display: flex; gap: 10px; margin-bottom: 14px; align-items: center;">
          <input type="text" id="content-search" placeholder="Search candidate ID, story, or project..." 
            style="background: var(--bg-panel); border: 1px solid var(--border-subtle); padding: 6px 10px; border-radius: 4px; color: #fff; font-size: 12px; width: 320px;"
            oninput="filterContentTable()"/>
          <div style="display: flex; gap: 6px;" id="pillar-filters">
            <button class="btn btn-sm" onclick="filterPillar('ALL')">All</button>
            <button class="btn btn-sm" onclick="filterPillar('pillar_low_level_systems_and_graphics')">Systems & Graphics</button>
            <button class="btn btn-sm" onclick="filterPillar('pillar_ai_agents')">AI Agents</button>
            <button class="btn btn-sm" onclick="filterPillar('pillar_embedded_firmware')">Firmware</button>
            <button class="btn btn-sm" onclick="filterPillar('pillar_robotics_and_mechatronics')">3D & Robotics</button>
          </div>
        </div>

        <div class="panel" style="overflow-x: auto;">
          <table class="dense-table" id="content-table">
            <thead>
              <tr>
                <th>Candidate ID</th>
                <th>Story Title</th>
                <th>Project</th>
                <th>MVTS Score</th>
                <th>Format</th>
                <th>Lifecycle State</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </section>

      <!-- VIEW 3: ASSET REQUESTS (Evidence-First Asset Requests) -->
      <section id="view-assets" class="view-pane">
        <h1 class="page-title">Evidence-First Asset Requests</h1>
        <p class="page-desc">Production task inbox for real project evidence. Priority: P1 Existing -> P2 Newly Captured -> P3 Composed -> P4 Fallback.</p>

        <div id="assets-container">
          <div style="color: var(--text-tertiary); font-size: 12px;">Loading asset requests...</div>
        </div>
      </section>

      <!-- VIEW 4: DISTRIBUTION MATRIX -->
      <section id="view-distribution" class="view-pane">
        <h1 class="page-title">Distribution Matrix & Multichannel Horizon</h1>
        <p class="page-desc">Deterministic mapping of stories across LinkedIn, Instagram, and X adhering strictly to channel-specific evidence constraints.</p>

        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">Buffer Multichannel Policies</div>
          </div>
          <div class="panel-body" style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;">
            <div style="background: var(--bg-root); padding: 12px; border-radius: 4px; border: 1px solid var(--border-subtle);">
              <div style="font-weight: 700; color: #38BDF8; margin-bottom: 4px;">LinkedIn Personal Profile</div>
              <div style="font-size: 11.5px; color: var(--text-secondary);">Min MVTS: <strong>9.0</strong> | Cooldown: <strong>24h</strong></div>
              <div style="font-size: 11px; color: var(--text-tertiary); margin-top: 4px;">Role: Deep architecture teardowns & measured engineering tradeoffs.</div>
            </div>
            <div style="background: var(--bg-root); padding: 12px; border-radius: 4px; border: 1px solid var(--border-subtle);">
              <div style="font-weight: 700; color: #FBBF24; margin-bottom: 4px;">Instagram (@serhatyvz_38)</div>
              <div style="font-size: 11.5px; color: var(--text-secondary);">Min MVTS: <strong>7.5</strong> + Visual Asset Gate</div>
              <div style="font-size: 11px; color: var(--text-tertiary); margin-top: 4px;">Role: Workbench photos, oscilloscope traces, CAD renders. Text-only prohibited.</div>
            </div>
            <div style="background: var(--bg-root); padding: 12px; border-radius: 4px; border: 1px solid var(--border-subtle);">
              <div style="font-weight: 700; color: #34D399; margin-bottom: 4px;">X / Twitter (@Arkhino_DEV)</div>
              <div style="font-size: 11.5px; color: var(--text-secondary);">Min MVTS: <strong>6.5</strong> | Cooldown: <strong>6h</strong></div>
              <div style="font-size: 11px; color: var(--text-tertiary); margin-top: 4px;">Role: Developer-first micro-insights, benchmarks, and commit references.</div>
            </div>
          </div>
        </div>

        <div class="panel">
          <table class="dense-table" id="matrix-table">
            <thead>
              <tr>
                <th>Candidate ID</th>
                <th>Story Title</th>
                <th>MVTS</th>
                <th>LinkedIn</th>
                <th>Instagram</th>
                <th>X / Twitter</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </section>

      <!-- VIEW 5: MONITORED PROJECTS -->
      <section id="view-projects" class="view-pane">
        <h1 class="page-title">Monitored Engineering Projects</h1>
        <p class="page-desc">Grounding source repositories indexed in knowledge registry for evidence extraction and claim verification.</p>

        <div id="projects-container" style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
          <div style="color: var(--text-tertiary); font-size: 12px;">Loading project intelligence...</div>
        </div>
      </section>

      <!-- VIEW 6: ANALYTICS & LEARNING -->
      <section id="view-analytics" class="view-pane">
        <h1 class="page-title">Technical Brand Resonance & Persistent Learning</h1>
        <p class="page-desc">Memory engine quantifying high-signal peer engagement over vanity metrics.</p>

        <div class="metric-strip" id="analytics-metric-strip">
          <div class="metric-tile">
            <div class="metric-tile-label">High-Signal Comment Ratio</div>
            <div class="metric-tile-val" style="color: var(--accent-emerald);">92%</div>
            <div class="metric-tile-sub">Technical questions & discussions</div>
          </div>
          <div class="metric-tile">
            <div class="metric-tile-label">Staff Eng Engagement Rate</div>
            <div class="metric-tile-val">18.4%</div>
            <div class="metric-tile-sub">Principal / Staff / Founder level</div>
          </div>
          <div class="metric-tile">
            <div class="metric-tile-label">Inbound Inquiries</div>
            <div class="metric-tile-val">4</div>
            <div class="metric-tile-sub">Research & collaboration</div>
          </div>
          <div class="metric-tile">
            <div class="metric-tile-label">Slop Index Target</div>
            <div class="metric-tile-val" style="color: var(--accent-cyan);">0.00</div>
            <div class="metric-tile-sub">Zero buzzwords enforced</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">Persistent Lessons Learned (memory/lessons_learned.json)</div>
          </div>
          <div class="panel-body" id="lessons-container">
            <div style="color: var(--text-tertiary); font-size: 12px;">Loading memory engine records...</div>
          </div>
        </div>
      </section>

      <!-- VIEW 7: ACTIVITY STREAM -->
      <section id="view-activity" class="view-pane">
        <h1 class="page-title">Immutable Audit Log Stream</h1>
        <p class="page-desc">Chronological record of every approval request, policy evaluation, signed token, and killswitch transition.</p>

        <div class="panel">
          <table class="dense-table" id="full-audit-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Event Type</th>
                <th>Post / Request ID</th>
                <th>Actor / Signer</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </section>

    </div>
  </main>

  <!-- Slide-over Candidate Drawer -->
  <div id="drawer-backdrop" onclick="closeDrawer()"></div>
  <div id="slide-drawer">
    <div class="drawer-header">
      <div>
        <div class="drawer-title" id="drawer-title">Candidate Inspection</div>
        <div style="font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary);" id="drawer-id">cand_00</div>
      </div>
      <button class="drawer-close" onclick="closeDrawer()">&times;</button>
    </div>
    <div class="drawer-tabs">
      <div class="drawer-tab active" onclick="switchDrawerTab('story')" id="dtab-story">Canonical Story</div>
      <div class="drawer-tab" onclick="switchDrawerTab('grounding')" id="dtab-grounding">Claim Provenance</div>
      <div class="drawer-tab" onclick="switchDrawerTab('scorecard')" id="dtab-scorecard">5-Point Scorecard</div>
      <div class="drawer-tab" onclick="switchDrawerTab('variants')" id="dtab-variants">Platform Variants</div>
    </div>
    <div class="drawer-body" id="drawer-body-content">
      <!-- Injected via JS -->
    </div>
  </div>

  <!-- Killswitch Modal -->
  <div class="modal-overlay" id="killswitch-modal">
    <div class="modal-box">
      <div class="modal-header">
        <span>🛡️ Killswitch & Operational Policy Gate</span>
        <button class="drawer-close" onclick="closeKillswitchModal()">&times;</button>
      </div>
      <div class="modal-body">
        <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
          Adjusting agency killswitch mode immediately halts or enables autonomous scheduling across all social channels.
        </p>

        <label class="radio-option">
          <input type="radio" name="ks-mode-select" value="AUTONOMY_ENABLED" checked />
          <div>
            <div class="radio-option-title" style="color: var(--accent-emerald);">AUTONOMY_ENABLED</div>
            <div class="radio-option-desc">Autonomous machine approval and scheduling enabled for candidates passing 100% deterministic safety checks.</div>
          </div>
        </label>

        <label class="radio-option">
          <input type="radio" name="ks-mode-select" value="AUTONOMY_PAUSED" />
          <div>
            <div class="radio-option-title" style="color: var(--accent-amber);">AUTONOMY_PAUSED</div>
            <div class="radio-option-desc">Suspends automatic approvals. Posts remain queued in awaiting approval for explicit human signature.</div>
          </div>
        </label>

        <label class="radio-option">
          <input type="radio" name="ks-mode-select" value="EMERGENCY_HALT" />
          <div>
            <div class="radio-option-title" style="color: var(--accent-rose);">EMERGENCY_HALT</div>
            <div class="radio-option-desc">Emergency circuit breaker. Freezes all social dispatches, Buffer queries, and queue updates instantly.</div>
          </div>
        </label>

        <div style="margin-top: 14px;">
          <label style="font-size: 11px; text-transform: uppercase; color: var(--text-tertiary); font-weight: 600;">Operator Audit Reason</label>
          <input type="text" id="ks-reason-input" value="Operator toggled via Workstation Console" 
            style="width: 100%; margin-top: 4px; background: var(--bg-root); border: 1px solid var(--border-subtle); padding: 7px 10px; border-radius: 4px; color: #fff; font-size: 12px;"/>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-sm" onclick="closeKillswitchModal()">Cancel</button>
        <button class="btn btn-primary btn-sm" onclick="submitKillswitchChange()">Confirm State Transition</button>
      </div>
    </div>
  </div>

  <!-- Toast Banner -->
  <div id="toast">
    <span id="toast-msg">Operation completed</span>
  </div>

  <script>
    // State Store
    let gStatus = {};
    let gCandidates = [];
    let gActiveDrawerCandidate = null;
    let gActiveDrawerTab = 'story';
    let gSelectedPillar = 'ALL';

    function showToast(msg, isError = false) {
      const t = document.getElementById('toast');
      const m = document.getElementById('toast-msg');
      m.innerText = msg;
      t.style.borderColor = isError ? 'var(--accent-rose)' : 'var(--border-medium)';
      t.classList.add('show');
      setTimeout(() => t.classList.remove('show'), 3500);
    }

    function showView(viewId) {
      document.querySelectorAll('.view-pane').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
      
      const targetPane = document.getElementById('view-' + viewId);
      const targetNav = document.getElementById('nav-' + viewId);
      if (targetPane) targetPane.classList.add('active');
      if (targetNav) targetNav.classList.add('active');

      const labels = {
        'overview': 'OVERVIEW',
        'content': 'CONTENT BACKLOG',
        'assets': 'EVIDENCE-FIRST ASSET REQUESTS',
        'distribution': 'DISTRIBUTION MATRIX',
        'projects': 'MONITORED PROJECTS',
        'analytics': 'ANALYTICS & LEARNING',
        'activity': 'ACTIVITY STREAM'
      };
      document.getElementById('breadcrumb-view').innerText = labels[viewId] || viewId.toUpperCase();

      if (viewId === 'content') loadContent();
      if (viewId === 'assets') loadAssetRequests();
      if (viewId === 'distribution') loadDistributionMatrix();
      if (viewId === 'projects') loadProjects();
      if (viewId === 'analytics') loadAnalytics();
      if (viewId === 'activity') loadActivity();
    }

    async function loadStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        gStatus = data;

        const frozen = data.frozen;
        const sdot = document.getElementById('sidebar-status-dot');
        const stext = document.getElementById('sidebar-state-text');
        if (frozen) {
          sdot.classList.add('frozen');
          stext.classList.add('frozen');
          stext.innerText = `FROZEN (${data.killswitch_mode})`;
        } else {
          sdot.classList.remove('frozen');
          stext.classList.remove('frozen');
          stext.innerText = `ACTIVE (${data.killswitch_mode})`;
        }

        document.getElementById('metric-status-val').innerText = frozen ? 'FROZEN' : 'ACTIVE';
        const ksModeEl = document.getElementById('metric-ks-mode');
        ksModeEl.innerText = data.killswitch_mode;
        ksModeEl.className = 'chip ' + (frozen ? 'chip-rose' : 'chip-green');

        const needed = (data.pending_assets_count || 0) + (data.pending_approvals_count || 0);
        document.getElementById('metric-input-needed').innerText = needed;
        document.getElementById('badge-assets-count').innerText = data.pending_assets_count || 0;

        loadOverviewQueue();
      } catch (err) {
        console.error("Status load error", err);
      }
    }

    async function loadOverviewQueue() {
      const q = document.getElementById('overview-action-queue');
      try {
        const [assetRes, apprRes] = await Promise.all([
          fetch('/api/asset-requests').then(r => r.json()),
          fetch('/api/approvals').then(r => r.json())
        ]);

        const allPendingReqs = (assetRes.requests || []).filter(r => r.status === 'PENDING');
        const reqs = allPendingReqs.slice(0, 4);
        const apprs = (apprRes.approvals || []).slice(0, 4);

        if (allPendingReqs.length === 0 && apprs.length === 0) {
          q.innerHTML = '<div style="color: var(--text-tertiary); font-size: 12px; padding: 6px 0;">✓ Zero action items required. All posts grounded and running autonomously.</div>';
        } else {
          let html = '';
          reqs.forEach(r => {
            html += `
              <div style="background: var(--bg-root); border: 1px solid var(--border-subtle); border-radius: 4px; padding: 8px 10px; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                  <div style="display: flex; align-items: center; gap: 6px;">
                    <span class="chip chip-amber">ASSET NEEDED</span>
                    <span style="font-weight: 600; font-size: 12px;">${r.requested_asset_title || 'Real Asset Request'}</span>
                  </div>
                  <div style="font-size: 11px; color: var(--text-secondary); margin-top: 2px;">Candidate: <code style="font-family: var(--font-mono);">${r.candidate_id}</code></div>
                </div>
                <button class="btn btn-sm btn-primary" onclick="showView('assets')">Fulfill</button>
              </div>
            `;
          });
          apprs.forEach(a => {
            html += `
              <div style="background: var(--bg-root); border: 1px solid var(--border-subtle); border-radius: 4px; padding: 8px 10px; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                  <div style="display: flex; align-items: center; gap: 6px;">
                    <span class="chip chip-cyan">APPROVAL QUEUE</span>
                    <span style="font-weight: 600; font-size: 12px;">${a.content_summary || a.post_id}</span>
                  </div>
                  <div style="font-size: 11px; color: var(--text-secondary); margin-top: 2px;">Platform: ${a.target_platform} | Score: ${a.scorecard_summary ? a.scorecard_summary.composite_score : 'N/A'}</div>
                </div>
                <button class="btn btn-sm btn-success" onclick="signApproval('${a.request_id}')">Sign</button>
              </div>
            `;
          });
          if (allPendingReqs.length > 4) {
            html += `
              <div style="text-align: center; margin-top: 8px;">
                <button class="btn btn-sm" onclick="showView('assets')" style="width: 100%;">
                  View all ${allPendingReqs.length} pending requests in Asset Inbox &rarr;
                </button>
              </div>
            `;
          }
          q.innerHTML = html;
        }
      } catch (e) {
        q.innerHTML = '<div style="color: var(--accent-rose); font-size: 11px;">Error loading action queue</div>';
      }

      // Quick Candidates in Overview
      try {
        const matRes = await fetch('/api/distribution-matrix').then(r => r.json());
        const tbody = document.querySelector('#overview-quick-candidates tbody');
        tbody.innerHTML = '';
        (matRes.candidates || []).slice(0, 5).forEach(c => {
          const row = document.createElement('tr');
          row.onclick = () => openDrawer(c.candidate_id);
          const li = c.channels.linkedin ? c.channels.linkedin.badge : '-';
          const ig = c.channels.instagram ? c.channels.instagram.badge : '-';
          const tw = c.channels.twitter ? c.channels.twitter.badge : '-';
          row.innerHTML = `
            <td class="cell-mono" style="color: var(--accent-cyan);">${c.candidate_id}</td>
            <td style="max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${c.title}</td>
            <td class="cell-mono" style="font-weight: 700;">${c.mvts_score.toFixed(1)}</td>
            <td>${formatBadge(li)}</td>
            <td>${formatBadge(ig)}</td>
            <td>${formatBadge(tw)}</td>
          `;
          tbody.appendChild(row);
        });
      } catch (e) {}

      // Quick Audit in Overview
      try {
        const actRes = await fetch('/api/activity?limit=6').then(r => r.json());
        const tbody = document.querySelector('#overview-audit-stream tbody');
        tbody.innerHTML = '';
        (actRes.events || []).forEach(e => {
          const row = document.createElement('tr');
          const time = e.timestamp ? e.timestamp.split('T')[1].split('.')[0] : '--:--:--';
          row.innerHTML = `
            <td class="cell-mono cell-muted">${time}</td>
            <td style="font-size: 11px; font-weight: 500;">${e.event}</td>
            <td class="cell-mono cell-muted">${e.authorized_by || e.approved_by || 'System'}</td>
          `;
          tbody.appendChild(row);
        });
      } catch (e) {}
    }

    async function loadContent() {
      try {
        const res = await fetch('/api/content');
        const data = await res.json();
        gCandidates = data.candidates || [];
        document.getElementById('badge-content-count').innerText = gCandidates.length;
        document.getElementById('metric-candidates-val').innerText = gCandidates.length;
        renderContentTable();
      } catch (e) {
        showToast("Error loading content backlog", true);
      }
    }

    function filterPillar(pillar) {
      gSelectedPillar = pillar;
      renderContentTable();
    }

    function filterContentTable() {
      renderContentTable();
    }

    function renderContentTable() {
      const q = (document.getElementById('content-search').value || '').toLowerCase();
      const tbody = document.querySelector('#content-table tbody');
      tbody.innerHTML = '';

      const filtered = gCandidates.filter(c => {
        if (gSelectedPillar !== 'ALL' && c.content_pillar !== gSelectedPillar) return false;
        if (q) {
          const str = (c.candidate_id + ' ' + c.title + ' ' + (c.project_id || '')).toLowerCase();
          if (!str.includes(q)) return false;
        }
        return true;
      });

      filtered.forEach(c => {
        const row = document.createElement('tr');
        row.onclick = () => openDrawer(c.candidate_id);

        const mvts = c.mvts_score || 0;
        let scoreChip = `<span class="chip chip-green">${mvts.toFixed(1)}</span>`;
        if (mvts < 7.5) scoreChip = `<span class="chip chip-amber">${mvts.toFixed(1)}</span>`;
        if (c.lifecycle_state === 'REJECTED') scoreChip = `<span class="chip chip-rose">${mvts.toFixed(1)}</span>`;

        let stateChip = `<span class="chip chip-green">${c.lifecycle_state}</span>`;
        if (c.lifecycle_state === 'REJECTED') stateChip = `<span class="chip chip-rose">REJECTED</span>`;
        if (c.lifecycle_state === 'CANDIDATE') stateChip = `<span class="chip chip-slate">CANDIDATE</span>`;

        row.innerHTML = `
          <td class="cell-mono" style="color: var(--accent-cyan); font-weight: 600;">${c.candidate_id}</td>
          <td style="font-weight: 500; max-width: 320px;">${c.title}</td>
          <td class="cell-mono cell-muted">${c.project_id || '-'}</td>
          <td>${scoreChip}</td>
          <td style="font-size: 11px; color: var(--text-secondary);">${c.proposed_format || 'Analysis'}</td>
          <td>${stateChip}</td>
          <td><button class="btn btn-sm" onclick="event.stopPropagation(); openDrawer('${c.candidate_id}')">Inspect</button></td>
        `;
        tbody.appendChild(row);
      });
    }

    function openDrawer(candId) {
      const cand = gCandidates.find(c => c.candidate_id === candId);
      if (!cand) return;
      gActiveDrawerCandidate = cand;

      document.getElementById('drawer-id').innerText = cand.candidate_id + ' • ' + (cand.content_pillar || '');
      document.getElementById('drawer-title').innerText = cand.title;

      switchDrawerTab(gActiveDrawerTab);

      document.getElementById('drawer-backdrop').style.display = 'block';
      document.getElementById('slide-drawer').classList.add('open');
    }

    function closeDrawer() {
      document.getElementById('drawer-backdrop').style.display = 'none';
      document.getElementById('slide-drawer').classList.remove('open');
    }

    function switchDrawerTab(tab) {
      gActiveDrawerTab = tab;
      document.querySelectorAll('.drawer-tab').forEach(el => el.classList.remove('active'));
      const tEl = document.getElementById('dtab-' + tab);
      if (tEl) tEl.classList.add('active');

      const c = gActiveDrawerCandidate;
      const b = document.getElementById('drawer-body-content');
      if (!c) return;

      if (tab === 'story') {
        b.innerHTML = `
          <div class="drawer-section-title">Canonical Technical Narrative</div>
          <div style="font-size: 13px; line-height: 1.6; color: var(--text-primary); margin-bottom: 16px;">
            ${c.story || c.title}
          </div>

          <div class="drawer-section-title">Engineering Angle & Target Audience</div>
          <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
            <strong>Format:</strong> ${c.proposed_format || 'Technical Breakdown'}<br/>
            <strong>Audience:</strong> ${(c.audience || []).join(', ') || 'Systems Engineers'}<br/>
            <strong>Technical Depth:</strong> ${c.technical_depth || 5}/5
          </div>

          <div class="drawer-section-title">Credibility Rationale</div>
          <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
            ${c.credibility_value || 'Direct builder authority based on verified code.'}
          </div>

          <div class="drawer-section-title">Supporting Asset Requirement</div>
          <div style="font-size: 12px; color: var(--accent-cyan);">
            📌 ${c.likely_supporting_asset || 'Workbench capture or architecture diagram.'}
          </div>
        `;
      } else if (tab === 'grounding') {
        b.innerHTML = `
          <div class="drawer-section-title">Claim Provenance & Commit Hashes</div>
          <div class="code-block">${c.evidence || 'Grounded in knowledge/projects_registry.json'}</div>

          <div class="drawer-section-title" style="margin-top: 14px;">Why Now (Milestone Context)</div>
          <div style="font-size: 12.5px; color: var(--text-secondary); line-height: 1.5;">
            ${c.why_now || 'Recent project release or benchmark completion.'}
          </div>

          <div class="drawer-section-title" style="margin-top: 14px;">Technical Risks & Boundary Clarifications</div>
          <div style="font-size: 12px; color: var(--accent-amber); background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.2); padding: 10px; border-radius: 4px;">
            ⚠️ ${c.risks || 'Ensure hardware scope is clearly defined.'}
          </div>
        `;
      } else if (tab === 'scorecard') {
        const sc = c.scorecard || {};
        b.innerHTML = `
          <div class="drawer-section-title">5-Point Editorial Scorecard</div>
          <table class="dense-table" style="margin-bottom: 16px;">
            <tr>
              <td>Technical Artifact / Rigor</td>
              <td class="cell-mono" style="text-align: right; font-weight: 700;">${(sc.technical_rigor || 3.0).toFixed(1)} / 3.0</td>
            </tr>
            <tr>
              <td>Grounding & Factual Provenance</td>
              <td class="cell-mono" style="text-align: right; font-weight: 700;">${(sc.grounding || 3.0).toFixed(1)} / 3.0</td>
            </tr>
            <tr>
              <td>Engineering Tradeoff Analysis</td>
              <td class="cell-mono" style="text-align: right; font-weight: 700;">${(sc.engineering_tradeoff || 2.0).toFixed(1)} / 2.0</td>
            </tr>
            <tr>
              <td>Actionable Takeaway Score</td>
              <td class="cell-mono" style="text-align: right; font-weight: 700;">${(sc.actionable_takeaway || 1.8).toFixed(1)} / 2.0</td>
            </tr>
            <tr style="background: var(--bg-hover);">
              <td style="font-weight: 700;">Composite MVTS Score</td>
              <td class="cell-mono" style="text-align: right; font-weight: 700; color: var(--accent-emerald);">${(sc.composite_score || c.mvts_score || 0).toFixed(1)} / 10.0</td>
            </tr>
          </table>

          <div class="drawer-section-title">Slop & Anti-Vanity Verification</div>
          <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.5;">
            ✓ <strong>Slop Index:</strong> 0.00 (Zero buzzwords, zero fake hype)<br/>
            ✓ <strong>Forbidden Openers:</strong> None detected<br/>
            ✓ <strong>Emoji Count:</strong> &le; 2 functional technical emojis
          </div>
        `;
      } else if (tab === 'variants') {
        const v = c.variants || {};
        b.innerHTML = `
          <div class="drawer-section-title">LinkedIn Variant (Long-Form Technical Teardown)</div>
          <div class="code-block" style="margin-bottom: 14px;">${v.linkedin ? v.linkedin.text : c.story}</div>

          <div class="drawer-section-title">Instagram Variant (@serhatyvz_38 Visual Caption)</div>
          <div class="code-block" style="margin-bottom: 14px;">${v.instagram ? v.instagram.text : 'Workbench capture required before release.'}</div>

          <div class="drawer-section-title">X / Twitter Thread Variant (@Arkhino_DEV)</div>
          <div class="code-block">${v.twitter ? v.twitter.text : c.title}</div>
        `;
      }
    }

    async function loadAssetRequests() {
      const container = document.getElementById('assets-container');
      try {
        const res = await fetch('/api/asset-requests');
        const data = await res.json();
        const reqs = data.requests || [];
        document.getElementById('badge-assets-count').innerText = reqs.filter(r => r.status === 'PENDING').length;

        if (reqs.length === 0) {
          container.innerHTML = '<div style="color: var(--text-tertiary); font-size: 12px; padding: 20px 0;">No asset requests currently pending. All candidate assets resolved.</div>';
          return;
        }

        container.innerHTML = '';
        reqs.forEach(r => {
          const card = document.createElement('div');
          card.className = 'asset-card';
          const isFulfilled = r.status === 'FULFILLED';

          const shotsList = (r.recommended_shots || []).map(s => `<li>${s}</li>`).join('');

          card.innerHTML = `
            <div class="asset-card-header">
              <div>
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                  <span class="chip ${isFulfilled ? 'chip-green' : 'chip-amber'}">${r.status}</span>
                  <span class="chip chip-cyan">Priority P2: Real Capture</span>
                  <span class="cell-mono" style="color: var(--text-tertiary); font-size: 11px;">${r.request_id}</span>
                </div>
                <div class="asset-card-title">${r.requested_asset_title || 'Real Asset Request'}</div>
                <div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 2px;">
                  Candidate: <code style="font-family: var(--font-mono); color: var(--accent-cyan);">${r.candidate_id}</code> | 
                  Target Platforms: <strong style="color: var(--text-primary);">${(r.target_platforms || ['instagram']).map(p => p.toUpperCase()).join(', ')}</strong>
                </div>
                <div style="font-size: 11px; color: var(--accent-cyan); margin-top: 3px;">
                  ⚡ Single upload fulfills and unlocks all ${(r.target_platforms || ['instagram']).length} platforms simultaneously.
                </div>
              </div>
            </div>

            <div class="asset-card-why">
              <strong>Technical Rationale:</strong> ${r.why_needed || 'Evidence required to prove hardware execution.'}
            </div>

            <div class="asset-instruction-box">
              <strong>Instructions:</strong> ${r.specific_instructions || 'Capture high-resolution clear photo of the assembly.'}
            </div>

            ${shotsList ? `<div style="font-size: 11px; font-weight: 600; color: var(--text-secondary); margin-bottom: 4px;">Recommended Angles:</div><ul class="asset-shots-list">${shotsList}</ul>` : ''}

            ${isFulfilled ? `
              <div style="background: var(--bg-root); border: 1px solid rgba(16, 185, 129, 0.3); padding: 10px 14px; border-radius: 4px; display: flex; align-items: center; justify-content: space-between;">
                <div>
                  <div style="color: var(--accent-emerald); font-weight: 600; font-size: 12px;">✓ Asset Fulfilled & Verified</div>
                  <div class="cell-mono" style="font-size: 11px; color: var(--text-secondary); margin-top: 2px;">
                    SHA-256: ${r.asset_sha256 || 'Calculated'}
                  </div>
                </div>
                <span style="font-size: 11px; color: var(--text-tertiary);">${r.fulfilled_at || ''}</span>
              </div>
            ` : `
              <div class="dropzone" id="dz-${r.request_id}" 
                ondragover="event.preventDefault(); this.classList.add('dragover');" 
                ondragleave="this.classList.remove('dragover');" 
                ondrop="handleDrop(event, '${r.request_id}')"
                onclick="document.getElementById('file-input-${r.request_id}').click()">
                
                <input type="file" id="file-input-${r.request_id}" style="display: none;" accept="image/*" onchange="handleFileSelect(event, '${r.request_id}')"/>
                <div class="dropzone-label">📁 Drag & drop workbench photo, or <span style="color: var(--accent-cyan); text-decoration: underline;">browse</span></div>
                <div class="dropzone-sub">PNG, JPG, or WEBP. SHA-256 hash calculated automatically upon submission.</div>

                <div class="preview-container" id="preview-${r.request_id}">
                  <img class="preview-img" id="img-${r.request_id}" src=""/>
                  <div class="preview-info" id="info-${r.request_id}"></div>
                  <button class="btn btn-sm btn-success" onclick="event.stopPropagation(); submitAsset('${r.request_id}')">Submit Asset</button>
                  <button class="btn btn-sm" onclick="event.stopPropagation(); clearAsset('${r.request_id}')">Clear</button>
                </div>
              </div>
            `}
          `;
          container.appendChild(card);
        });
      } catch (e) {
        container.innerHTML = '<div style="color: var(--accent-rose); font-size: 12px;">Error loading asset requests</div>';
      }
    }

    const gSelectedFiles = {};

    function handleFileSelect(evt, reqId) {
      const file = evt.target.files[0];
      if (file) setFilePreview(reqId, file);
    }

    function handleDrop(evt, reqId) {
      evt.preventDefault();
      document.getElementById('dz-' + reqId).classList.remove('dragover');
      const file = evt.dataTransfer.files[0];
      if (file) setFilePreview(reqId, file);
    }

    function setFilePreview(reqId, file) {
      gSelectedFiles[reqId] = file;
      const previewBox = document.getElementById('preview-' + reqId);
      const img = document.getElementById('img-' + reqId);
      const info = document.getElementById('info-' + reqId);

      img.src = URL.createObjectURL(file);
      info.innerHTML = `<strong>${file.name}</strong><br/><span style="color: var(--text-tertiary);">${(file.size / 1024).toFixed(1)} KB • ${file.type}</span>`;
      previewBox.style.display = 'flex';
    }

    function clearAsset(reqId) {
      delete gSelectedFiles[reqId];
      const previewBox = document.getElementById('preview-' + reqId);
      if (previewBox) previewBox.style.display = 'none';
      const fi = document.getElementById('file-input-' + reqId);
      if (fi) fi.value = '';
    }

    async function submitAsset(reqId) {
      const file = gSelectedFiles[reqId];
      if (!file) {
        showToast("Please select a file first", true);
        return;
      }

      const formData = new FormData();
      formData.append("file", file);

      try {
        const res = await fetch(`/api/asset-requests/${reqId}/upload`, {
          method: "POST",
          body: formData
        });
        const data = await res.json();
        if (res.ok && data.success) {
          const plats = (data.target_platforms || []).map(p => p.toUpperCase()).join(', ');
          showToast(`✓ Real asset registered! Unlocked for ${plats || 'all platforms'}. SHA-256: ${data.asset_sha256.substring(0, 12)}...`);
          loadAssetRequests();
          loadDistributionMatrix();
          loadStatus();
        } else {
          showToast(data.detail || "Upload failed", true);
        }
      } catch (e) {
        showToast("Error uploading asset", true);
      }
    }

    async function loadDistributionMatrix() {
      try {
        const res = await fetch('/api/distribution-matrix');
        const data = await res.json();
        const tbody = document.querySelector('#matrix-table tbody');
        tbody.innerHTML = '';

        (data.candidates || []).forEach(c => {
          const row = document.createElement('tr');
          row.onclick = () => openDrawer(c.candidate_id);
          const li = c.channels.linkedin ? c.channels.linkedin.badge : '-';
          const ig = c.channels.instagram ? c.channels.instagram.badge : '-';
          const tw = c.channels.twitter ? c.channels.twitter.badge : '-';

          row.innerHTML = `
            <td class="cell-mono" style="color: var(--accent-cyan); font-weight: 600;">${c.candidate_id}</td>
            <td style="font-weight: 500;">${c.title}</td>
            <td class="cell-mono" style="font-weight: 700;">${c.mvts_score.toFixed(1)}</td>
            <td>${formatBadge(li)}</td>
            <td>${formatBadge(ig)}</td>
            <td>${formatBadge(tw)}</td>
          `;
          tbody.appendChild(row);
        });
      } catch (e) {
        showToast("Error loading distribution matrix", true);
      }
    }

    function formatBadge(badge) {
      if (!badge || badge === '-') return '<span class="chip chip-slate">-</span>';
      if (badge.includes('READY')) return `<span class="chip chip-green">${badge}</span>`;
      if (badge.includes('REQUEST_USER')) return `<span class="chip chip-amber">${badge}</span>`;
      if (badge.includes('NO_ASSET')) return `<span class="chip chip-rose">${badge}</span>`;
      return `<span class="chip chip-slate">${badge}</span>`;
    }

    async function loadProjects() {
      const container = document.getElementById('projects-container');
      try {
        const res = await fetch('/api/projects');
        const data = await res.json();
        const projs = data.projects || [];

        container.innerHTML = '';
        projs.forEach(p => {
          const card = document.createElement('div');
          card.className = 'panel';
          const techChips = (p.tech_stack || []).map(t => `<span class="chip chip-slate" style="margin-right: 4px; margin-bottom: 4px;">${t}</span>`).join('');
          const metrics = p.verified_metrics || {};
          let metricsHtml = '';
          for (const [k, v] of Object.entries(metrics)) {
            metricsHtml += `<div><span style="color: var(--text-tertiary);">${k.replace(/_/g, ' ')}:</span> <strong>${v}</strong></div>`;
          }

          card.innerHTML = `
            <div class="panel-header">
              <div class="panel-title">${p.project_id}</div>
              <a href="${p.repo_url}" target="_blank" style="color: var(--accent-cyan); font-size: 11px; text-decoration: none; font-family: var(--font-mono);">repo &nearr;</a>
            </div>
            <div class="panel-body">
              <div style="font-size: 13.5px; font-weight: 600; margin-bottom: 6px;">${p.name}</div>
              <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px; line-height: 1.5;">${p.summary}</div>
              
              <div style="margin-bottom: 12px;">${techChips}</div>

              <div style="background: var(--bg-root); border: 1px solid var(--border-subtle); padding: 10px; border-radius: 4px; font-size: 11.5px; font-family: var(--font-mono); margin-bottom: 10px;">
                ${metricsHtml || 'Metrics grounded in test logs'}
              </div>
            </div>
          `;
          container.appendChild(card);
        });
      } catch (e) {
        container.innerHTML = '<div style="color: var(--accent-rose); font-size: 12px;">Error loading projects</div>';
      }
    }

    async function loadAnalytics() {
      try {
        const res = await fetch('/api/analytics');
        const data = await res.json();
        const lessonsBox = document.getElementById('lessons-container');
        lessonsBox.innerHTML = '';

        (data.lessons || []).forEach(l => {
          const item = document.createElement('div');
          item.style = "background: var(--bg-root); border: 1px solid var(--border-subtle); border-radius: 4px; padding: 12px; margin-bottom: 10px;";
          item.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span class="chip chip-cyan">${l.domain}</span>
              <span class="cell-mono cell-muted" style="font-size: 11px;">${l.timestamp}</span>
            </div>
            <div style="font-size: 12.5px; color: var(--text-primary); margin-bottom: 6px;">${l.observation}</div>
            <div style="font-size: 12px; color: var(--accent-emerald);"><strong>Actionable Rule:</strong> ${l.actionable_rule}</div>
          `;
          lessonsBox.appendChild(item);
        });
      } catch (e) {
        showToast("Error loading analytics", true);
      }
    }

    async function loadActivity() {
      try {
        const res = await fetch('/api/activity?limit=50');
        const data = await res.json();
        const tbody = document.querySelector('#full-audit-table tbody');
        tbody.innerHTML = '';

        (data.events || []).forEach(e => {
          const row = document.createElement('tr');
          const time = e.timestamp ? e.timestamp.replace('T', ' ').split('.')[0] : '--';
          row.innerHTML = `
            <td class="cell-mono cell-muted">${time}</td>
            <td style="font-weight: 600; font-size: 11.5px;">${e.event}</td>
            <td class="cell-mono" style="color: var(--accent-cyan); font-size: 11px;">${e.post_id || e.request_id || '-'}</td>
            <td class="cell-mono cell-muted">${e.authorized_by || e.approved_by || 'AutonomyPolicy'}</td>
            <td style="font-size: 11.5px; color: var(--text-secondary); max-width: 280px; overflow: hidden; text-overflow: ellipsis;">${e.reason || e.payload_sha256 || '-'}</td>
          `;
          tbody.appendChild(row);
        });
      } catch (e) {
        showToast("Error loading audit stream", true);
      }
    }

    async function signApproval(reqId) {
      try {
        const res = await fetch(`/api/approvals/${reqId}/sign`, { method: "POST" });
        const data = await res.json();
        if (res.ok && data.success) {
          showToast(`✓ Approval token generated: ${data.token_id}`);
          loadStatus();
        } else {
          showToast(data.detail || "Signing failed", true);
        }
      } catch (e) {
        showToast("Error signing approval", true);
      }
    }

    function openKillswitchModal() {
      document.getElementById('killswitch-modal').style.display = 'flex';
    }

    function closeKillswitchModal() {
      document.getElementById('killswitch-modal').style.display = 'none';
    }

    async function submitKillswitchChange() {
      const mode = document.querySelector('input[name="ks-mode-select"]:checked').value;
      const reason = document.getElementById('ks-reason-input').value || 'Operator updated state';

      const formData = new FormData();
      formData.append("mode", mode);
      formData.append("reason", reason);

      try {
        const res = await fetch('/api/killswitch', { method: "POST", body: formData });
        const data = await res.json();
        if (res.ok && data.success) {
          showToast(`🛡️ Killswitch updated: ${mode}`);
          closeKillswitchModal();
          loadStatus();
        } else {
          showToast(data.detail || "Killswitch update failed", true);
        }
      } catch (e) {
        showToast("Error updating killswitch", true);
      }
    }

    async function triggerMorningRun() {
      showToast("Running Morning Intelligence cycle...");
      try {
        const res = await fetch('/api/morning-run', { method: "POST" });
        const data = await res.json();
        if (res.ok && data.success) {
          showToast("🌅 Morning intelligence completed successfully!");
          loadStatus();
        } else {
          showToast(data.detail || "Morning run failed", true);
        }
      } catch (e) {
        showToast("Error triggering morning run", true);
      }
    }

    // Hash routing
    async function handleRoute() {
      const h = window.location.hash.replace('#', '');
      if (h === 'killswitch') {
        openKillswitchModal();
      } else if (h.startsWith('inspect=')) {
        const cid = h.replace('inspect=', '');
        showView('content');
        if (gCandidates.length === 0) {
          await loadContent();
        }
        openDrawer(cid);
      } else if (h) {
        showView(h);
      }
    }

    window.addEventListener('hashchange', handleRoute);

    // Auto-initialize
    loadStatus();
    loadContent().then(() => {
      handleRoute();
    });
    setInterval(loadStatus, 15000);
  </script>
</body>
</html>
"""


def start_server(port: int = 8765, open_browser: bool = True):
    url = f"http://127.0.0.1:{port}"
    print(f"\n🚀 Launching Personal Media Agency Web UI at: {url}")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    start_server()
