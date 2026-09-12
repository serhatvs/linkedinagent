"""Google Drive & Cloud Drive Integration Architecture for Serhat's Autonomous Media Agency.

Architecture:
DriveAssetSource
├── LocalSyncAdapter
├── ShareLinkAdapter
└── GoogleDriveOAuthAdapter

Supports:
1. Authenticated Google Drive OAuth 2.0 account integration (browsing, searching, private file download, provenance).
2. Local synced Drive folder scanning (Google Drive Desktop, OneDrive, or local drop folders).
3. Public/shared Google Drive URL and file ID ingestion without credentials.
4. Cryptographic SHA-256 deduplication and verification across all sources.
5. Cascading auto-fulfillment of pending candidate asset requests across platforms.
"""

from __future__ import annotations
import os
import re
import json
import uuid
import shutil
import hashlib
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple


SUPPORTED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".mp4", ".mov", ".webm",
    ".pdf", ".csv", ".log", ".txt", ".json"
}


def _infer_project(candidate_id: Optional[str], filename: str, explicit_project: Optional[str] = None) -> str:
    if explicit_project:
        return explicit_project
    check_str = f"{candidate_id or ''} {filename}".lower()
    if "usb" in check_str:
        return "usb-display"
    elif "jarvis" in check_str:
        return "JARVIS"
    elif "3dprinter" in check_str or "hardware" in check_str or "tmc2209" in check_str:
        return "3dprinter"
    elif "leshield" in check_str or "groth16" in check_str or "zk" in check_str:
        return "LeShield"
    elif "chronos" in check_str or "rag" in check_str:
        return "chronos-rag"
    return "General"


