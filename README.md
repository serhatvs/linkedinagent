# Autonomous Personal Media Agency

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.12 | 3.13](https://img.shields.io/badge/Python-3.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Tests: 86 passed](https://img.shields.io/badge/Tests-86%20passed-success.svg)](tests/)
[![Architecture: 9--Stage State Machine](https://img.shields.io/badge/Architecture-9--Stage%20State%20Machine-blueviolet.svg)](lifecycle/)
[![Security: HMAC--SHA256 Human Gate](https://img.shields.io/badge/Security-HMAC--SHA256%20Human%20Gate-red.svg)](core/approval_engine.py)

An evidence-grounded, desktop-class autonomous media operations agency engineered for systems programmers, robotics developers, and embedded engineers. Built with Antigravity agentic orchestration, deterministic Design Rule Checks (DRC), and zero-trust external write boundaries.

---

## 1. Prime Directive: Credibility Over Frequency

Generic social media bots prioritize volume: scraping feeds, generating shallow corporate summaries, and spamming clickbait emojis. In hardware, robotics, and low-level systems engineering, ungrounded AI content immediately erodes technical credibility.

This agency is strictly empowered to choose **NO-OP (Publish Nothing)** whenever there is no sufficiently novel, grounded engineering progress to communicate. Silence is vastly superior to shallow or AI-slop content.

---

## 2. Core Architectural Pillars

### 1. Zero Autonomous External Writes & HMAC-SHA256 Gating
The agency can autonomously mine git diffs, inspect lab benchmarks, draft technical write-ups, evaluate editorial scorecards, and plan visual media. However, **it cannot dispatch to social networks without a valid human approval token**. Every external dispatch verifies an immutable canonical payload hash against a human-signed receipt in `approvals/signed/` authenticated with HMAC-SHA256.

### 2. Persistent, Strictly Validated 9-Stage Lifecycle
Content flows sequentially through an explicit, persistent state machine without skipping states:
```
IDEA → CANDIDATE → DRAFT → REVIEWED → AWAITING_APPROVAL → APPROVED → SCHEDULED → PUBLISHED → ANALYZED
```
- **MVTS Thresholds**: Posts must meet platform-specific Minimum Viable Technical Substance (MVTS) scores (LinkedIn ≥ 9.0, Instagram ≥ 7.5, X ≥ 6.5).
- **Domain Design Rule Checks (DRC)**: Automated checks verify mains electrical isolation, BMS protection on LiPo setups, logic level shifting (5V vs 3.3V), and 100% claim grounding against local repository facts.

### 3. Evidence-First Visual Publishing
Text-only posts are prohibited across all channels. Every release requires verified technical assets—schematics, oscilloscope traces, CAD models, or physical workbench photos—ingested via an authenticated Google Drive browser strictly sandboxed to an isolated root folder with SHA-256 deduplication.

### 4. Multi-Channel Distribution via Buffer Native MCP
Interfaces natively with the Buffer Model Context Protocol (MCP) gateway to manage scheduled dispatches across:
- **LinkedIn Personal Profile**: Deep architectural teardowns & measured benchmarks.
- **Instagram Professional Account**: Visual workbench builds & hardware logs.
- **X Developer Account**: Punchy, developer-native insights & micro-learnings.

### 5. Operator Workstation UI
A local, dark-mode desktop workstation running on `http://127.0.0.1:8765` providing:
- Real-time 9-stage Kanban lifecycle tracking
- Live audit log stream & safety killswitch controls
- Sandboxed Google Drive asset browser with thumbnail previews
- Cryptographic approval token signing modal

---

## 3. Directory Structure

```text
linkedinagent/
├── .agents/                    # Specialized agent skills and workspace rules
│   ├── rules/                  # Editorial guardrails, safety policies, brand positioning
│   └── skills/                 # Subagent skills (scout, writer, editorial-review, publisher)
├── assets/                     # Media assets, promo video, screenshots
│   ├── screenshots/            # Workstation interface screenshots
│   └── user_submissions/      # Real hardware workbench photos and schematics
├── core/                       # Core python engines
│   ├── agency_cli.py           # Command-line interface & workstation launcher
│   ├── approval_engine.py      # HMAC-SHA256 approval gate & payload canonicalizer
│   ├── drive_adapter.py        # Sandboxed Google Drive OAuth & sync adapters
│   ├── editorial_evaluator.py  # 5-point scorecard & Design Rule Checks (DRC)
│   ├── grounding_engine.py     # 100% claim grounding against knowledge base
│   ├── models.py               # Pydantic v2 data models & state machine transitions
│   └── ui_server.py            # Local FastAPI / Starlette workstation web server
├── knowledge/                  # Source-of-truth registries
│   ├── approved_facts.json     # Verified author facts and verifiable claims
│   └── projects_registry.json  # Grounded project records, commit SHAs, and specs
├── lifecycle/                  # Persistent 9-stage content lifecycle store
│   ├── 01_ideas/
│   ├── 02_candidates/
│   ├── 03_drafts/
│   ├── 04_reviewed/
│   ├── 05_awaiting_approval/
│   ├── 06_approved/
│   ├── 07_scheduled/
│   ├── 08_published/
│   └── 09_analyzed/
├── approvals/                  # Cryptographic approval requests & signed receipts
│   ├── pending/
│   └── signed/
├── tests/                      # Automated test suite (86 passing tests)
└── mcp_config.json             # MCP gateway configuration
```

---

## 4. Quickstart

### Installation
Clone the repository and install dependencies in Python 3.12 or 3.13:
```bash
git clone https://github.com/serhatvs/linkedinagent.git
cd linkedinagent
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt  # Or: pip install pydantic fastapi uvicorn pytest pillow
```

### Running the Test Suite
Ensure all 86 unit and integration tests pass:
```bash
pytest tests/ -q
```

### Launching the Operator Workstation
Start the local workstation interface:
```bash
python core/agency_cli.py ui
```
Open `http://127.0.0.1:8765` in your browser to monitor the pipeline, review candidate teardowns, and manage sandboxed Drive assets.

---

## 5. Security & Safety Model

1. **No Scraping & No Fake Credentials**: Does not use Selenium, Puppeteer, or unofficial private endpoints. All social publishing flows through official Buffer MCP gateways.
2. **Keyring Isolation**: Signing secrets are resolved from user-isolated runtime stores (`~/.gemini/antigravity-cli/secrets/`) or environment variables, never committed to git.
3. **Fail-Closed Hardware DRC**: Unverified claims regarding mains voltages (220V/110V) or lithium-polymer battery charging without BMS protection fail closed deterministically.

---

## 6. License

This project is licensed under the [MIT License](LICENSE) - see the [LICENSE](LICENSE) file for details.
