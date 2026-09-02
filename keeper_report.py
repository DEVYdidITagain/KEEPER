"""
Renders an audit result as a standalone HTML page.

Self-contained on purpose: no external CSS, no fonts, no scripts. It opens
straight off disk with file://, and it can be dropped on any static host as-is
if you ever want the audit to be public. Same palette as the lighthouse art so
it reads as part of the same project rather than a tool someone bolted on.

Everything interpolated into the page goes through esc() - the details come
from chain data and a config file, and neither belongs in a page unescaped.
"""
from datetime import datetime, timezone
from html import escape as esc

PALETTE = {
    "ground": "#0E1519", "surface": "#151F24", "alt": "#1C282E",
    "ink": "#E4EBED", "soft": "#9FB1B8", "faint": "#68797F",
    "rule": "#24333A", "lamp": "#E8A33D", "sea": "#6BB3C9",
    "good": "#5FBF8F", "bad": "#E06B58",
}

_STATUS_COLOR = {"PASS": "good", "FAIL": "bad", "UNKNOWN": "lamp", "INFO": "faint"}
_STATUS_LABEL = {"PASS": "PASS", "FAIL": "FAIL", "UNKNOWN": "UNREAD", "INFO": "INFO"}


def _verdict_block(verdict: str) -> tuple[str, str, str]:
    if verdict == "PASS":
        return PALETTE["good"], "ALL CHECKS PASS", "Everything you have publicly promised is currently true on-chain."
    if verdict == "FAIL":
        return PALETTE["bad"], "CHECK FAILED", "At least one public commitment does not match the chain. Do not publish receipts."
    return PALETTE["lamp"], "INCOMPLETE", "Something could not be read. Resolve it before making any claim that depends on it."


