import base64
import json
import struct

import keeper_audit
import solana_safety
from keeper_audit import (FAIL, INFO, PASS, UNKNOWN, append_log, audit_token,
                          check_authorities, check_dev_holdings,
                          check_lp_burned, render_receipts, verify_log)


def _mint_bytes(mint_active: bool, freeze_active: bool, supply: int = 1_000_000_000,
                decimals: int = 6) -> bytes:
    raw = bytearray(82)
    struct.pack_into("<I", raw, 0, 1 if mint_active else 0)
    if mint_active:
        raw[4:36] = bytes([7] * 32)
    struct.pack_into("<Q", raw, 36, supply)
    raw[44] = decimals
    raw[45] = 1
    struct.pack_into("<I", raw, 46, 1 if freeze_active else 0)
    if freeze_active:
        raw[50:82] = bytes([9] * 32)
    return bytes(raw)


def _patch_mint(monkeypatch, raw: bytes):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"result": {"value": {"data": [base64.b64encode(raw).decode(), "base64"]}}}

    monkeypatch.setattr(solana_safety.requests, "post", lambda *a, **k: FakeResponse())


# ---------------------------------------------------------------- authorities

def test_revoked_authorities_pass(monkeypatch):
    _patch_mint(monkeypatch, _mint_bytes(False, False))
    checks = check_authorities("MINT", "url")
    by_name = {c["name"]: c for c in checks}
    assert by_name["mint authority"]["status"] == PASS
    assert by_name["freeze authority"]["status"] == PASS
    assert by_name["supply"]["status"] == INFO


def test_active_mint_authority_fails_and_names_the_holder(monkeypatch):
    _patch_mint(monkeypatch, _mint_bytes(True, False))
    by_name = {c["name"]: c for c in check_authorities("MINT", "url")}
    assert by_name["mint authority"]["status"] == FAIL
    # the holder pubkey must appear so it can be investigated, not just flagged
    assert solana_safety.b58encode(bytes([7] * 32)) in by_name["mint authority"]["detail"]


def test_active_freeze_authority_fails(monkeypatch):
    _patch_mint(monkeypatch, _mint_bytes(False, True))
    by_name = {c["name"]: c for c in check_authorities("MINT", "url")}
    assert by_name["freeze authority"]["status"] == FAIL


def test_missing_account_fails(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"result": {"value": None}}

    monkeypatch.setattr(solana_safety.requests, "post", lambda *a, **k: FakeResponse())
    checks = check_authorities("NOPE", "url")
    assert checks[0]["status"] == FAIL


# ------------------------------------------------------------------------ LP

def test_lp_supply_zero_passes(monkeypatch):
    _patch_mint(monkeypatch, _mint_bytes(False, False, supply=0))
    assert check_lp_burned("LP", "url")["status"] == PASS


def test_lp_with_supply_fails(monkeypatch):
    _patch_mint(monkeypatch, _mint_bytes(False, False, supply=5_000_000))
    assert check_lp_burned("LP", "url")["status"] == FAIL


# --------------------------------------------------------------- dev holdings

def test_dev_wallet_holding_zero_passes(monkeypatch):
    monkeypatch.setattr(keeper_audit, "rpc_call", lambda *a, **k: {"value": []})
    assert check_dev_holdings("MINT", "DEV", "url")["status"] == PASS


def test_dev_wallet_holding_tokens_fails(monkeypatch):
    monkeypatch.setattr(keeper_audit, "rpc_call", lambda *a, **k: {"value": [
        {"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": 42000}}}}}}
    ]})
    check = check_dev_holdings("MINT", "DEV", "url")
    assert check["status"] == FAIL
    assert "42,000" in check["detail"]


def test_unreadable_dev_wallet_is_unknown_not_pass(monkeypatch):
    monkeypatch.setattr(keeper_audit, "rpc_call", lambda *a, **k: {"_error": "boom"})
    assert check_dev_holdings("MINT", "DEV", "url")["status"] == UNKNOWN


# -------------------------------------------------------------------- verdict

