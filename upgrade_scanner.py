
from pathlib import Path
import ast

path = Path("scanner.py")
source = path.read_text(encoding="utf-8")

if '"version": "6.0"' in source:
    print("Scanner already upgraded.")
    raise SystemExit(0)

original = source


def replace(old, new):
    global source

    if source.count(old) != 1:
        raise RuntimeError(
            "Upgrade stopped: unexpected source code."
        )

    source = source.replace(old, new, 1)


replace(
    "import yfinance as yf",
    """import yfinance as yf

from zoneinfo import ZoneInfo
from ai_engine import (
    prepare_stock,
    train_engine,
    HORIZONS
)

training_frames = []


def completed_sessions(df):
    df = df.copy()
    now = datetime.datetime.now(
        ZoneInfo("Asia/Kolkata")
    )

    cutoff = datetime.time(16, 0)

    if now.time() < cutoff:
        df = df[df.index.date < now.date()]
    else:
        df = df[df.index.date <= now.date()]

    return df


def empty_prediction(h):
    return {
        "horizon": h,
        "status": "No signal",
        "direction": "No signal",
        "up_probability": None,
        "accuracy": None,
        "balanced_accuracy": None,
        "baseline_accuracy": None,
        "brier_score": None,
        "test_samples": 0
    }
"""
)

replace(
    "def analyse(symbol, df):",
    """def analyse(symbol, df):

    df = completed_sessions(df)"""
)

replace(
    """    prediction_1d = model_prediction(
        features, adjusted, 1
    )

    prediction_5d = model_prediction(
        features, adjusted, 5
    )""",
    """    training_frames.append(
        prepare_stock(
            symbol,
            features,
            adjusted
        )
    )

    prediction_1d = empty_prediction(1)
    prediction_5d = empty_prediction(5)"""
)

replace(
    "results.sort(",
    """print(
    "Preparing shared AI training data",
    flush=True
)

market = yf.download(
    "^NSEI",
    period="max",
    interval="1d",
    auto_adjust=True,
    progress=False,
    threads=False,
    timeout=30
)

if market.empty:
    raise RuntimeError(
        "Nifty data unavailable. Previous report preserved."
    )

market = completed_sessions(market)

market_close = market["Close"]

if isinstance(market_close, pd.DataFrame):
    market_close = market_close.iloc[:, 0]

market_close = market_close.dropna()

if market_close.empty:
    raise RuntimeError("No completed Nifty data")

training_data = pd.concat(
    training_frames,
    ignore_index=True
)

training_frames.clear()

predictions, diagnostics = train_engine(
    training_data,
    market_close
)

for stock in results:

    stock_predictions = predictions.get(
        stock["symbol"], {}
    )

    for horizon in HORIZONS:

        key = f"prediction_{horizon}d"

        output = empty_prediction(horizon)

        output.update(
            stock_predictions.get(key, {})
        )

        stock[key] = output

results.sort("""
)

replace(
    '"version": "5.0",',
    '''"version": "6.0",

    "ai_diagnostics": diagnostics,

    "prediction_horizons": list(HORIZONS),

    "prediction_scope": "Shared market model",

    "market_context": "Nifty 50",

    "completed_sessions_only": True,'''
)

replace(
    'print("StockMind AI 5.0 scan completed")',
    'print("StockMind AI 6.0 scan completed")'
)

ast.parse(source)

backup = Path("scanner_v5_backup.py")

if not backup.exists():
    backup.write_text(
        original,
        encoding="utf-8"
    )

temporary = Path("scanner_upgrade.tmp")

temporary.write_text(
    source,
    encoding="utf-8"
)

temporary.replace(path)

print("StockMind AI 6.0 upgrade successful.")
print("Original scanner backup preserved.")