def render_report(result: dict, log_state: dict | None = None,
                  ticker: str = "$TOKEN", donations: dict | None = None,
                  cause: str = "", donation_wallet: str = "") -> str:
    p = PALETTE
    colour, headline, subline = _verdict_block(result["verdict"])

    rows = []
    for c in result.get("checks", []):
        col = p[_STATUS_COLOR.get(c["status"], "faint")]
        rows.append(f'''      <tr>
        <td class="st" style="color:{col}">{esc(_STATUS_LABEL.get(c["status"], c["status"]))}</td>
        <td class="nm">{esc(c["name"])}</td>
        <td class="dt">{esc(str(c["detail"]))}</td>
      </tr>''')

    declared = result.get("declared_pct") or 0
    lock = result.get("lock_until")

    promises = []
    if result.get("dev_wallet"):
        if declared > 0:
            promises.append(f"Holds no more than <b>{declared:g}%</b> of supply")
        else:
            promises.append("Holds <b>none</b> of the supply")
    if lock:
        promises.append(f"Sells <b>nothing before {esc(str(lock))}</b>")
    promises.append("Mint and freeze authority <b>revoked</b>")

    chain_line = ""
    if log_state and log_state.get("ok"):
        n = log_state["entries"]
        chain_line = (f'<p class="chain">Audit log: <b>{n}</b> '
                      f'{"entry" if n == 1 else "entries"}, chain intact.'
                      f'<br><span class="hash">'
                      f'{esc(log_state.get("head", "")[:32])}…</span></p>')
    elif log_state:
        chain_line = (f'<p class="chain" style="color:{p["bad"]}">Audit log does not '
                      f'verify: {esc(str(log_state.get("reason", "unknown")))}</p>')

    donations_block = ""
    if donations is not None:
        rows_d = []
        for t in donations.get("payouts", [])[:12]:
            when = (t["time"] or "")[:16].replace("T", " ")
            to = t["counterparty"] or "unknown"
            rows_d.append(
                f'<tr><td class="st" style="color:{p["good"]}">{t["sol"]:.4f} SOL</td>'
                f'<td class="nm">{esc(when)}</td>'
                f'<td class="dt"><span class="mono">{esc(to)}</span></td></tr>')
        if not rows_d:
            rows_d.append(f'<tr><td class="dt" colspan="3">No payouts sent yet. '
                          f'Fees collected so far are sitting in the wallet below.</td></tr>')

        cause_line = f" to {esc(cause)}" if cause else ""
        donations_block = f'''
  <h3>Creator fees{cause_line}</h3>
  <div class="tiles">
    <div class="tile"><div class="n">{donations.get("received", 0):.4f}</div><div class="l">SOL received</div></div>
    <div class="tile"><div class="n" style="color:{p["good"]}">{donations.get("sent", 0):.4f}</div><div class="l">SOL sent on</div></div>
    <div class="tile"><div class="n">{donations.get("pending", 0):.4f}</div><div class="l">SOL awaiting transfer</div></div>
  </div>
  <table style="margin-top:14px"><tbody>
    {"".join(rows_d)}
  </tbody></table>
  {f'<div class="facts" style="margin-top:14px"><div><span>fee wallet</span>{esc(donation_wallet)}</div></div>' if donation_wallet else ""}
  <p class="caveat">On-chain this page can show that SOL arrived in that wallet and that
  SOL left it, to which address and when. It cannot show that the money was
  received and banked at the other end &mdash; that part rests on the recipient&rsquo;s own
  acknowledgement, not on anything provable here.</p>
'''

    generated = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")

    return f'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(ticker)} — Audit</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 40px 20px 80px;
    background: {p["ground"]}; color: {p["ink"]};
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    line-height: 1.6; -webkit-font-smoothing: antialiased;
  }}
  .wrap {{ max-width: 720px; margin: 0 auto; }}

  .lamp {{ width: 13px; height: 13px; border-radius: 50%;
          background: {p["lamp"]}; box-shadow: 0 0 22px 4px rgba(232,163,61,.35);
          margin-bottom: 22px; }}

  h1 {{ font-size: 1.75rem; margin: 0 0 6px; letter-spacing: -.02em; }}
  .sub {{ color: {p["soft"]}; margin: 0 0 34px; font-size: .9375rem; }}

  .verdict {{
    border: 1px solid {colour}; border-left: 3px solid {colour};
    border-radius: 4px; padding: 20px 22px; margin-bottom: 30px;
    background: {p["surface"]};
  }}
  .verdict h2 {{ margin: 0 0 6px; font-size: 1.125rem; color: {colour};
                letter-spacing: .04em; }}
  .verdict p {{ margin: 0; color: {p["soft"]}; font-size: .9375rem; }}

  h3 {{ font-size: .6875rem; text-transform: uppercase; letter-spacing: .16em;
       color: {p["faint"]}; margin: 32px 0 12px; font-weight: 600; }}

  table {{ width: 100%; border-collapse: collapse; font-size: .875rem; }}
  td {{ padding: 11px 10px; border-bottom: 1px solid {p["rule"]};
       vertical-align: top; }}
  td.st {{ width: 74px; font-family: ui-monospace, monospace; font-size: .75rem;
          letter-spacing: .06em; white-space: nowrap; }}
  td.nm {{ width: 150px; color: {p["ink"]}; }}
  td.dt {{ color: {p["soft"]}; }}

  ul.promises {{ margin: 0; padding-left: 20px; }}
  ul.promises li {{ margin-bottom: 7px; color: {p["soft"]}; font-size: .9375rem; }}
  ul.promises b {{ color: {p["ink"]}; }}

  .facts {{ background: {p["alt"]}; border: 1px solid {p["rule"]};
           border-radius: 4px; padding: 16px 18px; font-size: .8125rem;
           font-family: ui-monospace, monospace; color: {p["soft"]};
           overflow-x: auto; }}
  .facts div {{ margin-bottom: 6px; white-space: nowrap; }}
  .facts div:last-child {{ margin-bottom: 0; }}
  .facts span {{ color: {p["faint"]}; display: inline-block; width: 92px; }}

  .tiles {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
  .tile {{ background: {p["surface"]}; border: 1px solid {p["rule"]};
          border-radius: 4px; padding: 16px 18px; }}
  .tile .n {{ font-size: 1.5rem; font-variant-numeric: tabular-nums;
             letter-spacing: -.02em; }}
  .tile .l {{ font-size: .75rem; color: {p["faint"]}; text-transform: uppercase;
             letter-spacing: .1em; margin-top: 4px; }}
  .mono {{ font-family: ui-monospace, monospace; font-size: .75rem;
          word-break: break-all; }}
  .caveat {{ font-size: .8125rem; color: {p["faint"]}; margin-top: 14px;
            max-width: 62ch; line-height: 1.65; }}
  @media (max-width: 560px) {{ .tiles {{ grid-template-columns: 1fr; }} }}

  .chain {{ font-size: .875rem; color: {p["soft"]}; }}
  .hash {{ font-family: ui-monospace, monospace; font-size: .75rem;
          color: {p["sea"]}; word-break: break-all; }}

  footer {{ margin-top: 44px; padding-top: 18px; border-top: 1px solid {p["rule"]};
           color: {p["faint"]}; font-size: .8125rem; }}
  a {{ color: {p["sea"]}; }}
</style></head>
<body><div class="wrap">

  <div class="lamp"></div>
  <h1>{esc(ticker)} — public audit</h1>
  <p class="sub">Read directly from the Solana chain. Every claim below is something you can check yourself.</p>

  <div class="verdict">
    <h2>{headline}</h2>
    <p>{subline}</p>
  </div>

  <h3>What was promised</h3>
  <ul class="promises">
    {"".join(f"<li>{x}</li>" for x in promises)}
  </ul>

  <h3>What the chain says</h3>
  <table><tbody>
{chr(10).join(rows)}
  </tbody></table>

  <h3>Addresses</h3>
  <div class="facts">
    <div><span>token</span>{esc(result["mint"])}</div>
    {f'<div><span>dev wallet</span>{esc(str(result["dev_wallet"]))}</div>' if result.get("dev_wallet") else ""}
    {f'<div><span>lp mint</span>{esc(str(result["lp_mint"]))}</div>' if result.get("lp_mint") else ""}
  </div>

  {donations_block}

  <h3>Record</h3>
  {chain_line or '<p class="chain">Not logged.</p>'}

  <footer>
    Generated {generated} · <a href="https://solscan.io/token/{esc(result["mint"])}">Verify on Solscan</a><br>
    This page reports only what was measured. It is not a guarantee that a token is safe.
  </footer>

</div></body></html>
'''


# ---------------------------------------------------------------------------
# Screenshot card
# ---------------------------------------------------------------------------

def render_card(result: dict, log_state: dict | None = None,
                ticker: str = "$TOKEN") -> str:
    """
    A fixed 1200x675 card - exactly 16:9, which is how X crops an image in the
    timeline. Everything fits without scrolling so one screenshot carries the
    whole audit. Sized in px on purpose: this page is a picture, not a document.
    """
    p = PALETTE
    colour, headline, _ = _verdict_block(result["verdict"])

    rows = []
    for c in result.get("checks", []):
        col = p[_STATUS_COLOR.get(c["status"], "faint")]
        detail = str(c["detail"])
        if len(detail) > 78:
            detail = detail[:75] + "..."
        rows.append(f'''    <div class="row">
      <div class="st" style="color:{col}">{esc(_STATUS_LABEL.get(c["status"], c["status"]))}</div>
      <div class="nm">{esc(c["name"])}</div>
      <div class="dt">{esc(detail)}</div>
    </div>''')

    declared = result.get("declared_pct") or 0
    lock = result.get("lock_until")
    promise = []
    if result.get("dev_wallet"):
        promise.append(f"holds &le; {declared:g}%" if declared > 0 else "holds none")
    if lock:
        promise.append(f"no sales before {esc(str(lock))}")
    promise_line = " &nbsp;·&nbsp; ".join(promise) or "authorities revoked"

    chain = ""
    if log_state and log_state.get("ok"):
        n = log_state["entries"]
        chain = (f'{n} {"entry" if n == 1 else "entries"}, chain intact &nbsp;'
                 f'<span class="hash">{esc(log_state.get("head", "")[:24])}…</span>')
    elif log_state:
        chain = f'<span style="color:{p["bad"]}">log does not verify</span>'
    else:
        chain = "not logged"

    stamp = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{esc(ticker)} — Audit Card</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: 100%; overflow: hidden; }}
  body {{ background: #05090B; display: flex; align-items: center;
         justify-content: center;
         font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}

  .card {{
    width: 1200px; height: 675px; flex: 0 0 auto;
    background: {p["ground"]}; color: {p["ink"]};
    border: 1px solid {p["rule"]};
    padding: 46px 54px; display: flex; flex-direction: column;
    transform-origin: center;
  }}

  .head {{ display: flex; align-items: flex-start; gap: 18px; }}
  .lamp {{ width: 15px; height: 15px; border-radius: 50%; background: {p["lamp"]};
          box-shadow: 0 0 26px 5px rgba(232,163,61,.4); margin-top: 12px; flex: 0 0 auto; }}
  h1 {{ font-size: 38px; letter-spacing: -.02em; line-height: 1.1; }}
  .promise {{ color: {p["soft"]}; font-size: 16px; margin-top: 7px; }}

  .badge {{ margin-left: auto; text-align: right; }}
  .badge .v {{ color: {colour}; font-size: 26px; font-weight: 700;
              letter-spacing: .05em; line-height: 1.1; }}
  .badge .t {{ color: {p["faint"]}; font-size: 13px; margin-top: 6px;
              font-family: ui-monospace, monospace; }}

  .rows {{ margin-top: 30px; border-top: 1px solid {p["rule"]}; }}
  .row {{ display: flex; align-items: baseline; gap: 20px;
         padding: 19px 2px; border-bottom: 1px solid {p["rule"]}; }}
  .st {{ width: 72px; flex: 0 0 auto; font-family: ui-monospace, monospace;
        font-size: 13px; letter-spacing: .07em; }}
  .nm {{ width: 168px; flex: 0 0 auto; font-size: 16px; }}
  .dt {{ color: {p["soft"]}; font-size: 15px; }}

  .foot {{ margin-top: auto; padding-top: 26px;
          border-top: 1px solid {p["rule"]};
          display: flex; align-items: flex-end; gap: 30px; }}
  .addr {{ font-family: ui-monospace, monospace; font-size: 12.5px;
          color: {p["soft"]}; line-height: 1.85; }}
  .addr b {{ color: {p["faint"]}; font-weight: 400; display: inline-block; width: 82px; }}
  .rec {{ margin-left: auto; text-align: right; font-size: 12.5px;
         color: {p["faint"]}; line-height: 1.85; white-space: nowrap; }}
  .hash {{ font-family: ui-monospace, monospace; color: {p["sea"]}; }}

  /* the card is a fixed-size picture; scale it to whatever window it opens in
     so that a plain screenshot of the window captures the whole thing */
</style></head>
<body>
  <div class="card">
    <div class="head">
      <div class="lamp"></div>
      <div>
        <h1>{esc(ticker)} &mdash; public audit</h1>
        <div class="promise">Declared before launch: {promise_line}</div>
      </div>
      <div class="badge">
        <div class="v">{headline}</div>
        <div class="t">{stamp}</div>
      </div>
    </div>

    <div class="rows">
{chr(10).join(rows)}
    </div>

    <div class="foot">
      <div class="addr">
        <div><b>token</b>{esc(result["mint"])}</div>
        {f'<div><b>dev wallet</b>{esc(str(result["dev_wallet"]))}</div>' if result.get("dev_wallet") else ""}
      </div>
      <div class="rec">
        read live from the Solana chain<br>
        audit log: {chain}
      </div>
    </div>
  </div>

<script>
  (function () {{
    var card = document.querySelector(".card");
    function fit() {{
      var s = Math.min(window.innerWidth / 1232, window.innerHeight / 707);
      card.style.transform = "scale(" + s + ")";
    }}
    window.addEventListener("resize", fit);
    fit();
  }})();
</script>
</body></html>
'''
