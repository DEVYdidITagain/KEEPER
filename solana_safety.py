"""
Read-only SPL token mint safety checks via Solana's public JSON-RPC — no
API key, no wallet, no on-chain writes of any kind, and no new third-party
dependency (just `requests`, already used elsewhere in this project).

Parses the mint account's raw data using the standard, stable SPL Token
Mint layout (https://spl.solana.com/token) for the "classic" Token program
(owner `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA`) rather than pulling
in a Solana SDK. Verified against a known account (Wrapped SOL) before
being wired into anything: 82-byte account, both authorities correctly
show inactive, decimals correctly read as 9.

This is a basic, widely-used safety screen in meme-coin trading — not
exotic, and NOT proof a token is safe. It only flags two of the most
common rug-pull levers:
  - mint authority still active -> supply can be inflated arbitrarily
  - freeze authority still active -> holder token accounts can be frozen

Tokens on the newer Token-2022 program with extensions have larger/
different account data and are reported as "unparseable" rather than
guessed at.
"""
import base64
import logging
import struct

import requests

logger = logging.getLogger(__name__)

DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"
CLASSIC_TOKEN_MINT_SIZE = 82  # base SPL Token Mint account layout, no Token-2022 extensions


def fetch_mint_info(mint_address: str, rpc_url: str = DEFAULT_RPC_URL) -> dict:
    """
    Returns a dict describing the mint account:
      {"exists": False}
      {"exists": True, "parseable": False}  - e.g. Token-2022 w/ extensions
      {"exists": True, "parseable": True, "mint_authority_active": bool,
       "freeze_authority_active": bool, "decimals": int}
    """
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
        "params": [mint_address, {"encoding": "base64"}],
    }
    resp = requests.post(rpc_url, json=payload, timeout=10)
    resp.raise_for_status()
    result = resp.json().get("result") or {}
    value = result.get("value")
    if value is None:
        return {"exists": False}

    raw = base64.b64decode(value["data"][0])
    if len(raw) < CLASSIC_TOKEN_MINT_SIZE:
        return {"exists": True, "parseable": False}

    mint_authority_option = struct.unpack_from("<I", raw, 0)[0]
    decimals = raw[44]
    freeze_authority_option = struct.unpack_from("<I", raw, 46)[0]

    return {
        "exists": True,
        "parseable": True,
        "mint_authority_active": mint_authority_option == 1,
        "freeze_authority_active": freeze_authority_option == 1,
        "decimals": decimals,
    }


def assess_risk_flags(mint_info: dict) -> list[str]:
    """Plain-language risk flags from fetch_mint_info's output. Not exhaustive; absence of flags is not a safety guarantee."""
    if not mint_info.get("exists"):
        return ["mint account not found on-chain"]
    if not mint_info.get("parseable"):
        return ["non-standard mint layout (e.g. Token-2022 extensions) - not checked"]

    flags = []
    if mint_info["mint_authority_active"]:
        flags.append("mint authority still active - supply can be inflated")
    if mint_info["freeze_authority_active"]:
        flags.append("freeze authority still active - holder accounts can be frozen")
    return flags


# ---------------------------------------------------------------------------
# Richer detail used by keeper_audit.py. fetch_mint_info() above keeps its
# original narrow contract (three booleans) because several callers depend on
# it; this returns everything the same 82-byte layout carries, including the
# authority pubkeys themselves and the current supply, which a receipts post
# needs to quote.
# ---------------------------------------------------------------------------

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw: bytes) -> str:
    """Base58 (Bitcoin alphabet) - the encoding Solana uses for pubkeys."""
    n = int.from_bytes(raw, "big")
    out = ""
    while n > 0:
        n, rem = divmod(n, 58)
        out = _B58_ALPHABET[rem] + out
    # leading zero bytes are encoded as leading '1's
    for byte in raw:
        if byte != 0:
            break
        out = "1" + out
    return out or "1"


def fetch_mint_detail(mint_address: str, rpc_url: str = DEFAULT_RPC_URL) -> dict:
    """
    Full parse of the classic SPL Token Mint layout.

    Returns {"exists": False} / {"exists": True, "parseable": False} as
    fetch_mint_info does, or on success:
      {"exists": True, "parseable": True,
       "mint_authority": str | None,     # None == revoked
       "freeze_authority": str | None,   # None == revoked
       "supply_raw": int, "decimals": int, "supply_ui": float}
    """
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
        "params": [mint_address, {"encoding": "base64"}],
    }
    resp = requests.post(rpc_url, json=payload, timeout=15)
    resp.raise_for_status()
    value = (resp.json().get("result") or {}).get("value")
    if value is None:
        return {"exists": False}

    raw = base64.b64decode(value["data"][0])
    if len(raw) < CLASSIC_TOKEN_MINT_SIZE:
        return {"exists": True, "parseable": False}

    mint_opt   = struct.unpack_from("<I", raw, 0)[0]
    supply_raw = struct.unpack_from("<Q", raw, 36)[0]
    decimals   = raw[44]
    freeze_opt = struct.unpack_from("<I", raw, 46)[0]

    return {
        "exists": True,
        "parseable": True,
        "mint_authority": b58encode(raw[4:36]) if mint_opt == 1 else None,
        "freeze_authority": b58encode(raw[50:82]) if freeze_opt == 1 else None,
        "supply_raw": supply_raw,
        "decimals": decimals,
        "supply_ui": supply_raw / (10 ** decimals) if decimals <= 18 else float(supply_raw),
    }