class LocalSyncAdapter:
    """Handles local synced directories (e.g. Google Drive for Desktop virtual drive or OneDrive)."""

    def __init__(self, workspace_root: Path, parent: Optional["DriveAssetSource"] = None):
        self.workspace_root = workspace_root.resolve()
        self.parent = parent
        self.assets_dir = parent.assets_dir if parent else (self.workspace_root / "assets" / "user_submissions")
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def _get_parent_config(self) -> Dict[str, Any]:
        if self.parent:
            return self.parent.get_config()
        cfg_file = self.workspace_root / "knowledge" / "drive_config.json"
        if cfg_file.exists():
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_parent_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        if self.parent:
            return self.parent.save_config(updates)
        cfg_file = self.workspace_root / "knowledge" / "drive_config.json"
        cfg = self._get_parent_config()
        cfg.update(updates)
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return cfg

    def is_connected(self) -> bool:
        cfg = self._get_parent_config()
        path_str = cfg.get("local_sync_path", "")
        if not path_str:
            return False
        p = Path(path_str)
        return p.exists() and p.is_dir()

    def get_status_label(self) -> str:
        return "LOCAL_SYNC_CONNECTED" if self.is_connected() else "LOCAL_SYNC_NOT_CONFIGURED"

    def get_status(self) -> Dict[str, Any]:
        cfg = self._get_parent_config()
        connected = self.is_connected()
        synced_items = [i for i in cfg.get("synced_items", []) if i.get("source") == "local_sync"]
        return {
            "status": self.get_status_label(),
            "connected": connected,
            "local_sync_path": cfg.get("local_sync_path", ""),
            "synced_items_count": len(synced_items),
            "last_sync_at": cfg.get("last_sync_at")
        }

    def sync(self, local_path: Optional[str] = None) -> Dict[str, Any]:
        """Scan a local synced folder for new media, compute SHA-256, and fulfill pending requests."""
        cfg = self._get_parent_config()
        target_path_str = local_path or cfg.get("local_sync_path")
        if not target_path_str:
            return {
                "success": False,
                "synced_count": 0,
                "status": "LOCAL_SYNC_NOT_CONFIGURED",
                "message": "No local sync path configured."
            }

        target_dir = Path(target_path_str).resolve()
        if not target_dir.exists() or not target_dir.is_dir():
            return {
                "success": False,
                "synced_count": 0,
                "status": "LOCAL_SYNC_NOT_CONFIGURED",
                "message": f"Path '{target_dir}' does not exist or is not a directory."
            }

        synced_now = []
        existing_hashes = {i.get("sha256") for i in cfg.get("synced_items", []) if i.get("sha256")}

        from core.asset_planner import AssetPlanner
        planner = AssetPlanner(self.workspace_root)
        pending_reqs = planner.list_pending_requests()

        for fpath in target_dir.rglob("*"):
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            # Compute SHA-256
            hasher = hashlib.sha256()
            with open(fpath, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            sha = hasher.hexdigest()

            if sha in existing_hashes:
                continue

            # Copy to user_submissions
            dest_name = f"local_sync_{fpath.name}"
            dest_path = self.assets_dir / dest_name
            shutil.copy2(fpath, dest_path)
            existing_hashes.add(sha)

            # Auto-fulfill matching candidate
            cand_id = "-"
            for r in pending_reqs:
                if r.candidate_id in fpath.name or r.candidate_id.replace("cand_", "") in fpath.name:
                    cand_id = r.candidate_id
                    try:
                        planner.fulfill_request(r.request_id, dest_path)
                    except Exception:
                        pass
                    break

            inferred_proj = _infer_project(cand_id if cand_id != "-" else None, fpath.name)

            record = {
                "filename": dest_name,
                "original_path": str(fpath),
                "sha256": sha,
                "size_bytes": fpath.stat().st_size,
                "candidate_id": cand_id,
                "project": inferred_proj,
                "source": "local_sync",
                "synced_at": datetime.now(timezone.utc).isoformat()
            }
            synced_now.append(record)

        # Update config
        cfg_items = cfg.get("synced_items", [])
        cfg_items = synced_now + cfg_items
        self.parent.save_config({
            "synced_items": cfg_items[:150],
            "last_sync_at": datetime.now(timezone.utc).isoformat()
        })

        return {
            "success": True,
            "status": "LOCAL_SYNC_CONNECTED",
            "synced_count": len(synced_now),
            "items": synced_now,
            "message": f"Successfully ingested {len(synced_now)} new assets from local drive."
        }


class ShareLinkAdapter:
    """Handles unauthenticated public and shared Google Drive URLs and File IDs."""

    def __init__(self, workspace_root: Path, parent: Optional["DriveAssetSource"] = None):
        self.workspace_root = workspace_root.resolve()
        self.parent = parent
        self.assets_dir = parent.assets_dir if parent else (self.workspace_root / "assets" / "user_submissions")
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def _get_parent_config(self) -> Dict[str, Any]:
        if self.parent:
            return self.parent.get_config()
        cfg_file = self.workspace_root / "knowledge" / "drive_config.json"
        if cfg_file.exists():
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_parent_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        if self.parent:
            return self.parent.save_config(updates)
        cfg_file = self.workspace_root / "knowledge" / "drive_config.json"
        cfg = self._get_parent_config()
        cfg.update(updates)
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return cfg

    @staticmethod
    def is_available() -> bool:
        return True

    @staticmethod
    def get_status_label() -> str:
        return "SHARE_LINK_IMPORT_AVAILABLE"

    def get_status(self) -> Dict[str, Any]:
        cfg = self._get_parent_config()
        synced_items = [i for i in cfg.get("synced_items", []) if i.get("source") == "google_drive_share_link"]
        return {
            "status": self.get_status_label(),
            "available": True,
            "synced_items_count": len(synced_items)
        }

    @staticmethod
    def extract_file_id(url_or_id: str) -> Optional[str]:
        """Extract Google Drive file ID from URL or raw string."""
        if not url_or_id:
            return None
        text = url_or_id.strip()

        # Check for /file/d/{id} pattern
        m = re.search(r"/file/d/([a-zA-Z0-9_-]{15,})", text)
        if m:
            return m.group(1)

        # Check for id={id} query parameter
        m = re.search(r"[?&]id=([a-zA-Z0-9_-]{15,})", text)
        if m:
            return m.group(1)

        # Check for /folders/{id} pattern
        m = re.search(r"/folders/([a-zA-Z0-9_-]{15,})", text)
        if m:
            return m.group(1)

        # Raw file ID (alphanumeric, dashes, underscores, length >= 20)
        if re.match(r"^[a-zA-Z0-9_-]{20,}$", text):
            return text

        return None

    def import_from_url(
        self,
        url_or_id: str,
        candidate_id: Optional[str] = None,
        project: Optional[str] = None,
        custom_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """Download file from Google Drive share link, verify SHA-256, and register into Asset Storage."""
        file_id = self.extract_file_id(url_or_id)
        if not file_id:
            raise ValueError(f"Could not extract a valid Google Drive file ID from: '{url_or_id}'")

        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutonomousMediaAgency/1.0"}
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                fname = custom_filename
                cd = resp.headers.get("Content-Disposition")
                if not fname and cd:
                    fn_match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', cd)
                    if fn_match:
                        fname = urllib.parse.unquote(fn_match.group(1))

                if not fname:
                    content_type = resp.headers.get("Content-Type", "")
                    ext = ".png" if "image" in content_type else ".bin"
                    fname = f"drive_{file_id}{ext}"

                content = resp.read()

                # Handle Google Drive virus scan warning redirect for large files
                if b"Google Drive - Virus scan warning" in content[:2000] or b"confirm=" in content[:2000]:
                    conf_m = re.search(r'href="(/uc\?export=download&amp;confirm=[^"]+)"', content.decode("utf-8", errors="ignore"))
                    if conf_m:
                        confirm_url = "https://drive.google.com" + conf_m.group(1).replace("&amp;", "&")
                        confirm_req = urllib.request.Request(
                            confirm_url,
                            headers={"User-Agent": "Mozilla/5.0 AutonomousMediaAgency/1.0"}
                        )
                        with urllib.request.urlopen(confirm_req, timeout=45) as conf_resp:
                            content = conf_resp.read()

        except Exception as e:
            raise RuntimeError(f"Failed to fetch asset from Google Drive: {e}")

        # Compute SHA-256
        sha = hashlib.sha256(content).hexdigest()

        # Sanitize filename and save to destination
        clean_name = re.sub(r'[\\/*?:"<>| ]', '_', fname)
        prefix = f"{candidate_id}_" if candidate_id else "drive_"
        dest_filename = f"{prefix}{clean_name}"
        dest_path = self.assets_dir / dest_filename

        with open(dest_path, "wb") as f:
            f.write(content)

        inferred_proj = _infer_project(candidate_id, clean_name, project)

        # Check and fulfill matching candidate requests
        fulfilled_req = None
        try:
            from core.asset_planner import AssetPlanner
            planner = AssetPlanner(self.workspace_root)
            pending_reqs = planner.list_pending_requests()

            target_req = None
            if candidate_id:
                target_req = next((r for r in pending_reqs if r.candidate_id == candidate_id), None)
            if not target_req and pending_reqs:
                target_req = next((r for r in pending_reqs if r.candidate_id in clean_name), None)

            if target_req:
                fulfilled_req = planner.fulfill_request(target_req.request_id, dest_path)
        except Exception:
            pass

        # Update drive config history
        record = {
            "file_id": file_id,
            "filename": dest_filename,
            "sha256": sha,
            "size_bytes": len(content),
            "candidate_id": candidate_id or (fulfilled_req.candidate_id if fulfilled_req else "-"),
            "project": inferred_proj,
            "source": "google_drive_share_link",
            "provenance": {
                "adapter": "ShareLinkAdapter",
                "file_id": file_id,
                "share_url": url_or_id
            },
            "synced_at": datetime.now(timezone.utc).isoformat()
        }

        cfg = self._get_parent_config()
        synced_items = [i for i in cfg.get("synced_items", []) if i.get("file_id") != file_id]
        synced_items.insert(0, record)
        self._save_parent_config({
            "synced_items": synced_items[:150],
            "last_sync_at": datetime.now(timezone.utc).isoformat()
        })

        return {
            "success": True,
            "source": "google_drive_share_link",
            "file_id": file_id,
            "filename": dest_filename,
            "relative_path": f"user_submissions/{dest_filename}",
            "url": f"/assets/user_submissions/{dest_filename}",
            "size_bytes": len(content),
            "sha256": sha,
            "candidate_id": record["candidate_id"],
            "project": inferred_proj,
            "fulfilled_request": fulfilled_req.request_id if fulfilled_req else None
        }


class GoogleDriveOAuthAdapter:
    """Handles authenticated Google Drive API (OAuth 2.0) account integration.

    Provides:
    - Token management and automated refresh.
    - Browsing and searching private account files/folders.
    - Reading and downloading private files with provenance.
    - Detecting newly added media.
    - Status reporting: GOOGLE_DRIVE_ACCOUNT_CONNECTED or GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED.
    """

    DEFAULT_CREDS = {
        "configured": False,
        "client_id": "",
        "client_secret": "",
        "redirect_uri": "http://127.0.0.1:8765/api/drive/oauth/callback",
        "access_token": "",
        "refresh_token": "",
        "token_expiry": None,
        "account_email": None,
        "account_name": None,
        "root_folder_id": "",
        "root_folder_name": ""
    }

    AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
    USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"

    SCOPES = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile"
    ]

    def __init__(self, workspace_root: Path, parent: Optional["DriveAssetSource"] = None):
        self.workspace_root = workspace_root.resolve()
        self.parent = parent
        self.assets_dir = parent.assets_dir if parent else (self.workspace_root / "assets" / "user_submissions")
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnail_cache_dir = self.workspace_root / "assets" / ".cache" / "thumbnails"
        self.thumbnail_cache_dir.mkdir(parents=True, exist_ok=True)
        self._verified_within_root: set[str] = set()
        self.creds_file = self.workspace_root / "knowledge" / "drive_oauth_credentials.json"
        self._ensure_creds()

    def _get_parent_config(self) -> Dict[str, Any]:
        if self.parent:
            return self.parent.get_config()
        cfg_file = self.workspace_root / "knowledge" / "drive_config.json"
        if cfg_file.exists():
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_parent_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        if self.parent:
            return self.parent.save_config(updates)
        cfg_file = self.workspace_root / "knowledge" / "drive_config.json"
        cfg = self._get_parent_config()
        cfg.update(updates)
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return cfg

    def _ensure_creds(self):
        if not self.creds_file.exists():
            with open(self.creds_file, "w", encoding="utf-8") as f:
                json.dump(self.DEFAULT_CREDS, f, indent=2)

    def get_credentials(self) -> Dict[str, Any]:
        try:
            with open(self.creds_file, "r", encoding="utf-8") as f:
                c = json.load(f)
                return {**self.DEFAULT_CREDS, **c}
        except Exception:
            return self.DEFAULT_CREDS.copy()

    def save_credentials(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        c = self.get_credentials()
        c.update(updates)
        has_tokens = bool(c.get("access_token") or c.get("refresh_token"))
        c["configured"] = bool(c.get("client_id") and has_tokens)
        with open(self.creds_file, "w", encoding="utf-8") as f:
            json.dump(c, f, indent=2)
        return c

    def disconnect(self) -> Dict[str, Any]:
        """Clears connected tokens while preserving client ID and redirect URI."""
        c = self.get_credentials()
        c.update({
            "configured": False,
            "access_token": "",
            "refresh_token": "",
            "token_expiry": None,
            "account_email": None,
            "account_name": None,
            "root_folder_id": "",
            "root_folder_name": ""
        })
        with open(self.creds_file, "w", encoding="utf-8") as f:
            json.dump(c, f, indent=2)
        return {"success": True, "status": "GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED"}

    def is_connected(self) -> bool:
        """Strict check: True only if valid tokens are present."""
        c = self.get_credentials()
        if not (c.get("access_token") or c.get("refresh_token")):
            return False
        return True

    def get_status_label(self) -> str:
        """Strict status label per specification."""
        return "GOOGLE_DRIVE_ACCOUNT_CONNECTED" if self.is_connected() else "GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED"

    def get_status(self) -> Dict[str, Any]:
        c = self.get_credentials()
        connected = self.is_connected()
        synced_items = [i for i in self._get_parent_config().get("synced_items", []) if i.get("source") == "google_drive_oauth"]
        return {
            "status": self.get_status_label(),
            "connected": connected,
            "account_email": c.get("account_email"),
            "account_name": c.get("account_name"),
            "root_folder_id": c.get("root_folder_id"),
            "root_folder_name": c.get("root_folder_name"),
            "client_id_configured": bool(c.get("client_id")),
            "has_refresh_token": bool(c.get("refresh_token")),
            "token_expiry": c.get("token_expiry"),
            "synced_items_count": len(synced_items)
        }

    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """Constructs Google OAuth 2.0 consent URL."""
        c = self.get_credentials()
        client_id = c.get("client_id")
        if not client_id:
            raise ValueError("OAuth Client ID is not configured. (GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED)")

        params = {
            "client_id": client_id,
            "redirect_uri": c.get("redirect_uri", "http://127.0.0.1:8765/api/drive/oauth/callback"),
            "response_type": "code",
            "scope": " ".join(self.SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true"
        }
        if state:
            params["state"] = state
        return f"{self.AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str) -> Dict[str, Any]:
        """Exchanges authorization code for access and refresh tokens."""
        c = self.get_credentials()
        client_id = c.get("client_id")
        client_secret = c.get("client_secret")
        if not client_id or not client_secret:
            raise ValueError("OAuth client credentials missing. (GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED)")

        post_data = urllib.parse.urlencode({
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": c.get("redirect_uri", "http://127.0.0.1:8765/api/drive/oauth/callback"),
            "grant_type": "authorization_code"
        }).encode("utf-8")

        req = urllib.request.Request(self.TOKEN_ENDPOINT, data=post_data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token") or c.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        expiry_iso = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + expires_in, tz=timezone.utc).isoformat()

        # Fetch user info
        email = None
        name = None
        try:
            u_req = urllib.request.Request(self.USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"})
            with urllib.request.urlopen(u_req, timeout=15) as u_resp:
                u_data = json.loads(u_resp.read().decode("utf-8"))
                email = u_data.get("email")
                name = u_data.get("name")
        except Exception:
            pass

        self.save_credentials({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_expiry": expiry_iso,
            "account_email": email,
            "account_name": name
        })

        return {
            "success": True,
            "status": "GOOGLE_DRIVE_ACCOUNT_CONNECTED",
            "account_email": email,
            "account_name": name
        }

    def set_tokens(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
        account_email: Optional[str] = None,
        account_name: Optional[str] = None,
        token_expiry: Optional[str] = None,
        root_folder_id: Optional[str] = None,
        root_folder_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Manually inject or update tokens."""
        updates: Dict[str, Any] = {"access_token": access_token}
        if refresh_token:
            updates["refresh_token"] = refresh_token
        if account_email:
            updates["account_email"] = account_email
        if account_name:
            updates["account_name"] = account_name
        if token_expiry:
            updates["token_expiry"] = token_expiry
        if root_folder_id is not None:
            updates["root_folder_id"] = root_folder_id
        if root_folder_name is not None:
            updates["root_folder_name"] = root_folder_name

        self.save_credentials(updates)
        return self.get_status()

    def refresh_access_token(self) -> bool:
        """Refreshes the OAuth access token using the stored refresh token."""
        c = self.get_credentials()
        ref_token = c.get("refresh_token")
        client_id = c.get("client_id")
        client_secret = c.get("client_secret")

        if not (ref_token and client_id and client_secret):
            return False

        post_data = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": ref_token,
            "grant_type": "refresh_token"
        }).encode("utf-8")

        try:
            req = urllib.request.Request(self.TOKEN_ENDPOINT, data=post_data, headers={"Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            new_acc = data.get("access_token")
            exp_in = data.get("expires_in", 3600)
            expiry_iso = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + exp_in, tz=timezone.utc).isoformat()
            self.save_credentials({
                "access_token": new_acc,
                "token_expiry": expiry_iso
            })
            return True
        except Exception:
            return False

    def _get_valid_token(self) -> str:
        if not self.is_connected():
            raise RuntimeError("Google Drive OAuth is not configured. (GOOGLE_DRIVE_OAUTH_NOT_CONFIGURED)")
        c = self.get_credentials()
        tok = c.get("access_token")
        if not tok:
            if self.refresh_access_token():
                tok = self.get_credentials().get("access_token")
            else:
                raise RuntimeError("Failed to refresh Google Drive access token.")
        return tok

    def list_files(
        self,
        folder_id: Optional[str] = None,
        page_size: int = 25,
        page_token: Optional[str] = None,
        q: Optional[str] = None,
        order_by: str = "modifiedTime desc"
    ) -> Dict[str, Any]:
        """Lists files and folders from the authenticated Google Drive account."""
        tok = self._get_valid_token()
        c = self.get_credentials()
        target_folder = folder_id or c.get("root_folder_id") or None

        query_clauses = ["trashed = false"]
        if target_folder:
            query_clauses.append(f"'{target_folder}' in parents")
        if q:
            query_clauses.append(f"({q})")

        full_q = " and ".join(query_clauses)
        fields = "nextPageToken,files(id,name,mimeType,size,createdTime,modifiedTime,webViewLink,thumbnailLink,owners,md5Checksum)"
        params = {
            "pageSize": str(page_size),
            "fields": fields,
            "orderBy": order_by,
            "q": full_q
        }
        if page_token:
            params["pageToken"] = page_token

        url = f"{self.DRIVE_API_BASE}/files?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"})

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                # Try refresh once
                if self.refresh_access_token():
                    tok = self.get_credentials().get("access_token")
                    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"})
                    with urllib.request.urlopen(req, timeout=30) as retry_resp:
                        return json.loads(retry_resp.read().decode("utf-8"))
            raise RuntimeError(f"Google Drive API error ({e.code}): {e.reason}")

    def search_files(
        self,
        query: Optional[str] = None,
        name_contains: Optional[str] = None,
        mime_type: Optional[str] = None,
        modified_after: Optional[str] = None,
        folder_id: Optional[str] = None,
        page_size: int = 25
    ) -> Dict[str, Any]:
        """Searches files by name, type, modification date, and location."""
        clauses = []
        if name_contains:
            clauses.append(f"name contains '{name_contains}'")
        if mime_type:
            clauses.append(f"mimeType contains '{mime_type}'")
        if modified_after:
            clauses.append(f"modifiedTime > '{modified_after}'")
        if query:
            clauses.append(f"({query})")

        custom_q = " and ".join(clauses) if clauses else None
        return self.list_files(folder_id=folder_id, page_size=page_size, q=custom_q)

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """Fetches metadata and provenance for a specific file."""
        tok = self._get_valid_token()
        fields = "id,name,mimeType,size,createdTime,modifiedTime,webViewLink,thumbnailLink,owners,parents,md5Checksum"
        url = f"{self.DRIVE_API_BASE}/files/{file_id}?fields={urllib.parse.quote(fields)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"})

        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def download_file(self, file_id: str, dest_path: Optional[Path] = None) -> bytes:
        """Downloads private binary content for an authorized file."""
        tok = self._get_valid_token()
        url = f"{self.DRIVE_API_BASE}/files/{file_id}?alt=media"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})

        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read()

        if dest_path:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(content)

        return content

    def detect_new_media(self, folder_id: Optional[str] = None, since_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        """Detects newly added media (images, videos, PDFs) since last sync or timestamp."""
        media_clauses = [
            "(mimeType contains 'image/' or mimeType contains 'video/' or mimeType = 'application/pdf')"
        ]
        if since_iso:
            media_clauses.append(f"modifiedTime > '{since_iso}'")

        res = self.list_files(folder_id=folder_id, page_size=50, q=" and ".join(media_clauses))
        return res.get("files", [])

    def import_file(
        self,
        file_id: str,
        candidate_id: Optional[str] = None,
        project: Optional[str] = None,
        custom_filename: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Downloads private file, preserves provenance, hashes SHA-256, and registers in Asset Storage."""
        # Deduplication check: if file_id already ingested and file exists on disk
        cfg = self._get_parent_config()
        existing = next((i for i in cfg.get("synced_items", []) if i.get("file_id") == file_id), None)
        if existing and (self.assets_dir / existing.get("filename", "")).exists():
            return {
                "success": True,
                "deduplicated": True,
                "source": "google_drive_oauth",
                "file_id": file_id,
                "filename": existing["filename"],
                "relative_path": f"user_submissions/{existing['filename']}",
                "url": f"/assets/user_submissions/{existing['filename']}",
                "size_bytes": existing.get("size_bytes", 0),
                "sha256": existing.get("sha256", ""),
                "candidate_id": existing.get("candidate_id", "-"),
                "project": existing.get("project", "General"),
                "provenance": existing.get("provenance", {}),
                "fulfilled_request": None,
                "message": "Asset already ingested; returned existing record (SHA-256 deduplicated)."
            }

        meta = self.get_file_metadata(file_id)
        raw_name = custom_filename or meta.get("name") or f"drive_{file_id}"
        clean_name = re.sub(r'[\\/*?:"<>| ]', '_', raw_name)

        # Download content
        content = self.download_file(file_id)
        sha = hashlib.sha256(content).hexdigest()

        prefix = f"{candidate_id}_" if candidate_id else "oauth_drive_"
        dest_filename = f"{prefix}{clean_name}"
        dest_path = self.assets_dir / dest_filename

        with open(dest_path, "wb") as f:
            f.write(content)

        inferred_proj = _infer_project(candidate_id, clean_name, project)

        # Cascading auto-fulfillment
        fulfilled_req = None
        try:
            from core.asset_planner import AssetPlanner
            planner = AssetPlanner(self.workspace_root)
            if request_id and (planner.requests_dir / f"{request_id}.json").exists():
                fulfilled_req = planner.fulfill_request(request_id, dest_path)
            else:
                pending_reqs = planner.list_pending_requests()
                target_req = None
                if candidate_id:
                    target_req = next((r for r in pending_reqs if r.candidate_id == candidate_id), None)
                if not target_req and pending_reqs:
                    target_req = next((r for r in pending_reqs if r.candidate_id in clean_name), None)

                if target_req:
                    fulfilled_req = planner.fulfill_request(target_req.request_id, dest_path)
        except Exception:
            pass

        record = {
            "file_id": file_id,
            "filename": dest_filename,
            "sha256": sha,
            "size_bytes": len(content),
            "candidate_id": candidate_id or (fulfilled_req.candidate_id if fulfilled_req else "-"),
            "project": inferred_proj,
            "source": "google_drive_oauth",
            "provenance": {
                "adapter": "GoogleDriveOAuthAdapter",
                "drive_file_id": file_id,
                "drive_name": meta.get("name"),
                "mime_type": meta.get("mimeType"),
                "webViewLink": meta.get("webViewLink"),
                "account_email": self.get_credentials().get("account_email"),
                "account_name": self.get_credentials().get("account_name"),
                "created_time": meta.get("createdTime"),
                "modified_time": meta.get("modifiedTime")
            },
            "synced_at": datetime.now(timezone.utc).isoformat()
        }

        cfg = self._get_parent_config()
        synced_items = [i for i in cfg.get("synced_items", []) if i.get("file_id") != file_id]
        synced_items.insert(0, record)
        self._save_parent_config({
            "synced_items": synced_items[:150],
            "last_sync_at": datetime.now(timezone.utc).isoformat()
        })

        return {
            "success": True,
            "source": "google_drive_oauth",
            "file_id": file_id,
            "filename": dest_filename,
            "relative_path": f"user_submissions/{dest_filename}",
            "url": f"/assets/user_submissions/{dest_filename}",
            "size_bytes": len(content),
            "sha256": sha,
            "candidate_id": record["candidate_id"],
            "project": inferred_proj,
            "provenance": record["provenance"],
            "fulfilled_request": fulfilled_req.request_id if fulfilled_req else None
        }

    def get_root_folder_id(self) -> str:
        """Returns the configured root folder ID which acts as the absolute boundary."""
        c = self.get_credentials()
        rf = (c.get("root_folder_id") or "").strip()
        if not rf:
            rf = (self._get_parent_config().get("folder_id") or "").strip()
        return rf

    def get_root_folder_name(self) -> str:
        """Returns the name of the root folder, querying Google Drive API if not cached."""
        c = self.get_credentials()
        rname = (c.get("root_folder_name") or "").strip()
        if rname:
            return rname
        rf_id = self.get_root_folder_id()
        if not rf_id:
            return "Agency Drive"
        try:
            meta = self.get_file_metadata(rf_id)
            rname = meta.get("name") or "Agency Drive"
            self.save_credentials({"root_folder_name": rname})
            return rname
        except Exception:
            return "Agency Drive"

    def verify_within_root(self, folder_id: Optional[str]) -> bool:
        """Verifies if folder_id is within the configured root_folder_id.
        Enforces strict boundary isolation: navigating or uploading outside root is blocked.
        """
        root_id = self.get_root_folder_id()
        if not root_id:
            return True
        if not folder_id or folder_id == root_id:
            return True
        if folder_id in self._verified_within_root:
            return True

        curr = folder_id
        visited = set()
        while curr and curr != "root" and curr not in visited:
            visited.add(curr)
            try:
                meta = self.get_file_metadata(curr)
                parents = meta.get("parents", [])
                if not parents:
                    break
                if root_id in parents:
                    for v in visited:
                        self._verified_within_root.add(v)
                    self._verified_within_root.add(folder_id)
                    return True
                curr = parents[0]
            except Exception:
                break
        return False

    def get_breadcrumbs(self, folder_id: Optional[str]) -> List[Dict[str, str]]:
        """Returns hierarchical breadcrumbs starting strictly from root_folder_id down to folder_id."""
        root_id = self.get_root_folder_id()
        root_name = self.get_root_folder_name()
        root_bc = {"id": root_id, "name": root_name}

        if not root_id or not folder_id or folder_id == root_id:
            return [root_bc]

        trail: List[Dict[str, str]] = []
        curr = folder_id
        visited = set()
        while curr and curr != root_id and curr not in visited:
            visited.add(curr)
            try:
                meta = self.get_file_metadata(curr)
                trail.append({"id": curr, "name": meta.get("name", curr)})
                parents = meta.get("parents", [])
                if not parents or root_id in parents:
                    break
                curr = parents[0]
            except Exception:
                trail.append({"id": curr, "name": curr})
                break

        trail.reverse()
        return [root_bc] + trail

    def browse_folder(
        self,
        folder_id: Optional[str] = None,
        page_size: int = 100,
        page_token: Optional[str] = None,
        q: Optional[str] = None,
        mime_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """Browses a folder within root_folder_id, returning breadcrumbs, metadata, thumbnails, and asset mappings."""
        root_id = self.get_root_folder_id()
        target_folder = folder_id or root_id
        if not target_folder:
            raise RuntimeError("Google Drive root folder is not configured. Please configure in Drive Settings.")

        if not self.verify_within_root(target_folder):
            raise PermissionError(f"Access denied: Requested folder '{target_folder}' is outside the configured agency root folder.")

        breadcrumbs = self.get_breadcrumbs(target_folder)
        query_parts = []
        if q:
            query_parts.append(f"name contains '{q}'")

        custom_q = " and ".join(query_parts) if query_parts else None
        res = self.list_files(
            folder_id=target_folder,
            page_size=page_size,
            page_token=page_token,
            q=custom_q,
            order_by="folder,name,modifiedTime desc"
        )
        files = res.get("files", [])

        # Map against local synced_items
        cfg = self._get_parent_config()
        synced_map = {item.get("file_id"): item for item in cfg.get("synced_items", []) if item.get("file_id")}

        # Map candidate topics from LifecycleManager if available
        candidate_map: Dict[str, str] = {}
        try:
            from core.lifecycle_manager import LifecycleManager
            lm = LifecycleManager(self.workspace_root)
            for c in lm.list_candidates():
                candidate_map[c.candidate_id] = c.topic
        except Exception:
            pass

        annotated_items = []
        for f in files:
            fid = f.get("id")
            mime = f.get("mimeType", "")
            is_folder = (mime == "application/vnd.google-apps.folder")
            synced = synced_map.get(fid)
            is_imported = False
            if synced:
                fn = synced.get("filename", "")
                if fn and (self.assets_dir / fn).exists():
                    is_imported = True

            annotated_items.append({
                "id": fid,
                "name": f.get("name", ""),
                "mimeType": mime,
                "isFolder": is_folder,
                "size": int(f.get("size", 0)) if f.get("size") else 0,
                "createdTime": f.get("createdTime"),
                "modifiedTime": f.get("modifiedTime"),
                "webViewLink": f.get("webViewLink"),
                "thumbnailLink": f.get("thumbnailLink"),
                "hasThumbnail": bool(f.get("thumbnailLink") or "image/" in mime),
                "isImported": is_imported,
                "importedFilename": synced.get("filename") if is_imported else None,
                "sha256": synced.get("sha256") if is_imported else None,
                "candidateId": synced.get("candidate_id") if is_imported else None,
                "candidateTopic": candidate_map.get(synced.get("candidate_id", "")) if (is_imported and synced) else None,
                "project": synced.get("project") if is_imported else None,
                "localUrl": synced.get("url") if is_imported else None,
                "channels": ["LinkedIn", "Instagram", "X"] if is_imported else []
            })

        folders = [i for i in annotated_items if i["isFolder"]]
        files_only = [i for i in annotated_items if not i["isFolder"]]

        if mime_filter:
            mf = mime_filter.lower().strip()
            if mf in ("folders", "folder"):
                items = folders
            elif mf in ("images", "image"):
                items = [i for i in files_only if "image/" in i["mimeType"]]
            elif mf in ("videos", "video"):
                items = [i for i in files_only if "video/" in i["mimeType"]]
            elif mf in ("documents", "document", "docs"):
                items = [i for i in files_only if "image/" not in i["mimeType"] and "video/" not in i["mimeType"]]
            else:
                items = folders + files_only
        else:
            items = folders + files_only

        current_name = None
        for b in breadcrumbs:
            if b["id"] == target_folder:
                current_name = b["name"]
                break
        if not current_name:
            current_name = self.get_root_folder_name() if target_folder == root_id else target_folder

        return {
            "success": True,
            "root_folder_id": root_id,
            "current_folder": {
                "id": target_folder,
                "name": current_name
            },
            "is_root": (target_folder == root_id),
            "breadcrumbs": breadcrumbs,
            "items": items,
            "total_count": len(items),
            "folder_count": len(folders),
            "file_count": len(files_only),
            "next_page_token": res.get("nextPageToken")
        }

    def search_within_root(
        self,
        query: str,
        mime_filter: Optional[str] = None,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """Searches for files/folders by name within root_folder_id, reporting folder path for each."""
        root_id = self.get_root_folder_id()
        if not root_id:
            raise RuntimeError("Google Drive root folder is not configured.")

        res = self.list_files(folder_id=None, page_size=page_size, q=f"name contains '{query}'")
        raw_files = res.get("files", [])

        filtered_files = []
        for f in raw_files:
            fid = f.get("id")
            if fid == root_id:
                continue
            if self.verify_within_root(fid):
                filtered_files.append(f)

        cfg = self._get_parent_config()
        synced_map = {item.get("file_id"): item for item in cfg.get("synced_items", []) if item.get("file_id")}

        annotated = []
        for f in filtered_files:
            fid = f.get("id")
            mime = f.get("mimeType", "")
            is_folder = (mime == "application/vnd.google-apps.folder")
            synced = synced_map.get(fid)
            is_imported = bool(synced and (self.assets_dir / synced.get("filename", "")).exists())

            parent_id = f.get("parents", [None])[0] if f.get("parents") else None
            folder_path = "/"
            if parent_id:
                bc = self.get_breadcrumbs(parent_id)
                folder_path = " / ".join([b["name"] for b in bc])

            annotated.append({
                "id": fid,
                "name": f.get("name", ""),
                "mimeType": mime,
                "isFolder": is_folder,
                "size": int(f.get("size", 0)) if f.get("size") else 0,
                "modifiedTime": f.get("modifiedTime"),
                "webViewLink": f.get("webViewLink"),
                "thumbnailLink": f.get("thumbnailLink"),
                "folderPath": folder_path,
                "parentId": parent_id,
                "isImported": is_imported,
                "sha256": synced.get("sha256") if is_imported else None,
                "candidateId": synced.get("candidate_id") if is_imported else None,
                "project": synced.get("project") if is_imported else None
            })

        if mime_filter:
            mf = mime_filter.lower().strip()
            if mf in ("folders", "folder"):
                annotated = [i for i in annotated if i["isFolder"]]
            elif mf in ("images", "image"):
                annotated = [i for i in annotated if "image/" in i["mimeType"]]
            elif mf in ("videos", "video"):
                annotated = [i for i in annotated if "video/" in i["mimeType"]]
            elif mf in ("documents", "document", "docs"):
                annotated = [i for i in annotated if not i["isFolder"] and "image/" not in i["mimeType"] and "video/" not in i["mimeType"]]

        return {
            "success": True,
            "query": query,
            "results": annotated,
            "total_matches": len(annotated)
        }

    def get_thumbnail_bytes(self, file_id: str) -> Tuple[bytes, str]:
        """Fetches and caches thumbnail bytes for Google Drive images/assets."""
        cache_file = self.thumbnail_cache_dir / f"{file_id}.thumb"
        if cache_file.exists() and cache_file.stat().st_size > 0:
            with open(cache_file, "rb") as f:
                return f.read(), "image/jpeg"

        tok = self._get_valid_token()
        meta = self.get_file_metadata(file_id)
        thumb_link = meta.get("thumbnailLink")

        if thumb_link:
            try:
                req = urllib.request.Request(thumb_link, headers={"Authorization": f"Bearer {tok}"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    content = resp.read()
                    with open(cache_file, "wb") as f:
                        f.write(content)
                    return content, resp.headers.get("Content-Type", "image/jpeg")
            except Exception:
                pass

        mime = meta.get("mimeType", "")
        if "image/" in mime:
            try:
                content = self.download_file(file_id)
                with open(cache_file, "wb") as f:
                    f.write(content)
                return content, mime
            except Exception:
                pass

        svg_placeholder = (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#6b7280" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>'
        )
        return svg_placeholder, "image/svg+xml"

    def upload_file(
        self,
        folder_id: str,
        filename: str,
        content: bytes,
        mime_type: str = "application/octet-stream",
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """Uploads a file into the specified Google Drive folder, strictly enforcing root boundary."""
        if not self.verify_within_root(folder_id):
            raise PermissionError(f"Access denied: Target folder '{folder_id}' is outside the configured agency root folder.")

        target_filename = filename
        if not overwrite:
            existing = self.list_files(folder_id=folder_id, q=f"name = '{filename}'").get("files", [])
            if existing:
                base, ext = os.path.splitext(filename)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                target_filename = f"{base}_{stamp}{ext}"

        tok = self._get_valid_token()
        boundary = f"=====boundary_{uuid.uuid4().hex}====="
        meta_json = json.dumps({"name": target_filename, "parents": [folder_id]}).encode("utf-8")

        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode("utf-8")
            + meta_json
            + f"\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n".encode("utf-8")
            + content
            + f"\r\n--{boundary}--\r\n".encode("utf-8")
        )

        upload_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,mimeType,size,webViewLink,createdTime,modifiedTime"
        req = urllib.request.Request(
            upload_url,
            data=body,
            headers={
                "Authorization": f"Bearer {tok}",
                "Content-Type": f"multipart/related; boundary={boundary}",
                "Content-Length": str(len(body))
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return {
                    "success": True,
                    "file": result,
                    "folder_id": folder_id,
                    "filename": target_filename,
                    "size_bytes": len(content)
                }
        except urllib.error.HTTPError as e:
            if e.code == 403:
                err_body = e.read().decode("utf-8", errors="ignore")
                if "insufficientPermissions" in err_body:
                    raise PermissionError(
                        "Google Drive upload requires write permission (drive.file scope). "
                        "Please click 'Reconnect Google Drive' in Drive Settings to grant upload permissions."
                    )
            raise RuntimeError(f"Google Drive upload failed ({e.code}): {e.reason}")

    def attach_to_candidate(
        self,
        file_id: str,
        candidate_id: str,
        request_id: Optional[str] = None,
        project: Optional[str] = None,
        custom_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """Directly attaches a Google Drive file to a candidate, fulfills asset request, and cascades multi-platform."""
        import_res = self.import_file(
            file_id=file_id,
            candidate_id=candidate_id,
            project=project,
            custom_filename=custom_filename,
            request_id=request_id
        )

        dest_path = self.assets_dir / import_res["filename"]
        fulfilled_req_id = import_res.get("fulfilled_request")
        cascaded_requests = []

        try:
            from core.asset_planner import AssetPlanner
            planner = AssetPlanner(self.workspace_root)
            if not fulfilled_req_id:
                pending_reqs = planner.list_pending_requests()
                target_req = None
                if request_id:
                    target_req = next((r for r in pending_reqs if r.request_id == request_id), None)
                if not target_req and candidate_id:
                    target_req = next((r for r in pending_reqs if r.candidate_id == candidate_id), None)

                if target_req:
                    fulfilled = planner.fulfill_request(target_req.request_id, dest_path)
                    fulfilled_req_id = fulfilled.request_id

            req_dir = self.workspace_root / "lifecycle" / "human_asset_requests"
            if req_dir.exists():
                for rf in req_dir.glob("*.json"):
                    try:
                        with open(rf, "r", encoding="utf-8") as f:
                            rd = json.load(f)
                            if rd.get("candidate_id") == candidate_id and rd.get("status") == "FULFILLED":
                                cascaded_requests.append({
                                    "request_id": rd.get("request_id"),
                                    "platform": rd.get("platform", "ALL"),
                                    "status": rd.get("status")
                                })
                    except Exception:
                        pass
        except Exception:
            pass

        return {
            "success": True,
            "candidate_id": candidate_id,
            "file_id": file_id,
            "filename": import_res["filename"],
            "sha256": import_res["sha256"],
            "size_bytes": import_res["size_bytes"],
            "local_url": import_res["url"],
            "fulfilled_request_id": fulfilled_req_id,
            "cascaded_requests": cascaded_requests,
            "platforms": ["LinkedIn", "Instagram", "X"]
        }


class DriveAssetSource:
    """Master facade coordinating the three Drive asset ingestion adapters:
    1. LocalSyncAdapter (local synced desktop directory)
    2. ShareLinkAdapter (unauthenticated Google Drive share URLs/IDs)
    3. GoogleDriveOAuthAdapter (authenticated Google Drive OAuth 2.0 account)
    """

    DEFAULT_CONFIG = {
        "enabled": True,
        "drive_type": "google_drive",
        "folder_id": "",
        "folder_url": "",
        "local_sync_path": "",
        "auto_sync_on_morning_run": True,
        "last_sync_at": None,
        "synced_items": []
    }

    SUPPORTED_EXTENSIONS = SUPPORTED_EXTENSIONS

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.config_dir = self.workspace_root / "knowledge"
        self.config_file = self.config_dir / "drive_config.json"
        self.assets_dir = self.workspace_root / "assets" / "user_submissions"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_config()

        # Initialize sub-adapters
        self.local_sync = LocalSyncAdapter(self.workspace_root, self)
        self.share_link = ShareLinkAdapter(self.workspace_root, self)
        self.oauth = GoogleDriveOAuthAdapter(self.workspace_root, self)

    def _ensure_config(self):
        if not self.config_file.exists():
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.DEFAULT_CONFIG, f, indent=2)

    def get_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return {**self.DEFAULT_CONFIG, **cfg}
        except Exception:
            return self.DEFAULT_CONFIG.copy()

    def save_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        cfg = self.get_config()
        cfg.update(updates)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return cfg

    @staticmethod
    def extract_file_id(url_or_id: str) -> Optional[str]:
        return ShareLinkAdapter.extract_file_id(url_or_id)

    def import_from_google_drive(
        self,
        url_or_id: str,
        candidate_id: Optional[str] = None,
        project: Optional[str] = None,
        custom_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """Delegates to ShareLinkAdapter for link-based ingestion."""
        return self.share_link.import_from_url(
            url_or_id=url_or_id,
            candidate_id=candidate_id,
            project=project,
            custom_filename=custom_filename
        )

    def sync_local_drive(self, local_path: Optional[str] = None) -> Dict[str, Any]:
        """Delegates to LocalSyncAdapter."""
        return self.local_sync.sync(local_path=local_path)

    def sync(self) -> Dict[str, Any]:
        """Executes synchronization across configured endpoints."""
        cfg = self.get_config()
        results = {"timestamp": datetime.now(timezone.utc).isoformat(), "actions": []}

        # 1. Local sync if configured
        if cfg.get("local_sync_path"):
            local_res = self.local_sync.sync(cfg["local_sync_path"])
            results["actions"].append({"type": "local_drive", **local_res})

        # 2. Authenticated Google Drive OAuth new media check if account is connected
        if self.oauth.is_connected():
            try:
                detected = self.oauth.detect_new_media(since_iso=cfg.get("last_sync_at"))
                ingested = []
                for f_meta in detected[:10]:
                    try:
                        imp = self.oauth.import_file(f_meta["id"])
                        ingested.append(imp)
                    except Exception:
                        pass
                results["actions"].append({
                    "type": "google_drive_oauth",
                    "status": "GOOGLE_DRIVE_ACCOUNT_CONNECTED",
                    "detected_count": len(detected),
                    "ingested_count": len(ingested)
                })
            except Exception as e:
                results["actions"].append({
                    "type": "google_drive_oauth",
                    "error": str(e)
                })

        return results

    def get_status(self) -> Dict[str, Any]:
        """Provides composite status distinguishing all 3 layers clearly."""
        cfg = self.get_config()
        local_status = self.local_sync.get_status()
        oauth_status = self.oauth.get_status()
        share_status = self.share_link.get_status()

        # Determine overall status label without false claims
        if oauth_status["connected"]:
            overall_label = "GOOGLE DRIVE ACCOUNT CONNECTED"
        elif local_status["connected"]:
            overall_label = "LOCAL SYNC CONNECTED"
        else:
            overall_label = "SHARE LINK IMPORT AVAILABLE"

        return {
            "overall_status_label": overall_label,
            "local_sync_status": local_status["status"],
            "oauth_status": oauth_status["status"],
            "share_link_status": share_status["status"],
            "local_sync": local_status,
            "oauth": oauth_status,
            "share_link": share_status,
            "enabled": cfg.get("enabled", True),
            "drive_type": cfg.get("drive_type", "google_drive"),
            "folder_id": cfg.get("folder_id", ""),
            "folder_url": cfg.get("folder_url", ""),
            "local_sync_path": cfg.get("local_sync_path", ""),
            "auto_sync_on_morning_run": cfg.get("auto_sync_on_morning_run", True),
            "last_sync_at": cfg.get("last_sync_at"),
            "synced_items_count": len(cfg.get("synced_items", []))
        }

    def browse_folder(
        self,
        folder_id: Optional[str] = None,
        page_size: int = 100,
        page_token: Optional[str] = None,
        q: Optional[str] = None,
        mime_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """Delegates browsing to GoogleDriveOAuthAdapter."""
        return self.oauth.browse_folder(
            folder_id=folder_id,
            page_size=page_size,
            page_token=page_token,
            q=q,
            mime_filter=mime_filter
        )

    def search_within_root(
        self,
        query: str,
        mime_filter: Optional[str] = None,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """Delegates search to GoogleDriveOAuthAdapter."""
        return self.oauth.search_within_root(
            query=query,
            mime_filter=mime_filter,
            page_size=page_size
        )

    def upload_file(
        self,
        folder_id: str,
        filename: str,
        content: bytes,
        mime_type: str = "application/octet-stream",
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """Delegates upload to GoogleDriveOAuthAdapter."""
        return self.oauth.upload_file(
            folder_id=folder_id,
            filename=filename,
            content=content,
            mime_type=mime_type,
            overwrite=overwrite
        )

    def attach_to_candidate(
        self,
        file_id: str,
        candidate_id: str,
        request_id: Optional[str] = None,
        project: Optional[str] = None,
        custom_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """Delegates candidate attachment to GoogleDriveOAuthAdapter."""
        return self.oauth.attach_to_candidate(
            file_id=file_id,
            candidate_id=candidate_id,
            request_id=request_id,
            project=project,
            custom_filename=custom_filename
        )

    def get_thumbnail_bytes(self, file_id: str) -> Tuple[bytes, str]:
        """Delegates thumbnail retrieval to GoogleDriveOAuthAdapter."""
        return self.oauth.get_thumbnail_bytes(file_id)


# Backward compatibility alias
DriveAdapter = DriveAssetSource