def _audit_with(monkeypatch, mint_active=False, freeze_active=False, conc_error=True):
    _patch_mint(monkeypatch, _mint_bytes(mint_active, freeze_active))
    if conc_error:
        monkeypatch.setattr(keeper_audit, "rpc_call", lambda *a, **k: {"_error": "skip"})
    return audit_token("MINT", rpc_url="url")


def test_clean_token_verdict_is_pass(monkeypatch):
    # concentration returns UNKNOWN but is INFO-only, so it must not gate the verdict
    monkeypatch.setattr(keeper_audit, "check_concentration",
                        lambda *a, **k: {"name": "top-10 holders", "status": INFO, "detail": "x"})
    assert _audit_with(monkeypatch)["verdict"] == PASS


def test_any_failure_makes_the_verdict_fail(monkeypatch):
    monkeypatch.setattr(keeper_audit, "check_concentration",
                        lambda *a, **k: {"name": "top-10 holders", "status": INFO, "detail": "x"})
    assert _audit_with(monkeypatch, mint_active=True)["verdict"] == FAIL


def test_unknown_check_blocks_a_pass(monkeypatch):
    monkeypatch.setattr(keeper_audit, "check_concentration",
                        lambda *a, **k: {"name": "top-10 holders", "status": UNKNOWN, "detail": "x"})
    assert _audit_with(monkeypatch)["verdict"] == UNKNOWN


# ------------------------------------------------------------------- receipts

def test_receipts_refuses_to_render_on_a_failed_audit():
    out = render_receipts({"verdict": FAIL, "mint": "M", "lp_mint": None, "dev_wallet": None})
    assert "Not generating" in out
    assert "revoked" not in out


def test_receipts_only_claims_what_was_checked():
    result = {"verdict": PASS, "mint": "M", "lp_mint": None, "dev_wallet": None}
    out = render_receipts(result, "$KEEPER")
    assert "mint authority: revoked" in out
    # no LP mint was supplied, so the post must not claim the LP was burned
    assert "LP: burned" not in out
    assert "dev allocation" not in out


def test_receipts_includes_lp_and_dev_lines_when_checked():
    result = {"verdict": PASS, "mint": "M", "lp_mint": "LP", "dev_wallet": "DEV"}
    out = render_receipts(result, "$KEEPER")
    assert "LP: burned" in out
    # the wallet is named, not just the number - that is the point of the line
    assert "dev wallet: DEV - holds 0" in out


# ------------------------------------------------------------------------ log

def _result(mint="M", verdict=PASS):
    return {"checked_at": "2026-09-15T09:00:00+00:00", "mint": mint, "lp_mint": None,
            "dev_wallet": None, "verdict": verdict, "checks": []}


def test_log_chain_verifies(tmp_path):
    p = str(tmp_path / "log.jsonl")
    append_log(_result("A"), p)
    append_log(_result("B"), p)
    append_log(_result("C"), p)
    state = verify_log(p)
    assert state["ok"] is True
    assert state["entries"] == 3


def test_editing_an_old_entry_breaks_the_chain(tmp_path):
    p = str(tmp_path / "log.jsonl")
    append_log(_result("A", FAIL), p)
    append_log(_result("B"), p)

    lines = open(p, encoding="utf-8").read().splitlines()
    first = json.loads(lines[0])
    first["verdict"] = PASS          # rewriting history
    lines[0] = json.dumps(first, sort_keys=True)
    open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    state = verify_log(p)
    assert state["ok"] is False
    assert state["broken_at"] == 0


def test_deleting_an_entry_breaks_the_chain(tmp_path):
    p = str(tmp_path / "log.jsonl")
    append_log(_result("A"), p)
    append_log(_result("B"), p)
    append_log(_result("C"), p)

    lines = open(p, encoding="utf-8").read().splitlines()
    del lines[1]                      # quietly dropping a run
    open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    assert verify_log(p)["ok"] is False


def test_missing_log_is_not_ok(tmp_path):
    assert verify_log(str(tmp_path / "nope.jsonl"))["ok"] is False


