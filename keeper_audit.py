"""
Pre-launch and post-launch audit for a Solana SPL token, plus a tamper-evident
record that the audit actually happened.

Two jobs, deliberately kept in one place:

1. CHECK - reads a mint over the public JSON-RPC and answers the four questions
   a buyer actually cares about: can the dev still print supply, can the dev
   freeze wallets, is the LP burned, does the dev hold any of it. Nothing here
   writes to the chain, needs a key, or touches a wallet.

2. PROVE - every run can be appended to a hash-chained log (audit_log.jsonl).
   Each entry carries the SHA-256 of the previous entry, so an earlier record
   cannot be quietly edited after the fact without breaking every hash that
   follows it. This is what turns "I checked before launch" from a claim into
   something a stranger can verify.

The chain proves the log is INTERNALLY consistent and unedited since writing.
It does not prove when an entry was written - only that the sequence hasn't
been rewritten. For an external timestamp, publish a chain hash somewhere
public (a post) and the log is anchored from that moment on. `--anchor` prints
the line to post.

Reuses solana_safety.fetch_mint_detail for the mint layout parse rather than
re-implementing it. No new third-party dependency: requests only.
"""
import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import requests

from solana_safety import DEFAULT_RPC_URL, fetch_mint_detail

logger = logging.getLogger(__name__)

DEFAULT_LOG_PATH = "audit_log.jsonl"
INCINERATOR = "1nc1nerator11111111111111111111111111111111"

PASS, FAIL, UNKNOWN, INFO = "PASS", "FAIL", "UNKNOWN", "INFO"


# --------------------------------------------------------------------------
# RPC
# --------------------------------------------------------------------------

def rpc_call(method: str, params: list, rpc_url: str = DEFAULT_RPC_URL,
             attempts: int = 4) -> dict:
    """
    One JSON-RPC call with backoff. The public endpoint rate-limits hard under
    load (this project has hit real 429s on it before), so retries are not
    optional here.
    """
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    delay = 0.6
    last = None
    for attempt in range(attempts):
        try:
            resp = requests.post(rpc_url, json=payload, timeout=20)
            if resp.status_code == 429:
                last = "rate limited (429)"
                time.sleep(delay)
                delay *= 2
                continue
            resp.raise_for_status()
            body = resp.json()
            if "error" in body:
                return {"_error": body["error"].get("message", "rpc error")}
            return body.get("result") or {}
        except requests.RequestException as exc:
            last = str(exc)
            time.sleep(delay)
            delay *= 2
    return {"_error": last or "rpc unavailable"}


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------

def check_authorities(mint: str, rpc_url: str) -> list[dict]:
    detail = fetch_mint_detail(mint, rpc_url)

    if not detail.get("exists"):
        return [{"name": "mint account", "status": FAIL,
                 "detail": "no account found at this address on mainnet"}]
    if not detail.get("parseable"):
        return [{"name": "mint account", "status": UNKNOWN,
                 "detail": "non-standard layout (likely Token-2022 with "
                           "extensions) - not parsed, check manually"}]

    checks = []
    ma = detail["mint_authority"]
    checks.append({
        "name": "mint authority",
        "status": PASS if ma is None else FAIL,
        "detail": "revoked" if ma is None
                  else f"STILL ACTIVE - held by {ma}, supply can be inflated",
    })

    fa = detail["freeze_authority"]
    checks.append({
        "name": "freeze authority",
        "status": PASS if fa is None else FAIL,
        "detail": "revoked" if fa is None
                  else f"STILL ACTIVE - held by {fa}, wallets can be frozen",
    })

    checks.append({
        "name": "supply",
        "status": INFO,
        "detail": f"{detail['supply_ui']:,.0f} ({detail['decimals']} decimals)",
    })
    return checks


def check_lp_burned(lp_mint: str, rpc_url: str) -> dict:
    """
    LP tokens are burned when the LP mint's supply is zero. A non-zero supply
    means someone still holds the LP and can pull liquidity.
    """
    detail = fetch_mint_detail(lp_mint, rpc_url)
    if not detail.get("exists"):
        return {"name": "LP burned", "status": UNKNOWN,
                "detail": f"no account at LP mint {lp_mint}"}
    if not detail.get("parseable"):
        return {"name": "LP burned", "status": UNKNOWN,
                "detail": "LP mint has a non-standard layout - check manually"}

    supply = detail["supply_raw"]
    if supply == 0:
        return {"name": "LP burned", "status": PASS,
                "detail": "LP mint supply is 0 - all LP tokens burned"}
    return {"name": "LP burned", "status": FAIL,
            "detail": f"LP supply is {detail['supply_ui']:,.4f} - liquidity "
                      f"can still be pulled"}


