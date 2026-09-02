"""
The public landing page - what someone sees when they tap the link in your bio.

Deliberately not a marketing site. Everything on it is either something a buyer
can copy (the contract), click (buy, verify), or check (the audit and the
promises). No price, no chart, no roadmap: DexScreener does price better, and a
roadmap is the one thing on a meme coin page nobody believes.

Renders before launch too. With no audit result it shows the promises and says
the coin is not live, rather than half a page of blanks.

HERO_JS is a plain string, not part of the f-string template, so the canvas code
can use braces freely without doubling every one of them.
"""
from html import escape as esc

from keeper_report import PALETTE, _verdict_block

HERO_JS = r"""
(function () {
  var c = document.getElementById("hero"), x = c.getContext("2d");
  var reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  var W, H, stars = [];

  function size() {
    var d = Math.min(devicePixelRatio || 1, 2), r = c.getBoundingClientRect();
    W = r.width; H = r.height;
    c.width = W * d; c.height = H * d; x.setTransform(d, 0, 0, d, 0, 0);
    stars = [];
    for (var i = 0; i < Math.round(W * H / 4200); i++)
      stars.push({ x: Math.random() * W, y: Math.random() * H * 0.58,
                   r: Math.random() * 0.9 + 0.25, a: Math.random() * 0.5 + 0.1,
                   p: Math.random() * 6.283 });
  }

  function draw(t) {
    var hz = H * 0.66, th = H * 0.26, tw = Math.max(th * 0.26, 10);
    var cx = W * 0.5, ly = hz - th, lc = ly + th * 0.12;

    var sky = x.createLinearGradient(0, 0, 0, hz);
    sky.addColorStop(0, "#04070A"); sky.addColorStop(0.6, "#0A1319");
    sky.addColorStop(1, "#152633");
    x.fillStyle = sky; x.fillRect(0, 0, W, hz);

    for (var i = 0; i < stars.length; i++) {
      var s = stars[i];
      x.globalAlpha = s.a * (reduced ? 1 : 0.7 + 0.3 * Math.sin(t / 1400 + s.p));
      x.fillStyle = "#CFE0E6";
      x.beginPath(); x.arc(s.x, s.y, s.r, 0, 6.283); x.fill();
    }
    x.globalAlpha = 1;

    var ph = reduced ? 0.3 : (t % 6000) / 6000, base = ph * 6.283;
    var reach = Math.max(W, H) * 1.6, facing = 0;
    x.save(); x.globalCompositeOperation = "lighter";
    for (var b = 0; b < 2; b++) {
      var ang = base + b * Math.PI, tow = Math.max(0, Math.sin(ang));
      facing = Math.max(facing, tow);
      for (var k = 2; k >= 0; k--) {
        var sp = (0.07 + 0.04 * tow) * (1 + k * 0.9);
        var al = (0.03 + 0.17 * Math.pow(tow, 1.8)) * (k === 0 ? 1 : k === 1 ? 0.34 : 0.14);
        var g = x.createRadialGradient(cx, lc, 0, cx, lc, reach);
        g.addColorStop(0, "rgba(255,224,172," + al + ")");
        g.addColorStop(0.28, "rgba(232,163,61," + al * 0.4 + ")");
        g.addColorStop(1, "rgba(232,163,61,0)");
        x.fillStyle = g; x.beginPath(); x.moveTo(cx, lc);
        x.arc(cx, lc, reach, ang - sp, ang + sp); x.closePath(); x.fill();
      }
    }
    x.restore();

    var sea = x.createLinearGradient(0, hz, 0, H);
    sea.addColorStop(0, "#0D1A22"); sea.addColorStop(1, "#05090C");
    x.fillStyle = sea; x.fillRect(0, hz, W, H - hz);

    x.save(); x.globalCompositeOperation = "lighter";
    var col = x.createLinearGradient(0, hz, 0, H);
    col.addColorStop(0, "rgba(232,163,61," + (0.10 + 0.20 * facing) + ")");
    col.addColorStop(1, "rgba(232,163,61,0)");
    x.fillStyle = col;
    x.beginPath(); x.moveTo(cx - tw * 0.4, hz); x.lineTo(cx + tw * 0.4, hz);
    x.lineTo(cx + tw * 3.4, H); x.lineTo(cx - tw * 3.4, H); x.closePath(); x.fill();
    x.restore();

    for (var r2 = 0; r2 < 20; r2++) {
      var d2 = r2 / 20, y = hz + Math.pow(d2, 1.4) * (H - hz);
      x.globalAlpha = 0.32 + 0.3 * Math.abs(Math.sin(r2 * 2.1 + (reduced ? 0 : t / 1150)));
      x.fillStyle = "#04080A";
      x.fillRect(0, y, W, Math.max((H - hz) / 20 * 0.4, 1));
    }
    x.globalAlpha = 1;

    x.fillStyle = "#060B0E";
    x.beginPath();
    x.moveTo(cx - tw * 3, hz + (H - hz) * 0.12); x.lineTo(cx - tw * 1.5, hz - H * 0.005);
    x.lineTo(cx + tw * 1.5, hz - H * 0.005); x.lineTo(cx + tw * 3.3, hz + (H - hz) * 0.12);
    x.closePath(); x.fill();

    var topW = tw * 0.68, by = hz - H * 0.01, ry = ly + th * 0.2;
    x.fillStyle = "#0A1218";
    x.beginPath(); x.moveTo(cx - tw / 2, by); x.lineTo(cx - topW / 2, ry);
    x.lineTo(cx + topW / 2, ry); x.lineTo(cx + tw / 2, by); x.closePath(); x.fill();
    x.fillRect(cx - topW * 0.86, ry - th * 0.02, topW * 1.72, Math.max(th * 0.022, 1.5));
    x.fillStyle = "#0C1620";
    x.fillRect(cx - topW * 0.52, ly + th * 0.045, topW * 1.04, th * 0.14);
    x.fillStyle = "#0A1218";
    x.beginPath(); x.moveTo(cx - topW * 0.62, ly + th * 0.048);
    x.lineTo(cx, ly - th * 0.035); x.lineTo(cx + topW * 0.62, ly + th * 0.048);
    x.closePath(); x.fill();

    x.save(); x.globalCompositeOperation = "lighter";
    var lit = 0.3 + 0.7 * Math.pow(facing, 1.6);
    var lr = x.createRadialGradient(cx, lc, 0, cx, lc, tw * 2.6);
    lr.addColorStop(0, "rgba(255,232,190," + 0.42 * lit + ")");
    lr.addColorStop(0.1, "rgba(246,196,116," + 0.26 * lit + ")");
    lr.addColorStop(1, "rgba(232,163,61,0)");
    x.fillStyle = lr; x.beginPath(); x.arc(cx, lc, tw * 2.6, 0, 6.283); x.fill();
    x.fillStyle = "rgba(255,236,198," + (0.26 + 0.52 * lit) + ")";
    x.beginPath(); x.arc(cx, lc, Math.max(tw * 0.085, 1.2), 0, 6.283); x.fill();
    x.restore();

    var v = x.createRadialGradient(cx, H * 0.5, H * 0.25, cx, H * 0.5, H * 0.9);
    v.addColorStop(0, "rgba(0,0,0,0)"); v.addColorStop(1, "rgba(0,0,0,0.6)");
    x.fillStyle = v; x.fillRect(0, 0, W, H);
  }

  function loop(t) { draw(t); if (!reduced) requestAnimationFrame(loop); }
  addEventListener("resize", size);
  size(); if (reduced) draw(0); else requestAnimationFrame(loop);
})();

var btn = document.getElementById("copy");
if (btn) btn.addEventListener("click", function () {
  var t = document.getElementById("ca").textContent;
  function done() { btn.textContent = "Copied"; setTimeout(function () { btn.textContent = "Copy"; }, 1500); }
  try { navigator.clipboard.writeText(t).then(done, done); } catch (e) { done(); }
});
"""


