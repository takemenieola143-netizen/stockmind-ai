
import json
import time
import datetime
import os
import numpy as np
import pandas as pd
import yfinance as yf

from pathlib import Path
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, brier_score_loss

# StockMind AI 5.0
# Historical research and machine learning engine

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

        symbols = sorted(
            set(df["SYMBOL"].dropna().str.strip())
        )

        if symbols:
            return symbols, "NSE"

    except Exception as e:
        print("NSE list unavailable:", e)

    if Path("symbols.csv").exists():
        df = pd.read_csv("symbols.csv")
        df.columns = df.columns.str.strip().str.lower()

        return sorted(set(
            df["symbol"].dropna().astype(str).str.strip()
        )), "Local list"

    return STARTER, "Starter list"


def number(value, digits=2):
    try:
        value = float(value)

        if not np.isfinite(value):
            return None

        return round(value, digits)

    except Exception:
        return None


def model_prediction(features, close, horizon):

    output = {
        "horizon": horizon,
        "status": "Insufficient history",
        "up_probability": None,
        "direction": None,
        "accuracy": None,
        "balanced_accuracy": None,
        "baseline_accuracy": None,
        "brier_score": None,
        "test_samples": 0
    }

    try:
        future = close.shift(-horizon)

        target = (
            future > close
        ).astype(float).where(future.notna())

        dataset = features.copy()
        dataset["target"] = target

        dataset = dataset.replace(
            [np.inf, -np.inf], np.nan
        ).dropna().tail(1500)

        if len(dataset) < 350:
            return output

        X = dataset.drop(columns="target")
        y = dataset["target"].astype(int)

        split = int(len(dataset) * 0.8)

        # Purge overlapping future labels
        X_train = X.iloc[:split-horizon]
        y_train = y.iloc[:split-horizon]

        X_test = X.iloc[split:]
        y_test = y.iloc[split:]

        if y_train.nunique() < 2:
            return output

        model = HistGradientBoostingClassifier(
            max_iter=50,
            max_depth=3,
            learning_rate=0.05,
            min_samples_leaf=20,
            early_stopping=False,
            random_state=42
        )

        model.fit(X_train, y_train)

        predicted = model.predict(X_test)
        probabilities = model.predict_proba(X_test)[:, 1]

        baseline_class = int(y_train.mean() >= 0.5)

        output["accuracy"] = number(
            accuracy_score(y_test, predicted) * 100
        )

        output["balanced_accuracy"] = number(
            balanced_accuracy_score(
                y_test, predicted
            ) * 100
        )

        output["baseline_accuracy"] = number(
            (y_test == baseline_class).mean() * 100
        )

        output["brier_score"] = number(
            brier_score_loss(y_test, probabilities), 4
        )

        output["test_samples"] = len(y_test)

        # Refit after evaluating historical performance
        model.fit(X, y)

        latest = features.iloc[[-1]].replace(
            [np.inf, -np.inf], np.nan
        )

        if latest.isna().any(axis=None):
            return output

        probability = float(
            model.predict_proba(latest)[0][1]
        )

        output["up_probability"] = number(
            probability * 100
        )

        if probability >= 0.60:
            output["direction"] = "Bullish"

        elif probability <= 0.40:
            output["direction"] = "Bearish"

        else:
            output["direction"] = "Neutral"

        output["status"] = "Available"

        return output

    except Exception as e:
        output["status"] = "Model unavailable"
        print("ML error:", str(e))
        return output


