import keeper_donations
from keeper_donations import fetch_transfers, summarise

W = "MYWALLET"
OTHER = "CHURCHWALLET"


def _tx(keys, pre, post, fee=5000):
    return {
        "meta": {"preBalances": pre, "postBalances": post, "fee": fee},
        "transaction": {"message": {"accountKeys": [{"pubkey": k} for k in keys]}},
    }


def _patch(monkeypatch, sigs, txs):
    calls = {"i": 0}

    def fake(method, params, *a, **k):
        if method == "getSignaturesForAddress":
            return sigs
        if method == "getTransaction":
            tx = txs[calls["i"]]
            calls["i"] += 1
            return tx
        return {}

    monkeypatch.setattr(keeper_donations, "rpc_call", fake)


def test_incoming_transfer_is_detected(monkeypatch):
    _patch(monkeypatch,
           [{"signature": "s1", "blockTime": 1789000000}],
           [_tx([W, OTHER], [1_000_000_000, 5_000_000_000], [3_000_000_000, 3_000_000_000])])
    t = fetch_transfers(W, pause=0)
    assert len(t) == 1
    assert t[0]["direction"] == "in"
    assert t[0]["sol"] == 2.0
    assert t[0]["counterparty"] == OTHER


def test_outgoing_transfer_excludes_the_fee(monkeypatch):
    # sends 1 SOL and pays a 5000 lamport fee; the payout shown must be the 1 SOL
    _patch(monkeypatch,
           [{"signature": "s2", "blockTime": 1789000100}],
           [_tx([W, OTHER], [3_000_000_000, 0], [1_999_995_000, 1_000_000_000])])
    t = fetch_transfers(W, pause=0)
    assert t[0]["direction"] == "out"
    assert t[0]["sol"] == 1.0
    assert t[0]["counterparty"] == OTHER
    assert t[0]["fee_only"] is False


def test_fee_only_transaction_is_flagged(monkeypatch):
    _patch(monkeypatch,
           [{"signature": "s3", "blockTime": 1789000200}],
           [_tx([W, OTHER], [1_000_000_000, 0], [999_995_000, 0])])
    t = fetch_transfers(W, pause=0)
    assert t[0]["fee_only"] is True


def test_failed_transactions_are_skipped(monkeypatch):
    _patch(monkeypatch, [{"signature": "bad", "blockTime": 1, "err": {"x": 1}}], [])
    assert fetch_transfers(W, pause=0) == []


def test_summary_ignores_fee_noise_and_totals_correctly():
    transfers = [
        {"direction": "in", "sol": 5.0, "fee_only": False, "signature": "a"},
        {"direction": "out", "sol": 2.0, "fee_only": False, "signature": "b"},
        {"direction": "out", "sol": 0.000005, "fee_only": True, "signature": "c"},
    ]
    s = summarise(transfers)
    assert s["received"] == 5.0
    assert s["sent"] == 2.0
    assert s["pending"] == 3.0
    assert len(s["payouts"]) == 1


def test_pending_never_goes_negative():
    s = summarise([{"direction": "out", "sol": 1.0, "fee_only": False, "signature": "x"}])
    assert s["pending"] == 0.0
