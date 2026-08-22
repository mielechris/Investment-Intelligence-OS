import pytest

from intelligence.paper_portfolio import PaperPortfolioStore


def _packet():
    return {
        "risk_result": {
            "decision": "WATCH_ONLY",
            "paper_execution_eligible": True,
            "synthetic_fixture": True,
        },
        "risk_packet": {
            "market_data": {
                "symbol": "IIOS-TEST",
                "side": "LONG",
                "entry_price": 100.0,
            }
        },
    }


def _order():
    return {
        "simulated_notional": 10000,
        "real_notional": 0,
        "broker_order_sent": False,
        "live_execution": False,
        "synthetic_fixture": True,
        "source_risk_review_id": "risk-test",
    }


def test_simulated_order_creates_deduplicated_position(tmp_path):
    store = PaperPortfolioStore(tmp_path / "portfolio.db")
    first = store.record_simulated_order(candidate_id="candidate-1", order=_order(), candidate_packet=_packet())
    second = store.record_simulated_order(candidate_id="candidate-1", order=_order(), candidate_packet=_packet())
    assert first["position_id"] == second["position_id"]
    assert first["symbol"] == "IIOS-TEST"
    assert first["quantity"] == 100
    assert store.summary()["positions"] == 1


def test_mark_to_market_calculates_unrealized_pnl(tmp_path):
    store = PaperPortfolioStore(tmp_path / "portfolio.db")
    position = store.record_simulated_order(candidate_id="candidate-1", order=_order(), candidate_packet=_packet())
    marked = store.mark(position["position_id"], 105.0, source="test")
    assert marked["mark_price"] == 105.0
    assert marked["unrealized_pnl"] == 500.0
    assert store.summary()["unrealized_pnl"] == 500.0


def test_close_moves_unrealized_to_realized_pnl(tmp_path):
    store = PaperPortfolioStore(tmp_path / "portfolio.db")
    position = store.record_simulated_order(candidate_id="candidate-1", order=_order(), candidate_packet=_packet())
    store.mark(position["position_id"], 105.0, source="test")
    closed = store.close(position["position_id"], 105.0, source="test_close")

    assert closed["status"] == "closed"
    assert closed["mark_price"] == 105.0
    assert closed["unrealized_pnl"] == 0
    assert closed["realized_pnl"] == 500.0
    summary = store.summary()
    assert summary["open_positions"] == 0
    assert summary["closed_positions"] == 1
    assert summary["realized_pnl"] == 500.0


def test_closed_position_cannot_close_twice_or_be_remarked(tmp_path):
    store = PaperPortfolioStore(tmp_path / "portfolio.db")
    position = store.record_simulated_order(candidate_id="candidate-1", order=_order(), candidate_packet=_packet())
    store.close(position["position_id"], 105.0)

    with pytest.raises(ValueError, match="already closed"):
        store.close(position["position_id"], 110.0)
    with pytest.raises(ValueError, match="cannot be re-marked"):
        store.mark(position["position_id"], 106.0)


def test_real_capital_remains_zero(tmp_path):
    store = PaperPortfolioStore(tmp_path / "portfolio.db")
    store.record_simulated_order(candidate_id="candidate-1", order=_order(), candidate_packet=_packet())
    assert store.summary()["real_capital"] == 0
