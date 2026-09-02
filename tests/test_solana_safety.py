import base64
import struct

import solana_safety
from solana_safety import assess_risk_flags, fetch_mint_info


def _build_mint_account_bytes(mint_authority_active: bool, freeze_authority_active: bool, decimals: int = 9) -> bytes:
    """Builds a byte-accurate fake SPL Token Mint account (82 bytes)."""
    raw = bytearray(82)
    struct.pack_into("<I", raw, 0, 1 if mint_authority_active else 0)
    raw[44] = decimals
    raw[45] = 1  # is_initialized
    struct.pack_into("<I", raw, 46, 1 if freeze_authority_active else 0)
    return bytes(raw)


def _fake_response(value):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"result": {"value": value}}

    return FakeResponse()


def test_fetch_mint_info_parses_authorities_correctly(monkeypatch):
    raw = _build_mint_account_bytes(mint_authority_active=True, freeze_authority_active=False)
    data_b64 = base64.b64encode(raw).decode()
    monkeypatch.setattr(
        solana_safety.requests, "post",
        lambda *a, **k: _fake_response({"data": [data_b64, "base64"]}),
    )

    info = fetch_mint_info("FAKE_MINT")

    assert info["exists"] is True
    assert info["parseable"] is True
    assert info["mint_authority_active"] is True
    assert info["freeze_authority_active"] is False
    assert info["decimals"] == 9


def test_fetch_mint_info_matches_known_wrapped_sol_bytes(monkeypatch):
    """Real base64 data captured from Solana's public RPC for the Wrapped SOL mint - both authorities revoked."""
    real_wsol_data = (
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
    )
    monkeypatch.setattr(
        solana_safety.requests, "post",
        lambda *a, **k: _fake_response({"data": [real_wsol_data, "base64"]}),
    )

    info = fetch_mint_info("So11111111111111111111111111111111111111112")

    assert info["mint_authority_active"] is False
    assert info["freeze_authority_active"] is False
    assert info["decimals"] == 9


def test_fetch_mint_info_handles_missing_account(monkeypatch):
    monkeypatch.setattr(solana_safety.requests, "post", lambda *a, **k: _fake_response(None))

    info = fetch_mint_info("DOES_NOT_EXIST")

    assert info == {"exists": False}


def test_fetch_mint_info_flags_unparseable_non_classic_layout(monkeypatch):
    short_data = base64.b64encode(b"\x00" * 10).decode()
    monkeypatch.setattr(
        solana_safety.requests, "post",
        lambda *a, **k: _fake_response({"data": [short_data, "base64"]}),
    )

    info = fetch_mint_info("TOKEN_2022_EXAMPLE")

    assert info == {"exists": True, "parseable": False}


def test_assess_risk_flags_reports_both_authorities():
    flags = assess_risk_flags({
        "exists": True, "parseable": True,
        "mint_authority_active": True, "freeze_authority_active": True, "decimals": 6,
    })
    assert len(flags) == 2
    assert any("mint authority" in f for f in flags)
    assert any("freeze authority" in f for f in flags)


def test_assess_risk_flags_empty_when_both_revoked():
    flags = assess_risk_flags({
        "exists": True, "parseable": True,
        "mint_authority_active": False, "freeze_authority_active": False, "decimals": 6,
    })
    assert flags == []


def test_assess_risk_flags_handles_missing_and_unparseable():
    assert assess_risk_flags({"exists": False}) == ["mint account not found on-chain"]
    assert assess_risk_flags({"exists": True, "parseable": False}) == [
        "non-standard mint layout (e.g. Token-2022 extensions) - not checked"
    ]