def check_dev_holdings(mint: str, dev_wallet: str, rpc_url: str,
                       declared_pct: float = 0.0, supply: float = 0.0,
                       declared_sol: float = 0.0) -> dict:
    """
    Checks the dev wallet against what the dev PUBLICLY DECLARED it would hold,
    not against zero. A disclosed allocation is honest; the failure mode this
    guards against is holding more than you said you would.

    Three promise shapes, three behaviours - see the comment in the body.
    """
    result = rpc_call(
        "getTokenAccountsByOwner",
        [dev_wallet, {"mint": mint}, {"encoding": "jsonParsed"}],
        rpc_url,
    )
    if "_error" in result:
        return {"name": "dev allocation", "status": UNKNOWN,
                "detail": f"could not read wallet: {result['_error']}"}

    total = 0.0
    for acct in result.get("value", []):
        info = acct["account"]["data"]["parsed"]["info"]["tokenAmount"]
        total += float(info.get("uiAmount") or 0)

    held_pct_now = (total / supply * 100) if supply > 0 else None

    # Three honest shapes a promise can take, and the check differs for each:
    #   declared_pct > 0            -> "I hold no more than N%"  : a cap, can FAIL
    #   declared_sol > 0            -> "I bought N SOL worth"    : measured, the
    #                                  lock check does the enforcing
    #   neither                     -> "I hold none"             : FAIL on anything
    if declared_pct <= 0 and declared_sol > 0:
        shown = (f"{held_pct_now:.2f}% of supply" if held_pct_now is not None
                 else f"{total:,.0f} tokens")
        return {"name": "dev allocation", "status": INFO, "held_pct": held_pct_now,
                "detail": f"{shown} from the {declared_sol:g} SOL bought at launch "
                          f"- no cap was promised, the lock is what was promised"}

    if declared_pct <= 0:
        if total == 0:
            return {"name": "dev allocation", "status": PASS, "held_pct": 0.0,
                    "detail": f"{dev_wallet} holds 0, as declared"}
        return {"name": "dev allocation", "status": FAIL, "held_pct": None,
                "detail": f"declared 0 but {dev_wallet} holds {total:,.0f}"}

    if supply <= 0:
        return {"name": "dev allocation", "status": UNKNOWN,
                "detail": "supply unknown - cannot check the declared percentage"}

    held_pct = total / supply * 100
    # a small tolerance: fees and rounding shouldn't fail an honest wallet
    if held_pct <= declared_pct + 0.10:
        return {"name": "dev allocation", "status": PASS, "held_pct": held_pct,
                "detail": f"holds {held_pct:.2f}% - declared {declared_pct:.2f}%, "
                          f"within what was promised"}
    return {"name": "dev allocation", "status": FAIL, "held_pct": held_pct,
            "detail": f"holds {held_pct:.2f}% but declared {declared_pct:.2f}% - "
                      f"OVER the public commitment"}


def check_ops_wallet(mint: str, wallet: str, rpc_url: str,
                     supply: float = 0.0, label: str = "ops wallet") -> dict:
    """
    An operations wallet is DISCLOSED, not promised. It is expected to sell -
    that is what it is for - so it is reported as INFO and never gates the
    verdict. Its whole job on the page is to be visible, so that a sale from it
    is something the dev already told you about rather than something you found.
    """
    result = rpc_call(
        "getTokenAccountsByOwner",
        [wallet, {"mint": mint}, {"encoding": "jsonParsed"}],
        rpc_url,
    )
    if "_error" in result:
        return {"name": label, "status": INFO,
                "detail": f"{wallet} - could not read ({result['_error']})"}

    total = 0.0
    for acct in result.get("value", []):
        info = acct["account"]["data"]["parsed"]["info"]["tokenAmount"]
        total += float(info.get("uiAmount") or 0)

    if total == 0:
        return {"name": label, "status": INFO,
                "detail": f"{wallet} - holds 0 (spent or not yet bought)"}

    pct = f", {total / supply * 100:.2f}% of supply" if supply > 0 else ""
    return {"name": label, "status": INFO,
            "detail": f"{wallet} - holds {total:,.0f}{pct}, disclosed as an "
                      f"operations wallet"}


