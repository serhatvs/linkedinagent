"""Native PySide6 Desktop GUI for Serhat's Personal Media Agency.

Provides a standalone Windows desktop app to:
- View and fulfill pending Human Asset Requests with native Windows file dialogs & image previews.
- Review and sign posts in the Approval Queue.
- Inspect the Multi-Channel Distribution Matrix.
- Manage Killswitch modes and run Morning Health Checks.
"""

from __future__ import annotations
import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone

# Ensure workspace root in sys.path
_ws_root = Path(__file__).resolve().parent.parent
if str(_ws_root) not in sys.path:
    sys.path.insert(0, str(_ws_root))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QTextEdit, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QSplitter, QGroupBox, QRadioButton, QButtonGroup, QScrollArea, QFrame
)
from PySide6.QtGui import QPixmap, QFont, QColor, QPalette, QIcon
from PySide6.QtCore import Qt, QSize

from core.models import (
    HumanAssetRequest,
    Candidate,
    CandidateDecision,
    MVTSEvaluation,
    Post,
    LifecycleState
)
from core.asset_planner import AssetPlanner
from core.approval_engine import ApprovalEngine
from core.lifecycle_manager import LifecycleManager
from core.distribution_adapter import DistributionAdapter
from core.scheduler_engine import AgencyScheduler


