import json
import time
import datetime
import os
import pandas as pd
import yfinance as yf
from pathlib import Path

# StockMind AI 4.0
# Daily historical research engine

STARTER = """
RELIANCE TCS INFY HDFCBANK SBIN
ITC LT AXISBANK ICICIBANK WIPRO
TATAMOTORS TATASTEEL ONGC NTPC
POWERGRID IRFC RVNL YESBANK
IDEA SUZLON NHPC BHEL
""".split()

def get_symbols():
    url = (
        "https://archives.nseindia.com/"
        "content/equities/EQUITY_L.csv"
    )

    try:
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        df = df[df["SERIES"].str.strip() == "EQ"]
        return sorted(set(df["SYMBOL"].str.strip())), "NSE"
    except Exception as e:
        print("NSE list unavailable:", e)

    if Path("symbols.csv").exists():
        df = pd.read_csv("symbols.csv")
        df.columns = df.columns.str.strip().str.lower()
        return sorted(set(df["symbol"].dropna().astype(str).str.strip())), "Local list"

    return STARTER, "Starter list"


def number(value, digits=2):
    try:
        value = float(value)
        if pd.isna(value) or abs(value) == float("inf"):
            return None
        return round(value, digits)
    except Exception:
        return None


def analyse(symbol, df):
    df = df.dropna(subset=["Close"]).sort_index()

    if len(df) < 60:
        raise ValueError("Insufficient history")

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    price = float(close.iloc[-1])

    if price <= 0:
        raise ValueError("Invalid price")

    change = (
        price / close.iloc[-2] - 1
    ) * 100

    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1/14,
        adjust=False,
        min_periods=14
    ).mean()

    avg_loss = loss.ewm(
        alpha=1/14,
        adjust=False,
        min_periods=14
    ).mean()

    rsi = 100 - 100 / (
        1 + avg_gain / avg_loss
    )

    ema12 = close.ewm(
        span=12, adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26, adjust=False
    ).mean()

    macd = ema12 - ema26

    signal = macd.ewm(
        span=9, adjust=False
    ).mean()

    previous = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - previous).abs(),
        (low - previous).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(14).mean().iloc[-1]

    average_volume = volume.shift(1).rolling(20).mean().iloc[-1]

    relative_volume = (
        volume.iloc[-1] / average_volume
        if average_volume > 0 else None
    )

    ath = high.max()
    atl = low.min()

    score = 0
    reasons = []

    if price > sma20.iloc[-1]:
        score += 20
        reasons.append("Above 20-day average")

    if price > sma50.iloc[-1]:
        score += 20
        reasons.append("Above 50-day average")

    if price > sma200.iloc[-1]:
        score += 20
        reasons.append("Above 200-day average")

    if 45 <= rsi.iloc[-1] <= 65:
        score += 20
        reasons.append("RSI between 45 and 65")

    if macd.iloc[-1] > signal.iloc[-1]:
        score += 20
        reasons.append("Positive MACD crossover state")

    # Historical strategy test
    # Signal at close, execution next open
    position = (
        sma20 > sma50
    ).astype(float).shift(1).fillna(0)

    opens = df["Open"]
    returns = opens.pct_change()

    exposure = position.shift(1).fillna(0)
    turnover = position.diff().abs().shift(1).fillna(0)

    strategy = (
        exposure * returns - turnover * 0.002
    ).dropna().tail(252)

    equity = (1 + strategy).cumprod()

    drawdown = (
        equity / equity.cummax().clip(lower=1) - 1
    ).min()

    backtest = (
        equity.iloc[-1] - 1
    ) * 100 if len(equity) else None

    benchmark = (
        (1 + returns.dropna().tail(252)).prod() - 1
    ) * 100

    return {
        "symbol": symbol,
        "date": str(df.index[-1].date()),
        "price": number(price),
        "change": number(change),
        "volume": number(volume.iloc[-1], 0),
        "relative_volume": number(relative_volume),
        "rsi": number(rsi.iloc[-1]),
        "macd": number(macd.iloc[-1]),
        "macd_signal": number(signal.iloc[-1]),
        "sma20": number(sma20.iloc[-1]),
        "sma50": number(sma50.iloc[-1]),
        "sma200": number(sma200.iloc[-1]),
        "ath": number(ath),
        "atl": number(atl),
        "history_start": str(df.index[0].date()),
        "fall_from_high": number(
            (1 - price / ath) * 100
        ),
        "score": score,
        "reasons": reasons,
        "reference_entry": number(price),
        "reference_stop": number(
            max(0, price - 2 * atr)
        ),
        "reference_target": number(
            price + 4 * atr
        ),
        "backtest_return": number(backtest),
        "benchmark_return": number(benchmark),
        "max_drawdown": number(drawdown * 100),
        "backtest_days": len(strategy)
    }


symbols, universe_source = get_symbols()

limit = int(os.getenv("MAX_SYMBOLS", "0"))

if limit > 0:
    symbols = symbols[:limit]

results = []
failed = []

for start in range(0, len(symbols), 30):

    batch = symbols[start:start + 30]
    tickers = [s + ".NS" for s in batch]

    print("Scanning", start, "of", len(symbols))

    try:
        data = yf.download(
            tickers,
            period="max",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            threads=4,
            progress=False,
            timeout=30
        )

        for symbol in batch:
            try:
                ticker = symbol + ".NS"

                if isinstance(data.columns, pd.MultiIndex):
                    df = data[ticker].copy()
                else:
                    if len(batch) != 1:
                        raise ValueError("Unexpected data format")
                    df = data.copy()

                results.append(analyse(symbol, df))

            except Exception as e:
                failed.append(symbol)
                print(symbol, str(e))

    except Exception as e:
        failed.extend(batch)
        print("Batch failed:", e)

    time.sleep(3)


if not results:
    raise RuntimeError(
        "No data retrieved. Previous results preserved."
    )

results.sort(
    key=lambda x: x["score"],
    reverse=True
)

report = {
    "version": "4.0",
    "generated": datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(),
    "source": "Yahoo Finance daily historical data",
    "universe_source": universe_source,
    "requested": len(symbols),
    "connected": len(results),
    "failed": failed,
    "stocks": results
}

Path("market_data.json").write_text(
    json.dumps(report, indent=2, allow_nan=False),
    encoding="utf-8"
)

pd.DataFrame(results).to_csv(
    "market_data.csv",
    index=False
)

print("Requested:", len(symbols))
print("Successful:", len(results))
print("Failed:", len(failed))
print("StockMind AI 4.0 scan completed")