def check_concentration(mint: str, rpc_url: str) -> dict:
    """
    Top-10 share of supply. Reported, never pass/failed: on a fresh pump.fun
    token the bonding curve or pool account is legitimately the largest holder,
    so a high number here needs a human to look at who the holders are.
    """
    largest = rpc_call("getTokenLargestAccounts", [mint], rpc_url)
    if "_error" in largest:
        return {"name": "top-10 holders", "status": INFO,
                "detail": f"not read ({largest['_error']}) - informational only, "
                          f"does not affect the verdict"}

    accounts = largest.get("value", [])
    if not accounts:
        return {"name": "top-10 holders", "status": INFO,
                "detail": "no holder accounts returned"}

    supply_res = rpc_call("getTokenSupply", [mint], rpc_url)
    if "_error" in supply_res:
        return {"name": "top-10 holders", "status": INFO,
                "detail": f"not read ({supply_res['_error']}) - informational only"}

    # the public RPC occasionally answers with a shape we did not ask for;
    # this check is informational, so degrade rather than take the run down
    value = supply_res.get("value") if isinstance(supply_res, dict) else None
    if not isinstance(value, dict):
        return {"name": "top-10 holders", "status": INFO,
                "detail": "supply response was not in the expected shape - skipped"}

    supply = float(value.get("uiAmount") or 0)
    if supply <= 0:
        return {"name": "top-10 holders", "status": INFO,
                "detail": "supply reported as zero"}

    try:
        top10 = sum(float(a.get("uiAmount") or 0) for a in accounts[:10]
                    if isinstance(a, dict))
    except (TypeError, ValueError):
        return {"name": "top-10 holders", "status": INFO,
                "detail": "holder amounts could not be read - skipped"}
    pct = top10 / supply * 100
    return {"name": "top-10 holders", "status": INFO,
            "detail": f"{pct:.1f}% of supply "
                      f"(pool/bonding-curve accounts count toward this - "
                      f"check who they are before quoting it)"}


def check_lock_compliance(mint: str, dev_wallet: str, held_pct: float | None,
                          lock_until: str | None,
                          log_path: str = DEFAULT_LOG_PATH) -> dict:
    """
    Did the dev sell during the period they publicly promised not to?

    A single snapshot cannot answer that, so this compares the current holding
    against the EARLIEST logged holding for the same mint and wallet. That is
    what the hash-chained log is for: the history is the evidence, and it can't
    be edited after the fact without breaking the chain.
    """
    if not lock_until:
        return {"name": "lock", "status": INFO, "detail": "no lock declared"}

    try:
        deadline = datetime.fromisoformat(lock_until).date()
    except ValueError:
        return {"name": "lock", "status": UNKNOWN,
                "detail": f"could not read lock date '{lock_until}' (use YYYY-MM-DD)"}

    today = datetime.now(timezone.utc).date()
    if today > deadline:
        return {"name": "lock", "status": INFO,
                "detail": f"lock ended {lock_until} - selling is now within what you said"}

    if held_pct is None:
        return {"name": "lock", "status": UNKNOWN,
                "detail": "current holding unknown - cannot check the lock"}

    earliest = None
    if os.path.exists(log_path):
        with open(log_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("mint") != mint or entry.get("dev_wallet") != dev_wallet:
                    continue
                for c in entry.get("checks", []):
                    if c.get("name") == "dev allocation" and c.get("held_pct") is not None:
                        if earliest is None:
                            earliest = c["held_pct"]
                        break

    if earliest is None:
        return {"name": "lock", "status": INFO,
                "detail": f"locked until {lock_until} - no earlier run logged yet, "
                          f"so there is nothing to compare against. Log every run."}

    if held_pct < earliest - 0.05:
        return {"name": "lock", "status": FAIL,
                "detail": f"SOLD DURING LOCK - held {earliest:.2f}% at first check, "
                          f"holds {held_pct:.2f}% now, locked until {lock_until}"}

    return {"name": "lock", "status": PASS,
            "detail": f"holding intact since first check ({earliest:.2f}% -> "
                      f"{held_pct:.2f}%), locked until {lock_until}"}


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------

def audit_token(mint: str, lp_mint: str | None = None,
                dev_wallet: str | None = None,
                rpc_url: str = DEFAULT_RPC_URL,
                declared_pct: float = 0.0,
                declared_sol: float = 0.0,
                lock_until: str | None = None,
                log_path: str = DEFAULT_LOG_PATH,
                ops_wallets: list[str] | None = None) -> dict:
    checks = check_authorities(mint, rpc_url)

    supply = 0.0
    for c in checks:
        if c["name"] == "supply":
            detail = fetch_mint_detail(mint, rpc_url)
            supply = float(detail.get("supply_ui") or 0)

    if lp_mint:
        checks.append(check_lp_burned(lp_mint, rpc_url))
    if dev_wallet:
        alloc = check_dev_holdings(mint, dev_wallet, rpc_url, declared_pct, supply,
                                   declared_sol)
        checks.append(alloc)
        if lock_until:
            checks.append(check_lock_compliance(mint, dev_wallet,
                                                alloc.get("held_pct"), lock_until,
                                                log_path))
    for n, w in enumerate(ops_wallets or [], start=1):
        checks.append(check_ops_wallet(mint, w, rpc_url, supply,
                                       f"ops wallet {n}"))

    checks.append(check_concentration(mint, rpc_url))

    gating = [c for c in checks if c["status"] in (PASS, FAIL, UNKNOWN)]
    if any(c["status"] == FAIL for c in gating):
        verdict = FAIL
    elif any(c["status"] == UNKNOWN for c in gating):
        verdict = UNKNOWN
    else:
        verdict = PASS

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mint": mint,
        "lp_mint": lp_mint,
        "dev_wallet": dev_wallet,
        "ops_wallets": list(ops_wallets or []),
        "verdict": verdict,
        "declared_pct": declared_pct,
        "declared_sol": declared_sol,
        "lock_until": lock_until,
        "checks": checks,
    }


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

