# keeper-audit

The tool behind the $KEEPER public audit page, published so anyone can read what
it actually does rather than take the output on trust.

It answers four questions about a Solana token, straight from the chain:

- Can anyone still mint more supply?
- Can anyone freeze holders' wallets?
- Is the liquidity burned?
- Does the dev hold what they said they would?

Then it writes a record that it checked, in a form that can't be quietly edited
afterwards.

## What it is not

Not a safety checker that competes with DexScreener — DexScreener shows the
generic checks and does it well. This exists to check a **specific set of public
promises** against the chain, which is something no explorer can do because the
promises aren't on-chain: they were made in a post, before launch, by a person
who can now be held to them.

It cannot tell you a token is safe. Nothing can.

## Running it

```bash
pip install -r requirements.txt
python keeper_audit.py <MINT_ADDRESS>
```

With the full set of commitments:

```bash
python keeper_audit.py <MINT> \
  --dev-wallet <WALLET> --declared-sol 2 --lock-until 2026-10-15 \
  --ops-wallet <OPS1> --ops-wallet <OPS2> \
  --receipts --report docs/audit.html --card docs/card.html --log
```

Or put it all in `keeper.config.json` and run `python keeper_audit.py` with no
arguments. Windows users can double-click `check.bat`.

| command | does |
|---|---|
| `check.bat` | full audit, writes the report, card and site, opens it |
| `verify.bat` | checks the audit log has not been tampered with |
| `serve.bat` | serves `docs/` at http://localhost:8000 |
| `test.bat` | dry run against a live token, writes to separate test files |

## How the promises are checked

Three shapes, because a promise can be made three ways and each needs different
handling:

| declared | meaning | behaviour |
|---|---|---|
| `--declared-sol N` | "I bought N SOL worth" | holding is **reported**; the lock is what's enforced |
| `--declared-pct N` | "I hold no more than N%" | a cap — **fails** if exceeded |
| neither | "I hold none" | fails on any holding |

`--ops-wallet` marks a **disclosed** wallet — a marketing budget that was
announced in advance and is expected to be spent. Those are always reported and
never gate the verdict, because failing a wallet for doing the thing it was
publicly declared to do would be meaningless.

## The audit log

`--log` appends each run to `audit_log.jsonl`. Every entry carries the SHA-256 of
the entry before it, so editing or deleting any earlier record breaks the chain
from that point on and `--verify-log` reports exactly where.

```
log OK - 12 entries, chain intact
head  db3d1e133966310980949c38677b6164478b26547081f272810be5dd67e02e2f
```

The chain proves the log is internally consistent and unedited since it was
written. It does **not** prove when an entry was written — only that the sequence
hasn't been rewritten. `--anchor` prints a line containing the chain head to post
publicly; once that's on a timestamped post, everything before it is anchored.

The lock check uses this history: it compares the current holding against the
**earliest logged run** for that wallet, which is the only way a snapshot tool can
answer "did they sell during the period they promised not to."

## Honest limits

- The concentration figure includes pool and bonding-curve accounts, which are
  legitimately large holders on a fresh token. It's reported, never failed.
- Tokens on Token-2022 with extensions aren't parsed. They're reported as
  unreadable rather than guessed at.
- The donations tracker can show SOL arriving in a wallet and SOL leaving it. It
  cannot show the money was received and banked at the other end.
- The public Solana RPC rate-limits. Informational checks degrade rather than
  failing the run; the checks that matter retry with backoff.

## Dependencies

`requests`, and `pytest` to run the tests. Nothing else — the SPL mint layout is
parsed directly and base58 is implemented in `solana_safety.py`, so there's no
Solana SDK to audit before you trust this.

```bash
python -m pytest -q
```