def render_site(result: dict | None = None, ticker: str = "$TOKEN",
                donations: dict | None = None, cause: str = "",
                links: dict | None = None, promises: list[str] | None = None,
                tagline: str = "forty years on this rock. the light goes on at dusk.",
                pumpfun_url: str = "", charity_url: str = "",
                fees_donated: str = "") -> str:
    p = PALETTE
    links = links or {}
    live = bool(result and result.get("mint"))
    mint = result.get("mint", "") if result else ""

    if live:
        colour, headline, _ = _verdict_block(result["verdict"])
        status = (f'<a class="status" href="audit.html" '
                  f'style="border-color:{colour};color:{colour}">'
                  f'{headline} &mdash; see the full audit</a>')
        buy = pumpfun_url or f"https://pump.fun/coin/{mint}"
        ca_block = (
            f'<div class="ca"><span class="lbl">Contract</span>'
            f'<code id="ca">{esc(mint)}</code>'
            f'<button id="copy">Copy</button></div>'
            f'<div class="cta">'
            f'<a class="buy" href="{esc(buy)}">Buy on pump.fun</a>'
            f'<a class="alt" href="https://dexscreener.com/solana/{esc(mint)}">Chart</a>'
            f'<a class="alt" href="https://solscan.io/token/{esc(mint)}">Solscan</a>'
            f'</div>')
    else:
        status = (f'<span class="status" style="border-color:{p["faint"]};'
                  f'color:{p["soft"]}">Not live yet</span>')
        ca_block = ('<div class="ca"><span class="lbl">Contract</span>'
                    '<code>published at launch</code></div>')

    promise_cards = "".join(f'<div class="card"><p>{x}</p></div>'
                            for x in (promises or []))

    if donations:
        to = f" &rarr; {esc(cause)}" if cause else ""
        fees = (
            f'<section><h2>Creator fees{to}</h2><div class="tiles">'
            f'<div class="tile"><div class="n">{donations.get("received", 0):.3f}</div>'
            f'<div class="l">SOL received</div></div>'
            f'<div class="tile"><div class="n" style="color:{p["good"]}">'
            f'{donations.get("sent", 0):.3f}</div><div class="l">SOL sent on</div></div>'
            f'<div class="tile"><div class="n">{donations.get("pending", 0):.3f}</div>'
            f'<div class="l">awaiting transfer</div></div></div>'
            f'<p class="fine">On-chain this shows SOL arriving and SOL leaving. It cannot '
            f'show the money was banked at the other end &mdash; that rests on the '
            f'recipient, not on anything provable here.</p></section>')
    elif cause:
        # A self-reported figure, clearly labelled as such, plus a third-party
        # link. The charity's own page shows its all-time total from every
        # donor - saying so out loud is what stops this reading as if that
        # number were yours.
        raised = (f'<div class="tiles" style="grid-template-columns:1fr">'
                  f'<div class="tile"><div class="n">{esc(str(fees_donated))}</div>'
                  f'<div class="l">SOL in creator fees routed so far</div></div></div>'
                  if fees_donated else "")
        proof = (f'<p class="lead" style="margin-top:12px">Verify the recipient: '
                 f'<a href="{esc(charity_url)}">{esc(cause)} on donate.gg</a>. '
                 f'The total on that page is the church&rsquo;s, from every donor it has '
                 f'ever had &mdash; not mine, and most of it predates this coin.</p>'
                 if charity_url else "")
        fees = (f'<section><h2>Creator fees</h2><p class="lead">100% of creator fees go to '
                f'{esc(cause)}, set through pump.fun&rsquo;s charity function. They are not '
                f'routed through me and I cannot redirect them.</p>{raised}{proof}</section>')
    else:
        fees = ""

    # audit.html only exists once a real audit has been run, so linking it
    # before launch just hands a visitor a 404 on the one page that is supposed
    # to prove you are careful
    link_html = "".join(
        f'<a href="{esc(v)}">{esc(k)}</a>'
        for k, v in links.items()
        if v and not (v.endswith("audit.html") and not live))

    return f'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(ticker)}</title>