class AgencyGUI(QMainWindow):
    def __init__(self, workspace_root: Path):
        super().__init__()
        self.workspace_root = workspace_root
        self.planner = AssetPlanner(workspace_root)
        self.approval_engine = ApprovalEngine(workspace_root)
        self.lifecycle_manager = LifecycleManager(workspace_root)
        self.selected_file_path: Path | None = None
        self.current_req_data: dict | None = None

        self.setWindowTitle("Serhat — Autonomous Personal Media Agency")
        self.resize(1100, 720)
        self._apply_dark_theme()
        self._init_ui()
        self.refresh_all()

    def _apply_dark_theme(self):
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(9, 13, 22))
        palette.setColor(QPalette.WindowText, QColor(241, 245, 249))
        palette.setColor(QPalette.Base, QColor(17, 23, 38))
        palette.setColor(QPalette.AlternateBase, QColor(22, 31, 51))
        palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
        palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
        palette.setColor(QPalette.Text, QColor(241, 245, 249))
        palette.setColor(QPalette.Button, QColor(26, 37, 59))
        palette.setColor(QPalette.ButtonText, QColor(241, 245, 249))
        palette.setColor(QPalette.BrightText, QColor(6, 182, 212))
        palette.setColor(QPalette.Highlight, QColor(6, 182, 212))
        palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
        self.setPalette(palette)

        self.setStyleSheet("""
            QMainWindow { background-color: #090D16; }
            QTabWidget::pane { border: 1px solid rgba(255, 255, 255, 0.1); background: #0F1523; }
            QTabBar::tab { background: #111726; color: #94A3B8; padding: 10px 20px; font-weight: bold; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
            QTabBar::tab:selected { background: #0F1523; color: #06B6D4; border-bottom: 2px solid #06B6D4; }
            QListWidget { background: #111726; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; color: #F1F5F9; font-size: 13px; }
            QListWidget::item { padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.04); }
            QListWidget::item:selected { background: #1E293B; color: #06B6D4; }
            QPushButton { background: #06B6D4; color: #000; font-weight: bold; padding: 8px 16px; border-radius: 6px; border: none; }
            QPushButton:hover { background: #22D3EE; }
            QPushButton:disabled { background: #334155; color: #64748B; }
            QTextEdit { background: #111726; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; color: #F1F5F9; font-family: 'Consolas', monospace; }
            QTableWidget { background: #111726; border: 1px solid rgba(255, 255, 255, 0.08); gridline-color: rgba(255,255,255,0.05); color: #F1F5F9; }
            QHeaderView::section { background: #090D16; color: #94A3B8; font-weight: bold; padding: 6px; border: 1px solid rgba(255,255,255,0.05); }
            QGroupBox { border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; margin-top: 1ex; font-weight: bold; color: #06B6D4; padding: 12px; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }
        """)

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Header Bar
        header = QHBoxLayout()
        title_label = QLabel("🚀 Serhat — Autonomous Personal Media Agency")
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        header.addWidget(title_label)

        header.addStretch()

        self.lbl_status = QLabel("🟢 ACTIVE")
        self.lbl_status.setStyleSheet("background: rgba(16, 185, 129, 0.15); color: #10B981; padding: 4px 10px; border-radius: 12px; font-weight: bold;")
        header.addWidget(self.lbl_status)

        layout.addLayout(header)

        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self._build_asset_requests_tab()
        self._build_approvals_tab()
        self._build_distribution_tab()
        self._build_controls_tab()

    # --- TAB 1: ASSET REQUESTS ---
    def _build_asset_requests_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        # Left list of requests
        left_panel = QVBoxLayout()
        lbl_list = QLabel("Pending & Active Asset Requests")
        lbl_list.setFont(QFont("Arial", 11, QFont.Bold))
        left_panel.addWidget(lbl_list)

        self.list_requests = QListWidget()
        self.list_requests.currentItemChanged.connect(self._on_request_selected)
        left_panel.addWidget(self.list_requests)

        btn_refresh = QPushButton("🔄 Refresh Requests")
        btn_refresh.setStyleSheet("background: #1E293B; color: #fff;")
        btn_refresh.clicked.connect(self.refresh_asset_requests)
        left_panel.addWidget(btn_refresh)

        layout.addLayout(left_panel, 1)

        # Right detail & submission pane
        right_panel = QVBoxLayout()

        self.lbl_req_title = QLabel("Select an asset request to review instructions")
        self.lbl_req_title.setFont(QFont("Arial", 12, QFont.Bold))
        right_panel.addWidget(self.lbl_req_title)

        self.lbl_req_meta = QLabel("")
        self.lbl_req_meta.setStyleSheet("color: #06B6D4; font-family: monospace;")
        right_panel.addWidget(self.lbl_req_meta)

        self.txt_instructions = QTextEdit()
        self.txt_instructions.setReadOnly(True)
        self.txt_instructions.setMaximumHeight(160)
        right_panel.addWidget(self.txt_instructions)

        # Image preview box
        self.lbl_preview = QLabel("No Image Selected")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setStyleSheet("border: 2px dashed rgba(255,255,255,0.15); border-radius: 8px; background: rgba(0,0,0,0.2); min-height: 180px;")
        right_panel.addWidget(self.lbl_preview)

        # File selection buttons
        btn_layout = QHBoxLayout()
        self.btn_select_file = QPushButton("📁 Choose Photo / Image...")
        self.btn_select_file.setStyleSheet("background: #1E293B; color: #fff;")
        self.btn_select_file.clicked.connect(self._choose_file)
        btn_layout.addWidget(self.btn_select_file)

        self.btn_submit_asset = QPushButton("🚀 Submit & Fulfill Request")
        self.btn_submit_asset.setEnabled(False)
        self.btn_submit_asset.clicked.connect(self._submit_current_asset)
        btn_layout.addWidget(self.btn_submit_asset)

        right_panel.addLayout(btn_layout)
        layout.addLayout(right_panel, 2)

        self.tabs.addTab(tab, "📸 Asset Requests")

    def refresh_asset_requests(self):
        self.list_requests.clear()
        requests_dir = self.workspace_root / "lifecycle" / "human_asset_requests"
        if not requests_dir.exists():
            return

        for p in sorted(requests_dir.glob("*.json"), key=os.path.getmtime, reverse=True):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    status_marker = "✅" if d.get("status") == "FULFILLED" else "📸"
                    item_text = f"{status_marker} [{d.get('target_platforms', [''])[0].upper()}] {d.get('candidate_id')} — {d.get('requested_asset_title')}"
                    item = QListWidgetItem(item_text)
                    item.setData(Qt.UserRole, d)
                    self.list_requests.addItem(item)
            except Exception:
                pass

    def _on_request_selected(self, current: QListWidgetItem, previous):
        if not current:
            return
        d = current.data(Qt.UserRole)
        self.current_req_data = d
        self.selected_file_path = None

        self.lbl_req_title.setText(d.get("requested_asset_title", ""))
        self.lbl_req_meta.setText(f"Candidate: {d.get('candidate_id')} | Target: {', '.join(d.get('target_platforms', []))} | Status: {d.get('status')}")

        shots_text = "\n".join([f"  • {s}" for s in d.get("recommended_shots", [])])
        full_instr = (
            f"WHY NEEDED:\n{d.get('why_needed')}\n\n"
            f"SHOOTING INSTRUCTIONS:\n{d.get('specific_instructions')}\n\n"
            f"RECOMMENDED SHOTS:\n{shots_text}"
        )
        self.txt_instructions.setText(full_instr)

        if d.get("status") == "FULFILLED":
            self.btn_select_file.setEnabled(False)
            self.btn_submit_asset.setEnabled(False)
            fpath = d.get("fulfilled_asset_path")
            self.lbl_preview.setText(f"✅ Fulfilled with:\n{fpath}\nSHA-256: {d.get('asset_sha256', 'N/A')}")
            # Try to preview if image exists
            if fpath:
                full_p = (self.workspace_root / fpath).resolve()
                if full_p.exists():
                    pix = QPixmap(str(full_p))
                    self.lbl_preview.setPixmap(pix.scaled(400, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.btn_select_file.setEnabled(True)
            self.btn_submit_asset.setEnabled(False)
            self.lbl_preview.clear()
            self.lbl_preview.setText("Ready: Click 'Choose Photo / Image' to select file")

    def _choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Photo for Asset Request",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if path:
            self.selected_file_path = Path(path)
            pix = QPixmap(path)
            self.lbl_preview.setPixmap(pix.scaled(400, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.btn_submit_asset.setEnabled(True)

    def _submit_current_asset(self):
        if not self.current_req_data or not self.selected_file_path:
            return
        req_id = self.current_req_data["request_id"]
        try:
            req = self.planner.fulfill_request(req_id, self.selected_file_path)
            QMessageBox.information(
                self,
                "Asset Registered",
                f"✅ Photo successfully registered!\n\nPath: {req.fulfilled_asset_path}\nSHA-256: {req.asset_sha256}\n\nPost is now unlocked!"
            )
            self.refresh_asset_requests()
        except Exception as e:
            QMessageBox.critical(self, "Submission Failed", str(e))

    # --- TAB 2: APPROVALS ---
    def _build_approvals_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("Pending Human Approval Requests"))
        self.list_approvals = QListWidget()
        self.list_approvals.currentItemChanged.connect(self._on_approval_selected)
        left_panel.addWidget(self.list_approvals)

        btn_ref_app = QPushButton("🔄 Refresh Approvals")
        btn_ref_app.setStyleSheet("background: #1E293B; color: #fff;")
        btn_ref_app.clicked.connect(self.refresh_approvals)
        left_panel.addWidget(btn_ref_app)

        layout.addLayout(left_panel, 1)

        right_panel = QVBoxLayout()
        self.lbl_appr_title = QLabel("Select an approval request to inspect")
        self.lbl_appr_title.setFont(QFont("Arial", 12, QFont.Bold))
        right_panel.addWidget(self.lbl_appr_title)

        self.txt_appr_content = QTextEdit()
        self.txt_appr_content.setReadOnly(True)
        right_panel.addWidget(self.txt_appr_content)

        self.btn_sign_approval = QPushButton("✍️ Approve & Sign Post (Serhat)")
        self.btn_sign_approval.setEnabled(False)
        self.btn_sign_approval.clicked.connect(self._sign_selected_approval)
        right_panel.addWidget(self.btn_sign_approval)

        layout.addLayout(right_panel, 2)
        self.tabs.addTab(tab, "📋 Approval Queue")

    def refresh_approvals(self):
        self.list_approvals.clear()
        pending_dir = self.workspace_root / "approvals" / "pending"
        if not pending_dir.exists():
            return

        for p in sorted(pending_dir.glob("*.json"), key=os.path.getmtime, reverse=True):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    item = QListWidgetItem(f"⏳ [{d.get('target_platform', '').upper()}] {d.get('content_summary', '')[:40]}...")
                    item.setData(Qt.UserRole, d)
                    self.list_approvals.addItem(item)
            except Exception:
                pass

    def _on_approval_selected(self, current: QListWidgetItem, previous):
        if not current:
            return
        d = current.data(Qt.UserRole)
        self.current_appr_data = d
        self.lbl_appr_title.setText(f"Post: {d.get('post_id')} | Target: {d.get('target_platform')}")
        self.txt_appr_content.setText(d.get("content_full_text", ""))
        self.btn_sign_approval.setEnabled(True)

    def _sign_selected_approval(self):
        if not hasattr(self, "current_appr_data") or not self.current_appr_data:
            return
        req_id = self.current_appr_data["request_id"]
        try:
            req = self.approval_engine.get_approval_request(req_id)
            token = self.approval_engine.sign_approval_request(req, signer="Serhat")
            QMessageBox.information(
                self,
                "Approval Granted",
                f"✅ Approval Token Generated!\nToken ID: {token.token_id}\nCanonical Hash: {token.canonical_payload_sha256[:20]}..."
            )
            self.refresh_approvals()
        except Exception as e:
            QMessageBox.critical(self, "Signing Failed", str(e))

    # --- TAB 3: DISTRIBUTION MATRIX ---
    def _build_distribution_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        lbl = QLabel("Multi-Platform Distribution Matrix (Top Backlog Candidates)")
        lbl.setFont(QFont("Arial", 11, QFont.Bold))
        layout.addWidget(lbl)

        self.table_matrix = QTableWidget()
        self.table_matrix.setColumnCount(5)
        self.table_matrix.setHorizontalHeaderLabels(["Candidate ID", "MVTS", "LinkedIn (Reputation)", "Instagram (Visual)", "X (Developer Feed)"])
        self.table_matrix.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table_matrix)

        btn_ref_mat = QPushButton("🔄 Refresh Matrix")
        btn_ref_mat.setStyleSheet("background: #1E293B; color: #fff;")
        btn_ref_mat.clicked.connect(self.refresh_distribution_matrix)
        layout.addWidget(btn_ref_mat)

        self.tabs.addTab(tab, "🌐 Distribution Matrix")

    def refresh_distribution_matrix(self):
        backlog_file = self.workspace_root / "lifecycle" / "real_content_backlog.json"
        if not backlog_file.exists():
            return

        with open(backlog_file, "r", encoding="utf-8") as f:
            bdata = json.load(f)

        candidates = bdata.get("candidates", [])[:12]
        adapter = DistributionAdapter()
        self.table_matrix.setRowCount(len(candidates))

        for i, c in enumerate(candidates):
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

            self.table_matrix.setItem(i, 0, QTableWidgetItem(cid))
            self.table_matrix.setItem(i, 1, QTableWidgetItem(f"{mvts_val:.1f}"))

            col_idx = 2
            for plat in ["linkedin", "instagram", "twitter"]:
                asset_res = self.planner.evaluate_asset_availability(cand_obj, plat)
                assets_for_plat = [asset_res["asset"]] if asset_res.get("status") == "ASSET_READY" else []

                story = adapter.generate_story_variants(
                    candidate=cand_obj,
                    base_text=c.get("title", "") + ". Measured engineering details.",
                    media_assets=assets_for_plat
                )

                if plat in story.variants:
                    badge = f"✅ READY (P{asset_res.get('source_priority', '1')})"
                elif asset_res.get("human_request_needed"):
                    badge = "📸 REQ_USER"
                elif len(assets_for_plat) == 0:
                    badge = "⏸️ NO ASSET"
                else:
                    badge = "⏸️ HELD"

                self.table_matrix.setItem(i, col_idx, QTableWidgetItem(badge))
                col_idx += 1

    # --- TAB 4: CONTROLS ---
    def _build_controls_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Killswitch group
        ks_box = QGroupBox("Shield & Killswitch Modes")
        ks_layout = QVBoxLayout(ks_box)

        self.rb_enabled = QRadioButton("🟢 AUTONOMY_ENABLED (Fully Autonomous Machine-Approval Active)")
        self.rb_paused = QRadioButton("⏸️ AUTONOMY_PAUSED (Require Manual Signatures)")
        self.rb_stop = QRadioButton("🔴 EMERGENCY_STOP (Halt All Operations)")

        ks_layout.addWidget(self.rb_enabled)
        ks_layout.addWidget(self.rb_paused)
        ks_layout.addWidget(self.rb_stop)

        btn_save_ks = QPushButton("💾 Update Autonomy Mode")
        btn_save_ks.clicked.connect(self._save_killswitch_mode)
        ks_layout.addWidget(btn_save_ks)

        layout.addWidget(ks_box)

        # Morning run box
        mr_box = QGroupBox("Morning Health Run")
        mr_layout = QVBoxLayout(mr_box)

        self.txt_mr_out = QTextEdit()
        self.txt_mr_out.setReadOnly(True)
        self.txt_mr_out.setMaximumHeight(180)
        mr_layout.addWidget(self.txt_mr_out)

        btn_mr = QPushButton("▶️ Run Morning Intelligence Cycle")
        btn_mr.clicked.connect(self._run_morning_cycle)
        mr_layout.addWidget(btn_mr)

        layout.addWidget(mr_box)
        layout.addStretch()

        self.tabs.addTab(tab, "⚙️ Control Center")

    def refresh_controls(self):
        ks = self.approval_engine.get_killswitch_state()
        mode = ks.get("mode", "AUTONOMY_ENABLED")
        if mode == "AUTONOMY_ENABLED":
            self.rb_enabled.setChecked(True)
            self.lbl_status.setText("🟢 ACTIVE")
            self.lbl_status.setStyleSheet("background: rgba(16, 185, 129, 0.15); color: #10B981; padding: 4px 10px; border-radius: 12px; font-weight: bold;")
        elif mode == "AUTONOMY_PAUSED":
            self.rb_paused.setChecked(True)
            self.lbl_status.setText("⏸️ PAUSED")
            self.lbl_status.setStyleSheet("background: rgba(245, 158, 11, 0.15); color: #F59E0B; padding: 4px 10px; border-radius: 12px; font-weight: bold;")
        else:
            self.rb_stop.setChecked(True)
            self.lbl_status.setText("🔴 EMERGENCY STOP")
            self.lbl_status.setStyleSheet("background: rgba(244, 63, 94, 0.15); color: #F43F5E; padding: 4px 10px; border-radius: 12px; font-weight: bold;")

    def _save_killswitch_mode(self):
        mode = "AUTONOMY_ENABLED"
        if self.rb_paused.isChecked():
            mode = "AUTONOMY_PAUSED"
        elif self.rb_stop.isChecked():
            mode = "EMERGENCY_STOP"

        self.approval_engine.set_killswitch_mode(mode, reason="Updated via Desktop GUI", authorized_by="Serhat")
        QMessageBox.information(self, "Killswitch Updated", f"Mode changed to: {mode}")
        self.refresh_controls()

    def _run_morning_cycle(self):
        scheduler = AgencyScheduler(self.workspace_root)
        briefing = scheduler.run_morning_intelligence()
        self.txt_mr_out.setText(
            f"Executed At: {briefing.get('executed_at')}\n"
            f"Queue: {briefing.get('scheduled_queue_count')} scheduled posts\n"
            f"Backlog Viable: {briefing.get('viable_candidates_count')} candidates\n"
            f"Decision: {briefing.get('decision')}\n"
            f"Rationale: {briefing.get('rationale')}\n"
            f"Write Bytes: 0 (Read-Only Health Inspection)"
        )

    def refresh_all(self):
        self.refresh_asset_requests()
        self.refresh_approvals()
        self.refresh_distribution_matrix()
        self.refresh_controls()


def launch_gui():
    app = QApplication.instance() or QApplication(sys.argv)
    ws = Path(__file__).resolve().parent.parent
    window = AgencyGUI(ws)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_gui()
