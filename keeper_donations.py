"""
Reads a donation wallet's incoming and outgoing SOL so a public page can show
where creator fees went.

What this can and cannot prove, stated plainly because the page repeats it:
  - CAN prove: SOL arrived in the wallet, and SOL left it, to which address,
    when, and for how much. All of that is on-chain and checkable by anyone.
  - CANNOT prove: that the recipient banked it, or that an off-ramp actually
    delivered fiat to a real organisation. That half needs the recipient's own
    acknowledgement. A page that implies otherwise is overstating.

Balances come from the transaction's own pre/post lamport arrays rather than a
separate balance call, so each entry reflects the state at that block instead
of a later snapshot. Uses only the public JSON-RPC and requests.
"""
import logging
import time
from datetime import datetime, timezone

from keeper_audit import rpc_call
from solana_safety import DEFAULT_RPC_URL

logger = logging.getLogger(__name__)

LAMPORTS = 1_000_000_000


def fetch_transfers(wallet: str, rpc_url: str = DEFAULT_RPC_URL,
                    max_txns: int = 40, pause: float = 0.25) -> list[dict]:
    """
    Recent SOL movements for `wallet`, newest first.

    Each entry: {"signature", "time" (ISO or None), "direction" in/out,
                 "sol", "counterparty" or None, "fee_only" bool}

    `fee_only` marks a transaction where the only change was the network fee -
    those are noise on a donation page and the renderer drops them.
    """
    sigs = rpc_call("getSignaturesForAddress", [wallet, {"limit": max_txns}], rpc_url)
    if not isinstance(sigs, list):
        logger.warning("could not list signatures for %s: %s", wallet, sigs)
        return []

    out = []
    for entry in sigs:
        if entry.get("err"):
            continue
        time.sleep(pause)
        tx = rpc_call("getTransaction",
                      [entry["signature"],
                       {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
                      rpc_url)
        if not isinstance(tx, dict) or "_error" in tx or not tx:
            continue

        meta = tx.get("meta") or {}
        msg = (tx.get("transaction") or {}).get("message") or {}
        keys = [k.get("pubkey") if isinstance(k, dict) else k
                for k in (msg.get("accountKeys") or [])]
        pre, post = meta.get("preBalances") or [], meta.get("postBalances") or []
        if wallet not in keys or len(pre) != len(keys) or len(post) != len(keys):
            continue

        i = keys.index(wallet)
        delta = post[i] - pre[i]
        fee = meta.get("fee", 0)

        # a transaction whose only effect on us was paying the fee
        if delta < 0 and abs(delta) <= fee:
            direction, sol, fee_only = "out", abs(delta) / LAMPORTS, True
        elif delta > 0:
            direction, sol, fee_only = "in", delta / LAMPORTS, False
        elif delta < 0:
            direction, sol, fee_only = "out", (abs(delta) - fee) / LAMPORTS, False
        else:
            continue

        counterparty = None
        if direction == "out":
            gains = [(post[j] - pre[j], keys[j]) for j in range(len(keys))
                     if j != i and post[j] > pre[j]]
            if gains:
                counterparty = max(gains)[1]
        else:
            losses = [(pre[j] - post[j], keys[j]) for j in range(len(keys))
                      if j != i and pre[j] > post[j]]
            if losses:
                counterparty = max(losses)[1]

        bt = entry.get("blockTime")
        out.append({
            "signature": entry["signature"],
            "time": datetime.fromtimestamp(bt, timezone.utc).isoformat(timespec="minutes")
                    if bt else None,
            "direction": direction,
            "sol": round(sol, 6),
            "counterparty": counterparty,
            "fee_only": fee_only,
        })
    return out


def summarise(transfers: list[dict]) -> dict:
    """Totals, ignoring fee-only noise."""
    real = [t for t in transfers if not t["fee_only"]]
    received = sum(t["sol"] for t in real if t["direction"] == "in")
    sent = sum(t["sol"] for t in real if t["direction"] == "out")
    return {
        "received": round(received, 6),
        "sent": round(sent, 6),
        "pending": round(max(received - sent, 0.0), 6),
        "payouts": [t for t in real if t["direction"] == "out"],
        "count_in": sum(1 for t in real if t["direction"] == "in"),
    }