def test_rate_limited_holder_check_does_not_block_a_pass(monkeypatch):
    """A flaky public RPC must not stop a clean launch - concentration is INFO only."""
    _patch_mint(monkeypatch, _mint_bytes(False, False))
    monkeypatch.setattr(keeper_audit, "rpc_call", lambda *a, **k: {"_error": "rate limited (429)"})
    result = audit_token("MINT", rpc_url="url")
    conc = [c for c in result["checks"] if c["name"] == "top-10 holders"][0]
    assert conc["status"] == INFO
    assert result["verdict"] == PASS


# --------------------------------------------- declared (non-zero) allocation

def test_declared_allocation_within_promise_passes(monkeypatch):
    monkeypatch.setattr(keeper_audit, "rpc_call", lambda *a, **k: {"value": [
        {"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": 30_000_000}}}}}}
    ]})
    check = check_dev_holdings("MINT", "DEV", "url", declared_pct=3.0, supply=1_000_000_000)
    assert check["status"] == PASS
    assert "3.00%" in check["detail"]


def test_holding_more_than_declared_fails(monkeypatch):
    monkeypatch.setattr(keeper_audit, "rpc_call", lambda *a, **k: {"value": [
        {"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": 90_000_000}}}}}}
    ]})
    check = check_dev_holdings("MINT", "DEV", "url", declared_pct=3.0, supply=1_000_000_000)
    assert check["status"] == FAIL
    assert "OVER the public commitment" in check["detail"]


def test_declaring_zero_but_holding_fails(monkeypatch):
    monkeypatch.setattr(keeper_audit, "rpc_call", lambda *a, **k: {"value": [
        {"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": 1}}}}}}
    ]})
    assert check_dev_holdings("MINT", "DEV", "url")["status"] == FAIL


def test_receipts_quote_the_measured_holding_not_the_promise():
    """The post must state what the chain says, with the promise as context."""
    out = render_receipts({"verdict": PASS, "mint": "M", "lp_mint": None,
                           "dev_wallet": "DEVWALLET", "declared_pct": 3.0,
                           "lock_until": "2026-12-15",
                           "checks": [{"name": "dev allocation", "held_pct": 2.41}]},
                          "$KEEPER")
    assert "holds 2.41%" in out
    assert "declared 3% before launch" in out
    assert "not selling before 2026-12-15" in out


# ------------------------------------------------------------- lock compliance

def _logged(tmp_path, mint, wallet, held_pct):
    p = str(tmp_path / "log.jsonl")
    append_log({"checked_at": "2026-09-15T09:00:00+00:00", "mint": mint,
                "lp_mint": None, "dev_wallet": wallet, "verdict": PASS,
                "checks": [{"name": "dev allocation", "status": PASS,
                            "held_pct": held_pct, "detail": ""}]}, p)
    return p


def test_selling_during_the_lock_is_caught(tmp_path):
    p = _logged(tmp_path, "M", "DEV", 3.00)
    check = keeper_audit.check_lock_compliance("M", "DEV", 1.10, "2099-12-15", p)
    assert check["status"] == FAIL
    assert "SOLD DURING LOCK" in check["detail"]


def test_holding_intact_during_the_lock_passes(tmp_path):
    p = _logged(tmp_path, "M", "DEV", 3.00)
    check = keeper_audit.check_lock_compliance("M", "DEV", 3.00, "2099-12-15", p)
    assert check["status"] == PASS


def test_after_the_lock_expires_selling_is_not_a_failure(tmp_path):
    p = _logged(tmp_path, "M", "DEV", 3.00)
    check = keeper_audit.check_lock_compliance("M", "DEV", 0.20, "2020-01-01", p)
    assert check["status"] == INFO
    assert "lock ended" in check["detail"]


def test_no_prior_log_says_so_rather_than_passing_silently(tmp_path):
    check = keeper_audit.check_lock_compliance("M", "DEV", 3.0, "2099-12-15",
                                               str(tmp_path / "none.jsonl"))
    assert check["status"] == INFO
    assert "nothing to compare" in check["detail"]