<meta name="description" content="{esc(ticker)} — every promise published before launch, and checkable at any time.">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: {p["ground"]}; color: {p["ink"]};
         font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
         line-height: 1.65; -webkit-font-smoothing: antialiased; }}
  .wrap {{ max-width: 680px; margin: 0 auto; padding: 0 22px 90px; }}

  .hero {{ position: relative; height: 46vh; min-height: 300px; max-height: 460px;
          margin-bottom: 30px; }}
  canvas {{ display: block; width: 100%; height: 100%; }}
  .heroText {{ position: absolute; inset: auto 0 7% 0; text-align: center; padding: 0 22px; }}
  h1 {{ font-size: clamp(2.2rem, 9vw, 3.4rem); letter-spacing: -.03em; line-height: 1; }}
  .tag {{ color: {p["soft"]}; margin-top: 10px; font-size: .9375rem; }}

  .status {{ display: inline-block; border: 1px solid; border-radius: 3px;
            padding: 8px 14px; font-size: .8125rem; letter-spacing: .04em;
            text-decoration: none; margin-bottom: 20px; }}

  .ca {{ background: {p["surface"]}; border: 1px solid {p["rule"]}; border-radius: 4px;
        padding: 14px 16px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
  .ca .lbl {{ font-size: .6875rem; text-transform: uppercase; letter-spacing: .14em;
             color: {p["faint"]}; }}
  .ca code {{ font-family: ui-monospace, monospace; font-size: .8125rem;
             word-break: break-all; flex: 1; min-width: 190px; }}
  .ca button {{ background: {p["alt"]}; color: {p["soft"]}; border: 1px solid {p["rule"]};
               border-radius: 3px; padding: 7px 13px; font-size: .75rem; cursor: pointer;
               font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }}
  .ca button:hover {{ color: {p["lamp"]}; border-color: {p["lamp"]}; }}

  .cta {{ display: flex; gap: 10px; margin-top: 13px; flex-wrap: wrap; }}
  .buy {{ background: {p["lamp"]}; color: #10161A; font-weight: 700; text-decoration: none;
         padding: 12px 22px; border-radius: 3px; }}
  .alt {{ border: 1px solid {p["rule"]}; color: {p["soft"]}; text-decoration: none;
         padding: 12px 18px; border-radius: 3px; }}
  .alt:hover {{ color: {p["ink"]}; }}

  section {{ margin-top: 44px; }}
  h2 {{ font-size: .6875rem; text-transform: uppercase; letter-spacing: .16em;
       color: {p["faint"]}; margin-bottom: 14px; font-weight: 600; }}
  .lead {{ color: {p["soft"]}; font-size: .9375rem; max-width: 60ch; }}

  .card {{ background: {p["surface"]}; border: 1px solid {p["rule"]};
          border-left: 2px solid {p["lamp"]}; border-radius: 3px;
          padding: 15px 17px; margin-bottom: 9px; }}
  .card p {{ font-size: .9375rem; color: {p["soft"]}; }}
  .card b {{ color: {p["ink"]}; }}
  .card code {{ font-family: ui-monospace, monospace; font-size: .75rem;
               color: {p["sea"]}; word-break: break-all; }}

  .tiles {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
  .tile {{ background: {p["surface"]}; border: 1px solid {p["rule"]};
          border-radius: 4px; padding: 15px 16px; }}
  .tile .n {{ font-size: 1.35rem; font-variant-numeric: tabular-nums; }}
  .tile .l {{ font-size: .6875rem; color: {p["faint"]}; text-transform: uppercase;
             letter-spacing: .1em; margin-top: 3px; }}

  .links {{ display: flex; flex-wrap: wrap; gap: 9px; }}
  .links a {{ border: 1px solid {p["rule"]}; color: {p["soft"]}; text-decoration: none;
             padding: 9px 15px; border-radius: 3px; font-size: .875rem; }}
  .links a:hover {{ color: {p["lamp"]}; border-color: {p["lamp"]}; }}

  .fine {{ font-size: .8125rem; color: {p["faint"]}; margin-top: 14px; max-width: 60ch; }}
  footer {{ margin-top: 52px; padding-top: 20px; border-top: 1px solid {p["rule"]};
           font-size: .8125rem; color: {p["faint"]}; max-width: 62ch; }}
  @media (max-width: 560px) {{ .tiles {{ grid-template-columns: 1fr; }} }}
</style></head>
<body>

<div class="hero">
  <canvas id="hero"></canvas>
  <div class="heroText">
    <h1>{esc(ticker)}</h1>
    <p class="tag">{esc(tagline)}</p>
  </div>
</div>

<div class="wrap">
  {status}
  {ca_block}

  <section>
    <h2>Published before launch</h2>
    {promise_cards}
  </section>

  {fees}

  <section>
    <h2>Elsewhere</h2>
    <div class="links">{link_html}</div>
  </section>

  <footer>
    Nothing here is financial advice, and none of it is a guarantee that a token is safe.
    It is a record of what was promised and what the chain says. Check it yourself.
  </footer>
</div>

<script>{HERO_JS}</script>
</body></html>
'''
