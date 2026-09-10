# Emergency Killswitch & Incident Response Procedure

This document outlines the deterministic safety protocol in the event of an unintended state drift, security concern, or human override request.

---

## The Master Killswitch Command

To immediately pause all agency operations and revoke all pending or signed actions:

```bash
python -m core.agency_cli killswitch --reason "Human operator requested full freeze"
```

---

## Automated Actions Executed by the Killswitch

1. **Immediate Pipeline Freeze**:
   - Sets global agency state flag `agency_frozen: true` in `approvals/killswitch_state.json`.
   - All state transitions in `core.lifecycle_manager` are rejected with `E_AGENCY_FROZEN`.

2. **Revocation of Approval Tokens**:
   - All tokens in `approvals/signed/` are moved to `approvals/revoked/` or flagged as expired.
   - Any attempt by `publisher` to dispatch to Metricool MCP will immediately fail payload and signature checks.

3. **Metricool Queue Quarantine**:
   - If configured with write access, queries Metricool MCP for any scheduled posts in the future and sends cancellation requests.

4. **Incident Audit Log**:
   - Appends an immutable event to `approvals/audit_log.jsonl` with timestamp, initiator, and reason.

---

## Recovery Procedure
1. Inspect the incident log in `approvals/audit_log.jsonl`.
2. Address root cause (e.g. prompt injection attempt, incorrect benchmark claim).
3. Explicitly unfreeze using:
   ```bash
   python -m core.agency_cli unfreeze --authorized-by "Serhat"
   ```