def test_a_malformed_lock_date_is_unknown_not_pass(tmp_path):
    check = keeper_audit.check_lock_compliance("M", "DEV", 3.0, "next tuesday",
                                               str(tmp_path / "none.jsonl"))
    assert check["status"] == UNKNOWN


# ------------------------------------------------------------- ops wallets

def test_ops_wallet_is_reported_never_failed(monkeypatch):
    """A disclosed ops wallet is expected to sell - it must not gate the verdict."""
    monkeypatch.setattr(keeper_audit, "rpc_call", lambda *a, **k: {"value": [
        {"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": 5_000_000}}}}}}
    ]})
    check = keeper_audit.check_ops_wallet("MINT", "OPS1", "url", supply=1_000_000_000)
    assert check["status"] == INFO
    assert "0.50% of supply" in check["detail"]
    assert "disclosed" in check["detail"]


def test_emptied_ops_wallet_reads_as_spent(monkeypatch):
    monkeypatch.setattr(keeper_audit, "rpc_call", lambda *a, **k: {"value": []})
    check = keeper_audit.check_ops_wallet("MINT", "OPS1", "url")
    assert check["status"] == INFO
    assert "holds 0" in check["detail"]


def test_ops_wallets_do_not_change_a_pass_verdict(monkeypatch):
    _patch_mint(monkeypatch, _mint_bytes(False, False))
    monkeypatch.setattr(keeper_audit, "rpc_call", lambda *a, **k: {"value": [
        {"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": 9_999_999}}}}}}
    ]})
    result = audit_token("MINT", rpc_url="url", ops_wallets=["OPS1", "OPS2"])
    assert result["verdict"] == PASS
    assert len([c for c in result["checks"] if c["name"].startswith("ops wallet")]) == 2


def test_malformed_rpc_response_does_not_crash_the_audit(monkeypatch):
    """A weird response from the public RPC must degrade, not take the run down."""
    _patch_mint(monkeypatch, _mint_bytes(False, False))
    monkeypatch.setattr(keeper_audit, "rpc_call",
                        lambda *a, **k: {"value": ["unexpected", "shape"]})
    result = audit_token("MINT", rpc_url="url")
    conc = [c for c in result["checks"] if c["name"] == "top-10 holders"][0]
    assert conc["status"] == INFO
    assert result["verdict"] == PASS


# --------------------------------------------- SOL-denominated promise

def test_sol_promise_reports_the_holding_and_does_not_fail(monkeypatch):
    """'I bought 2 SOL worth' is not a cap - the lock is what gets enforced."""
    monkeypatch.setattr(keeper_audit, "rpc_call", lambda *a, **k: {"value": [
        {"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": 41_000_000}}}}}}
    ]})
    check = check_dev_holdings("MINT", "DEV", "url", declared_pct=0,
                               supply=1_000_000_000, declared_sol=2)
    assert check["status"] == INFO
    assert "4.10% of supply" in check["detail"]
    assert "2 SOL bought at launch" in check["detail"]
    assert round(check["held_pct"], 4) == 4.1


def test_sol_promise_never_claims_a_percentage_was_declared():
    out = render_receipts({"verdict": PASS, "mint": "M", "lp_mint": None,
                           "dev_wallet": "DEVW", "declared_pct": 0,
                           "declared_sol": 2, "lock_until": "2026-10-15",
                           "checks": [{"name": "dev allocation", "held_pct": 4.1}]},
                          "$KEEPER")
    assert "2 SOL bought at launch, now 4.10% of supply" in out
    assert "Nothing sold before 2026-10-15" in out
    # the exact failure this replaced: claiming a percentage that was never promised
    assert "declared" not in out.lower()


def test_declaring_nothing_at_all_still_fails_on_a_holding(monkeypatch):
    monkeypatch.setattr(keeper_audit, "rpc_call", lambda *a, **k: {"value": [
        {"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": 5}}}}}}
    ]})
    check = check_dev_holdings("MINT", "DEV", "url", declared_pct=0, declared_sol=0)
    assert check["status"] == FAIL
