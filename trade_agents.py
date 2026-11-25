
import json
import math
from pathlib import Path
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo


VERSION = "6.1"


def num(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def agent(status, reason):
    return {
        "status": status,
        "reason": reason
    }


# AGENT 1: MACHINE LEARNING

def prediction_agent(stock, report):

    p = stock.get("prediction_1d") or {}
    diagnostics = report.get(
        "ai_diagnostics", {}
    ).get("1", {})

    probability = num(p.get("up_probability"))

    if (
        p.get("status") != "Available"
        or diagnostics.get("reliable") is not True
        or probability is None
        or not 0 <= probability <= 100
    ):
        return agent(
            "UNKNOWN",
            "No validated AI prediction"
        )

    if probability >= 60:
        return agent(
            "POSITIVE",
            f"Up probability {probability:.2f}%"
        )

    if probability <= 40:
        return agent(
            "NEGATIVE",
            f"Up probability {probability:.2f}%"
        )

    return agent(
        "NEUTRAL",
        f"Up probability {probability:.2f}%"
    )


# AGENT 2: TECHNICAL ANALYSIS

def technical_agent(stock):

    score = num(stock.get("score"))
    rsi = num(stock.get("rsi"))
    macd = num(stock.get("macd"))
    signal = num(stock.get("macd_signal"))
    volume = num(stock.get("relative_volume"))

    values = [score, rsi, macd, signal, volume]

    if any(v is None for v in values):
        return agent(
            "UNKNOWN",
            "Incomplete technical data"
        )

    if (
        score >= 80
        and 45 <= rsi <= 65
        and macd > signal
        and volume >= 1.5
    ):
        return agent(
            "POSITIVE",
            "Strong trend and volume confirmation"
        )

    if score <= 40 and macd < signal:
        return agent(
            "NEGATIVE",
            "Weak technical trend"
        )

    return agent(
        "NEUTRAL",
        "Entry conditions not fully satisfied"
    )


# AGENT 3: FUNDAMENTALS

def fundamental_agent(stock):

    return agent(
        "UNKNOWN",
        "Verified fundamental data not connected"
    )


# AGENT 4: NEWS

def news_agent(stock):

    return agent(
        "UNKNOWN",
        "Verified news feed not connected"
    )


# AGENT 5: RISK MANAGEMENT

def risk_agent(stock):

    price = num(stock.get("price"))
    turnover = num(
        stock.get("average_daily_turnover")
    )
    volatility = num(stock.get("volatility"))

    if any(
        v is None
        for v in [price, turnover, volatility]
    ):
        return agent(
            "BLOCK",
            "Missing risk data"
        )

    if price < 20:
        return agent(
            "BLOCK",
            "Low-priced stock risk filter"
        )

    if turnover < 10000000:
        return agent(
            "BLOCK",
            "Insufficient average daily turnover"
        )

    if volatility > 60:
        return agent(
            "BLOCK",
            "High historical volatility"
        )

    return agent(
        "POSITIVE",
        "Basic liquidity and volatility filters passed"
    )


# AGENT 6: BACKTESTING

def backtest_agent(stock):

    strategy = num(stock.get("backtest_return"))
    benchmark = num(stock.get("benchmark_return"))
    trades = num(stock.get("backtest_trades"))
    drawdown = num(stock.get("max_drawdown"))

    values = [strategy, benchmark, trades, drawdown]

    if any(v is None for v in values):
        return agent(
            "UNKNOWN",
            "Backtest data unavailable"
        )

    if trades < 10:
        return agent(
            "UNKNOWN",
            "Too few historical trades"
        )

    if (
        strategy > 0
        and strategy > benchmark
        and abs(drawdown) <= 20
    ):
        return agent(
            "POSITIVE",
            "Technical strategy beat its benchmark"
        )

    if strategy < 0 or abs(drawdown) > 30:
        return agent(
            "NEGATIVE",
            "Weak returns or excessive drawdown"
        )

    return agent(
        "NEUTRAL",
        "Limited historical strategy advantage"
    )


# AGENT 7: MARKET DIRECTION

def market_agent(report, expected_date):

    changes = [
        num(s.get("change"))
        for s in report.get("stocks", [])
        if s.get("date") == expected_date
    ]

    changes = [
        c for c in changes if c is not None
    ]

    if len(changes) < 100:
        return agent(
            "UNKNOWN",
            "Insufficient fresh market breadth data"
        )

    advancing = sum(c > 0 for c in changes)
    breadth = advancing / len(changes)

    if breadth >= 0.55:
        status = "POSITIVE"
    elif breadth <= 0.45:
        status = "NEGATIVE"
    else:
        status = "NEUTRAL"

    return agent(
        status,
        f"{breadth * 100:.2f}% of stocks advancing"
    )


# AGENT 8: TRADE PLANNING

def trade_planning_agent(stock):

    entry = num(stock.get("reference_entry"))
    stop = num(stock.get("reference_stop"))
    target = num(stock.get("reference_target"))

    values = [entry, stop, target]

    if any(v is None for v in values):
        return agent(
            "BLOCK",
            "Missing reference price levels"
        )

    if not 0 < stop < entry < target:
        return agent(
            "BLOCK",
            "Invalid trade price levels"
        )

    risk = entry - stop
    reward = target - entry
    ratio = reward / risk

    if risk / entry > 0.08:
        status = "BLOCK"
        reason = "Stop-loss distance exceeds 8%"
    elif ratio < 1.95:
        status = "BLOCK"
        reason = "Insufficient reward-to-risk ratio"
    else:
        status = "POSITIVE"
        reason = "Reference trade levels acceptable"

    return {
        "status": status,
        "reason": reason,
        "entry": round(entry, 2),
        "stop_loss": round(stop, 2),
        "target": round(target, 2),
        "reward_risk": round(ratio, 2),
        "risk_pct": round(risk / entry * 100, 2),
        "reward_pct": round(
            reward / entry * 100, 2
        )
    }


# AGENT 9: MASTER DECISION

def master_agent(stock, report, expected_date,
                 market):

    agents = {
        "prediction": prediction_agent(
            stock, report
        ),
        "technical": technical_agent(stock),
        "fundamental": fundamental_agent(stock),
        "news": news_agent(stock),
        "risk": risk_agent(stock),
        "backtesting": backtest_agent(stock),
        "market": market,
        "trade_planning": trade_planning_agent(stock)
    }

    statuses = {
        name: result["status"]
        for name, result in agents.items()
    }

    votes = Counter(statuses.values())

    decision = "WAIT"
    reason = "Insufficient supporting evidence"

    if (
        stock.get("date") != expected_date
        or report.get("completed_sessions_only")
        is not True
        or str(report.get("version")) != "6.0"
    ):
        reason = "Stale or incomplete market data"

    elif votes["BLOCK"] > 0:
        reason = "Risk or trade planning veto"

    elif (
        statuses["prediction"] == "NEGATIVE"
        and statuses["technical"] == "NEGATIVE"
    ):
        decision = "EXIT REVIEW"
        reason = "AI and technical weakness"

    elif (
        statuses["prediction"] == "POSITIVE"
        and statuses["technical"] == "POSITIVE"
        and statuses["risk"] == "POSITIVE"
        and statuses["trade_planning"] == "POSITIVE"
        and statuses["backtesting"] == "POSITIVE"
        and statuses["market"] == "POSITIVE"
    ):
        decision = "BUY WATCHLIST"
        reason = "All available core checks passed"

    elif (
        statuses["technical"] == "POSITIVE"
        and statuses["prediction"] == "NEUTRAL"
    ):
        decision = "MONITOR"
        reason = "Technical strength without AI confirmation"

    return {
        "decision": decision,
        "reason": reason,
        "mode": "Paper trading research only",
        "agents": agents,
        "positive_votes": votes["POSITIVE"],
        "negative_votes": votes["NEGATIVE"],
        "unknown_agents": votes["UNKNOWN"],
        "risk_blocks": votes["BLOCK"]
    }


# GENERATE MULTI-AGENT REPORT

def run_agents(report, expected_date):

    market = market_agent(
        report, expected_date
    )

    results = []

    for stock in report.get("stocks", []):

        result = master_agent(
            stock, report, expected_date, market
        )

        results.append({
            "symbol": stock.get("symbol"),
            "date": stock.get("date"),
            "price": stock.get("price"),
            "technical_score": stock.get("score"),
            **result
        })

    counts = Counter(
        s["decision"] for s in results
    )

    return {
        "version": VERSION,
        "source_version": report.get("version"),
        "generated": datetime.now(
            ZoneInfo("Asia/Kolkata")
        ).isoformat(),
        "expected_market_date": expected_date,
        "stocks_analysed": len(results),
        "signal_counts": dict(counts),
        "stocks": results
    }


if __name__ == "__main__":

    source = Path("market_data.json")

    report = json.loads(
        source.read_text(encoding="utf-8")
    )

    today = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).date().isoformat()

    output = run_agents(report, today)

    Path("trade_signals.json").write_text(
        json.dumps(
            output,
            indent=2,
            allow_nan=False
        ),
        encoding="utf-8"
    )

    print("StockMind AI 6.1 completed")
    print("Stocks:", output["stocks_analysed"])
    print("Signals:", output["signal_counts"])