_MARK = {PASS: "PASS", FAIL: "FAIL", UNKNOWN: " ?  ", INFO: "  - "}


def render_report(result: dict) -> str:
    lines = [
        "",
        f"  mint      {result['mint']}",
        f"  checked   {result['checked_at']}",
        "",
    ]
    for c in result["checks"]:
        lines.append(f"  [{_MARK[c['status']]}]  {c['name']:<18} {c['detail']}")
    lines += ["", f"  VERDICT   {result['verdict']}"]
    if result["verdict"] == PASS:
        lines.append("            safe to publish receipts")
    elif result["verdict"] == FAIL:
        lines.append("            DO NOT LAUNCH - fix the failures above first")
    else:
        lines.append("            something could not be read - resolve before publishing")
    lines.append("")
    return "\n".join(lines)


def render_receipts(result: dict, ticker: str = "$TOKEN") -> str:
    """The launch post, with only what the audit actually verified."""
    if result["verdict"] != PASS:
        return ("Not generating a receipts post: the audit did not pass.\n"
                "Every line in that post has to be true.")

    mint = result["mint"]
    lines = [
        f"{ticker} is live.",
        "",
        f"CA: {mint}",
        "",
        "mint authority: revoked",
        "freeze authority: revoked",
    ]
    if result["lp_mint"]:
        lines.append("LP: burned")
    if result["dev_wallet"]:
        declared = result.get("declared_pct") or 0
        dsol = result.get("declared_sol") or 0
        held = None
        for c in result.get("checks", []):
            if c["name"] == "dev allocation":
                held = c.get("held_pct")

        if declared <= 0 and dsol > 0:
            shown = f"{held:.2f}% of supply" if held is not None else "unread"
            line = (f"dev wallet: {result['dev_wallet']} - {dsol:g} SOL bought at "
                    f"launch, now {shown}")
            if result.get("lock_until"):
                line += f". Nothing sold before {result['lock_until']}"
            lines.append(line)
        elif declared <= 0:
            lines.append(f"dev wallet: {result['dev_wallet']} - holds 0")
        else:
            # quote what the chain says, not what was promised - the promise is
            # context, the measurement is the claim
            shown = f"{held:.2f}%" if held is not None else "unread"
            line = (f"dev wallet: {result['dev_wallet']} - holds {shown} "
                    f"(declared {declared:g}% before launch)")
            if result.get("lock_until"):
                line += f", not selling before {result['lock_until']}"
            lines.append(line)
    lines += [
        "",
        f"Verify: https://solscan.io/token/{mint}",
        "",
        "Check it before you buy. That goes for anything I ship, including this.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Tamper-evident log
# --------------------------------------------------------------------------

def _entry_hash(entry: dict, prev_hash: str) -> str:
    body = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


def append_log(result: dict, path: str = DEFAULT_LOG_PATH) -> dict:
    prev_hash = "0" * 64
    index = 0
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    prev = json.loads(line)
                    prev_hash = prev["hash"]
                    index = prev["index"] + 1

    entry = dict(result)
    entry["index"] = index
    entry["prev_hash"] = prev_hash
    entry["hash"] = _entry_hash(entry, prev_hash)

    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def verify_log(path: str = DEFAULT_LOG_PATH) -> dict:
    """Walks the chain. Returns {"ok": bool, "entries": int, "broken_at": int|None}."""
    if not os.path.exists(path):
        return {"ok": False, "entries": 0, "broken_at": None,
                "reason": f"no log at {path}"}

    prev_hash = "0" * 64
    count = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            stored = entry.pop("hash")
            if entry["prev_hash"] != prev_hash:
                return {"ok": False, "entries": count,
                        "broken_at": entry["index"],
                        "reason": "prev_hash does not match the entry before it"}
            if _entry_hash(entry, prev_hash) != stored:
                return {"ok": False, "entries": count,
                        "broken_at": entry["index"],
                        "reason": "entry contents were modified after writing"}
            prev_hash = stored
            count += 1
    return {"ok": True, "entries": count, "broken_at": None,
            "head": prev_hash}


def render_anchor(path: str = DEFAULT_LOG_PATH) -> str:
    state = verify_log(path)
    if not state["ok"]:
        return f"Log does not verify ({state.get('reason')}) - nothing to anchor."
    return (f"Audit log, {state['entries']} entries.\n"
            f"sha256 {state['head']}\n\n"
            f"Posting this so the record can't be rewritten later.")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Audit a Solana token and keep a tamper-evident record of it.")
    ap.add_argument("mint", nargs="?", help="token mint address")
    ap.add_argument("--lp-mint", help="LP mint address, to check the LP is burned")
    ap.add_argument("--dev-wallet", help="your wallet, checked against what you declared")
    ap.add_argument("--declared-pct", type=float, default=0.0,
                    help="percent of supply you publicly capped yourself at (default 0)")
    ap.add_argument("--declared-sol", type=float, default=0.0,
                    help="SOL you publicly said you would buy at launch")
    ap.add_argument("--lock-until",
                    help="date you publicly said you would not sell before, e.g. 2026-12-15")
    ap.add_argument("--ticker", default="$TOKEN", help="ticker for the receipts post")
    ap.add_argument("--rpc", default=DEFAULT_RPC_URL)
    ap.add_argument("--log-path", default=DEFAULT_LOG_PATH)
    ap.add_argument("--log", action="store_true", help="append this run to the audit log")
    ap.add_argument("--receipts", action="store_true", help="print the launch post")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--verify-log", action="store_true", help="check the log chain")
    ap.add_argument("--anchor", action="store_true", help="print a post that anchors the log")
    ap.add_argument("--config", default="keeper.config.json",
                    help="JSON file holding your token settings (default keeper.config.json)")
    ap.add_argument("--report", help="write an HTML audit page to this path")
    ap.add_argument("--card", help="write a 1200x675 screenshot card to this path")
    ap.add_argument("--site", help="write the public landing page to this path")
    ap.add_argument("--fee-wallet", help="wallet that creator fees land in, tracked on the report")
    ap.add_argument("--cause", default="", help="who the fees go to, e.g. 'a church in Hampton, SC'")
    ap.add_argument("--ops-wallet", action="append", dest="ops_wallets", default=None,
                    help="a disclosed operations wallet (repeatable); reported, never gated")
    ap.add_argument("--open", action="store_true", dest="open_report",
                    help="open the HTML report in your browser when it is written")
    args = ap.parse_args(argv)

    # Config fills in anything not given on the command line, so the everyday
    # run is just `python keeper_audit.py` with no arguments at all.
    if os.path.exists(args.config):
        try:
            with open(args.config, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (OSError, ValueError) as exc:
            print(f"  Could not read {args.config}: {exc}")
            return 1
        args.mint         = args.mint         or cfg.get("mint")
        args.lp_mint      = args.lp_mint      or cfg.get("lp_mint")
        args.dev_wallet   = args.dev_wallet   or cfg.get("dev_wallet")
        args.lock_until   = args.lock_until   or cfg.get("lock_until")
        args.report       = args.report       or cfg.get("report_path")
        args.card         = args.card         or cfg.get("card_path")
        args.site         = args.site         or cfg.get("site_path")
        args.fee_wallet   = args.fee_wallet   or cfg.get("fee_wallet")
        args.ops_wallets  = args.ops_wallets  or cfg.get("ops_wallets") or []
        if not args.cause:
            args.cause = cfg.get("cause", "")
        if args.declared_pct == 0.0:
            args.declared_pct = float(cfg.get("declared_pct") or 0.0)
        if args.declared_sol == 0.0:
            args.declared_sol = float(cfg.get("declared_sol") or 0.0)
        if args.ticker == "$TOKEN":
            args.ticker = cfg.get("ticker", "$TOKEN")
        if cfg.get("always_log"):
            args.log = True

    if args.verify_log:
        state = verify_log(args.log_path)
        if state["ok"]:
            n = state["entries"]
            print(f"\n  log OK - {n} {'entry' if n == 1 else 'entries'}, chain intact")
            print(f"  head  {state['head']}\n")
            return 0
        print(f"\n  LOG BROKEN - {state.get('reason')}")
        if state["broken_at"] is not None:
            print(f"  first bad entry: index {state['broken_at']}")
        print()
        return 1

    if args.anchor:
        print("\n" + render_anchor(args.log_path) + "\n")
        return 0

    if not args.mint:
        ap.error("a mint address is required (or use --verify-log / --anchor)")

    result = audit_token(args.mint, args.lp_mint, args.dev_wallet, args.rpc,
                         args.declared_pct, args.declared_sol, args.lock_until,
                         args.log_path, args.ops_wallets)

    if args.log:
        entry = append_log(result, args.log_path)
        result["logged_as"] = entry["hash"]

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render_report(result))
        if args.log:
            print(f"  logged    {result['logged_as'][:16]}...  -> {args.log_path}\n")

    donations = None
    if args.fee_wallet:
        from keeper_donations import fetch_transfers, summarise
        print("  reading fee wallet (this takes a moment)...")
        donations = summarise(fetch_transfers(args.fee_wallet, args.rpc))
        print(f"  donations {donations['received']:.4f} SOL in, "
              f"{donations['sent']:.4f} SOL sent on")

    if args.report:
        from keeper_report import render_report as render_html
        state = verify_log(args.log_path) if os.path.exists(args.log_path) else None
        parent = os.path.dirname(os.path.abspath(args.report))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(render_html(result, state, args.ticker, donations,
                                 args.cause, args.fee_wallet or ""))
        print(f"  report    {args.report}")
        if args.open_report:
            import webbrowser
            webbrowser.open("file:///" + os.path.abspath(args.report).replace("\\", "/"))
        print()

    if args.card:
        from keeper_report import render_card
        state = verify_log(args.log_path) if os.path.exists(args.log_path) else None
        parent = os.path.dirname(os.path.abspath(args.card))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.card, "w", encoding="utf-8") as fh:
            fh.write(render_card(result, state, args.ticker))
        print(f"  card      {args.card}  (1200x675, screenshot this)")
        print()

    if args.site:
        from keeper_site import render_site
        cfg_all = {}
        if os.path.exists(args.config):
            with open(args.config, encoding="utf-8") as fh:
                cfg_all = json.load(fh)
        parent = os.path.dirname(os.path.abspath(args.site))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.site, "w", encoding="utf-8") as fh:
            fh.write(render_site(result, args.ticker, donations, args.cause,
                                 cfg_all.get("links") or {},
                                 cfg_all.get("promises") or [],
                                 cfg_all.get("tagline") or
                                 "forty years on this rock. the light goes on at dusk.",
                                 cfg_all.get("pumpfun_url", "")))
        print(f"  site      {args.site}")
        print()

    if args.receipts:
        print("-" * 60)
        print(render_receipts(result, args.ticker))
        print("-" * 60 + "\n")

    return 0 if result["verdict"] == PASS else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(main())