def analyse(symbol, df):

    df = df.dropna(
        subset=["Close", "Open", "High", "Low", "Volume"]
    ).sort_index()

    df = df[~df.index.duplicated(keep="last")]

    df = df[
        (df["Close"] > 0) &
        (df["Open"] > 0) &
        (df["High"] > 0) &
        (df["Low"] > 0)
    ]

    if len(df) < 60:
        raise ValueError("Insufficient history")

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
    opens = df["Open"]

    price = float(close.iloc[-1])

    change = (
        price / close.iloc[-2] - 1
    ) * 100

    # Adjusted history for return calculations

    if "Adj Close" in df.columns:
        adjusted = df["Adj Close"].where(
            df["Adj Close"] > 0
        ).fillna(close)
    else:
        adjusted = close.copy()

    factor = adjusted / close

    adj_open = opens * factor
    adj_high = high * factor
    adj_low = low * factor

    sma20 = adjusted.rolling(20).mean()
    sma50 = adjusted.rolling(50).mean()
    sma200 = adjusted.rolling(200).mean()

    delta = adjusted.diff()

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

    rsi = rsi.mask(
        (avg_gain == 0) & (avg_loss == 0), 50
    )

    ema12 = adjusted.ewm(
        span=12, adjust=False
    ).mean()

    ema26 = adjusted.ewm(
        span=26, adjust=False
    ).mean()

    macd = ema12 - ema26

    signal = macd.ewm(
        span=9, adjust=False
    ).mean()

    previous = adjusted.shift(1)

    tr = pd.concat([
        adj_high - adj_low,
        (adj_high - previous).abs(),
        (adj_low - previous).abs()
    ], axis=1).max(axis=1)

    atr_series = tr.rolling(14).mean()

    latest_factor = float(factor.iloc[-1])

    atr = atr_series.iloc[-1] / latest_factor

    average_volume = volume.shift(1).rolling(20).mean()

    relative_volume = (
        volume / average_volume.replace(0, np.nan)
    )

    ath = high.max()
    atl = low.min()

    # Technical scoring

    conditions = [
        (
            adjusted > sma20,
            "Above 20-day average"
        ),
        (
            adjusted > sma50,
            "Above 50-day average"
        ),
        (
            adjusted > sma200,
            "Above 200-day average"
        ),
        (
            rsi.between(45, 65),
            "RSI between 45 and 65"
        ),
        (
            macd > signal,
            "Positive MACD state"
        )
    ]

    score_series = pd.Series(
        0, index=df.index, dtype=float
    )

    reasons = []

    for condition, reason in conditions:

        score_series += condition.astype(int) * 20

        if bool(condition.iloc[-1]):
            reasons.append(reason)

    score = int(score_series.iloc[-1])

    # Historical strategy:
    # Score >= 80 at close, enter next open.
    # Exit when score falls below 80.

    desired = (
        (score_series >= 80) &
        sma200.notna()
    ).astype(float)

    position = desired.shift(1).fillna(0)

    forward_return = (
        adj_open.shift(-1) / adj_open - 1
    )

    turnover = position.diff().abs().fillna(
        position.iloc[0]
    )

    # Assumed cost: 0.2% per transaction side

    cost = 0.002

    strategy = (
        (1 - turnover * cost) *
        (1 + position * forward_return) - 1
    )

    test = pd.DataFrame({
        "strategy": strategy,
        "benchmark": forward_return,
        "position": position,
        "open": adj_open,
        "eligible": sma200.shift(1).notna()
    })

    test = test[
        test["eligible"]
    ].dropna().tail(252)

    trades = []
    entry = None

    if len(test):

        test = test.copy()

        # Charge entry if already invested
        # at the start of the evaluation window.

        if test["position"].iloc[0] == 1:
            first = test.index[0]

            if turnover.loc[first] == 0:
                test.loc[first, "strategy"] = (
                    (1 + test.loc[first, "strategy"])
                    * (1 - cost) - 1
                )

        for _, row in test.iterrows():

            if row["position"] == 1 and entry is None:
                entry = row["open"]

            elif row["position"] == 0 and entry is not None:

                trade_return = (
                    row["open"] * (1 - cost) /
                    (entry * (1 + cost)) - 1
                )

                trades.append(trade_return)
                entry = None

        equity = (
            1 + test["strategy"]
        ).cumprod()

        drawdown = (
            equity /
            equity.cummax().clip(lower=1) - 1
        ).min()

        backtest = (
            equity.iloc[-1] - 1
        ) * 100

        benchmark = (
            (1 + test["benchmark"]).prod() - 1
        ) * 100

        active_days = int(
            test["position"].sum()
        )

    else:

        backtest = None
        benchmark = None
        drawdown = None
        active_days = 0

    win_rate = (
        sum(t > 0 for t in trades) /
        len(trades) * 100
        if trades else None
    )

    # Machine learning features
    # All features use information available
    # on or before the signal date.

    features = pd.DataFrame({

        "return_1": adjusted.pct_change(1),
        "return_5": adjusted.pct_change(5),
        "return_10": adjusted.pct_change(10),
        "return_20": adjusted.pct_change(20),

        "rsi": rsi / 100,

        "sma20_gap": adjusted / sma20 - 1,
        "sma50_gap": adjusted / sma50 - 1,
        "sma200_gap": adjusted / sma200 - 1,

        "macd_gap": (macd - signal) / adjusted,

        "volatility": (
            adjusted.pct_change().rolling(20).std()
        ),

        "atr_pct": atr_series / adjusted,

        "relative_volume": relative_volume.clip(
            lower=0, upper=20
        ),

        "score": score_series / 100

    }, index=df.index)

    prediction_1d = model_prediction(
        features, adjusted, 1
    )

    prediction_5d = model_prediction(
        features, adjusted, 5
    )

    volatility = (
        adjusted.pct_change().tail(60).std()
        * np.sqrt(252) * 100
    )

    turnover_value = (
        close * volume
    ).tail(20).mean()

    if price <= 5 or turnover_value < 1000000:
        risk = "Very High"

    elif volatility > 50:
        risk = "High"

    elif volatility > 25:
        risk = "Moderate"

    else:
        risk = "Lower relative volatility"

    return {

        "symbol": symbol,
        "date": str(df.index[-1].date()),

        "price": number(price),
        "change": number(change),

        "volume": number(volume.iloc[-1], 0),

        "relative_volume": number(
            relative_volume.iloc[-1]
        ),

        "rsi": number(rsi.iloc[-1]),

        "macd": number(
            macd.iloc[-1] / latest_factor
        ),

        "macd_signal": number(
            signal.iloc[-1] / latest_factor
        ),

        "sma20": number(
            sma20.iloc[-1] / latest_factor
        ),

        "sma50": number(
            sma50.iloc[-1] / latest_factor
        ),

        "sma200": number(
            sma200.iloc[-1] / latest_factor
        ),

        "ath": number(ath),
        "atl": number(atl),

        "history_start": str(
            df.index[0].date()
        ),

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

        "atr": number(atr),

        "backtest_return": number(backtest),

        "benchmark_return": number(benchmark),

        "max_drawdown": number(
            drawdown * 100
            if drawdown is not None else None
        ),

        "backtest_days": len(test),

        "backtest_active_days": active_days,

        "backtest_trades": len(trades),

        "win_rate": number(win_rate),

        "backtest_strategy": (
            "Score >= 80, next-open execution"
        ),

        "transaction_cost_pct": 0.2,

        "prediction_1d": prediction_1d,

        "prediction_5d": prediction_5d,

        "volatility": number(volatility),

        "average_daily_turnover": number(
            turnover_value
        ),

        "risk": risk

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

    print(
        "Scanning", start, "of", len(symbols),
        flush=True
    )

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

                if isinstance(
                    data.columns, pd.MultiIndex
                ):
                    df = data[ticker].copy()

                else:

                    if len(batch) != 1:
                        raise ValueError(
                            "Unexpected data format"
                        )

                    df = data.copy()

                results.append(
                    analyse(symbol, df)
                )

            except Exception as e:

                failed.append(symbol)

                print(
                    symbol, str(e), flush=True
                )

    except Exception as e:

        failed.extend(batch)

        print("Batch failed:", e, flush=True)

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

    "version": "5.0",

    "generated": datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(),

    "source": "Yahoo Finance daily historical data",

    "universe_source": universe_source,

    "requested": len(symbols),

    "connected": len(results),

    "failed": failed,

    "ml_available": sum(
        x["prediction_1d"]["status"] == "Available"
        for x in results
    ),

    "stocks": results

}


temporary = Path("market_data.tmp")

temporary.write_text(
    json.dumps(
        report,
        indent=2,
        allow_nan=False
    ),
    encoding="utf-8"
)

temporary.replace("market_data.json")


pd.json_normalize(results).to_csv(
    "market_data.csv",
    index=False
)


print("Requested:", len(symbols))
print("Successful:", len(results))
print("Failed:", len(failed))
print("ML available:", report["ml_available"])
print("StockMind AI 5.0 scan completed")
