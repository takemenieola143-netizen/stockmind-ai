
import numpy as np
import pandas as pd

from sklearn.base import clone
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import (
    RandomForestClassifier,
    ExtraTreesClassifier,
    HistGradientBoostingClassifier
)
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss
)

from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier

HORIZONS = (1, 5, 10, 20)
SEED = 42


def get_models():
    return {
        "Logistic Regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=500)
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=100,
            max_depth=6,
            min_samples_leaf=30,
            n_jobs=2,
            random_state=SEED
        ),
        "Extra Trees": ExtraTreesClassifier(
            n_estimators=100,
            max_depth=7,
            min_samples_leaf=30,
            n_jobs=2,
            random_state=SEED
        ),
        "HistGradientBoosting":
            HistGradientBoostingClassifier(
                max_iter=100,
                max_depth=4,
                early_stopping=False,
                random_state=SEED
            ),
        "XGBoost": XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            n_jobs=2,
            random_state=SEED
        ),
        "LightGBM": LGBMClassifier(
            n_estimators=100,
            num_leaves=15,
            learning_rate=0.05,
            n_jobs=2,
            verbosity=-1,
            random_state=SEED
        ),
        "CatBoost": CatBoostClassifier(
            iterations=100,
            depth=5,
            learning_rate=0.05,
            verbose=False,
            thread_count=2,
            allow_writing_files=False,
            random_seed=SEED
        ),
        "Neural Network": make_pipeline(
            StandardScaler(),
            MLPClassifier(
                hidden_layer_sizes=(32, 16),
                max_iter=100,
                random_state=SEED
            )
        )
    }


def prepare_stock(symbol, features, close):

    data = features.copy().sort_index()
    data.index = pd.to_datetime(
        data.index
    ).tz_localize(None).normalize()

    close = close.copy()
    close.index = pd.to_datetime(
        close.index
    ).tz_localize(None).normalize()

    data = data.replace(
        [np.inf, -np.inf], np.nan
    )

    dates = pd.Series(
        close.index, index=close.index
    )

    for h in HORIZONS:
        future = close.shift(-h)

        data[f"target_{h}"] = (
            future > close
        ).astype(float).where(future.notna())

        data[f"end_{h}"] = dates.shift(-h)

    data["symbol"] = symbol
    data["date"] = data.index

    return data.tail(1500).reset_index(drop=True)


def add_market_features(data, market_close):

    market = market_close.copy()

    market.index = pd.to_datetime(
        market.index
    ).tz_localize(None).normalize()

    market = market.sort_index()

    context = pd.DataFrame({
        "market_return_1": market.pct_change(1),
        "market_return_5": market.pct_change(5),
        "market_return_20": market.pct_change(20),
        "market_trend": (
            market / market.rolling(50).mean() - 1
        ),
        "market_volatility": (
            market.pct_change().rolling(20).std()
        )
    })

    context.index.name = "date"

    return data.merge(
        context.reset_index(),
        on="date",
        how="left"
    )


def metrics(y, p, baseline):

    predicted = (p >= 0.5).astype(int)
    baseline_class = int(baseline >= 0.5)

    return {
        "accuracy": round(
            accuracy_score(y, predicted) * 100, 2
        ),
        "balanced_accuracy": round(
            balanced_accuracy_score(
                y, predicted
            ) * 100, 2
        ),
        "baseline_accuracy": round(
            np.mean(y == baseline_class) * 100, 2
        ),
        "brier_score": round(
            brier_score_loss(y, p), 4
        ),
        "baseline_brier": round(
            np.mean((y - baseline) ** 2), 4
        ),
        "test_samples": int(len(y))
    }


def sample_data(data, maximum=200000):

    if len(data) <= maximum:
        return data

    return data.sample(
        maximum,
        random_state=SEED
    ).sort_values("date")


def calibrator(probabilities, targets):

    probabilities = np.clip(
        probabilities, 0.00001, 0.99999
    )

    logits = np.log(
        probabilities / (1 - probabilities)
    ).reshape(-1, 1)

    model = LogisticRegression(max_iter=300)
    model.fit(logits, targets)

    return model


def calibrate(model, probabilities):

    p = np.clip(
        probabilities, 0.00001, 0.99999
    )

    logits = np.log(
        p / (1 - p)
    ).reshape(-1, 1)

    return model.predict_proba(logits)[:, 1]


def train_engine(data, market_close=None):

    if market_close is not None:
        data = add_market_features(
            data, market_close
        )

    feature_columns = [
        c for c in data.columns
        if c not in ("symbol", "date")
        and not c.startswith("target_")
        and not c.startswith("end_")
    ]

    data = data.replace(
        [np.inf, -np.inf], np.nan
    )

    data = data.dropna(
        subset=feature_columns
    ).sort_values("date")

    latest = data.groupby(
        "symbol", sort=False
    ).tail(1)

    results = {
        symbol: {} for symbol in latest["symbol"]
    }

    diagnostics = {}

    for h in HORIZONS:

        print(
            f"Training {h}-day models",
            flush=True
        )

        target = f"target_{h}"
        end = f"end_{h}"

        history = data.dropna(
            subset=[target, end]
        )

        dates = np.sort(
            history["date"].unique()
        )

        if len(dates) < 300:
            continue

        selection_dates = [
            dates[int(len(dates) * x)]
            for x in (0.40, 0.50, 0.60, 0.70)
        ]

        calibration_start = selection_dates[-1]
        test_start = dates[int(len(dates) * 0.85)]

        leaderboard = []
        candidates = get_models()

        for name, prototype in candidates.items():

            try:
                losses = []
                benchmark_losses = []
                fold_accuracies = []

                for start, stop in zip(
                    selection_dates[:-1],
                    selection_dates[1:]
                ):

                    train = history[
                        (history["date"] < start) &
                        (history[end] < start)
                    ]

                    validation = history[
                        (history["date"] >= start) &
                        (history["date"] < stop) &
                        (history[end] < stop)
                    ]

                    train = sample_data(train)
                    validation = sample_data(validation)

                    if (
                        len(train) < 1000 or
                        len(validation) < 300 or
                        train[target].nunique() < 2 or
                        validation[target].nunique() < 2
                    ):
                        continue

                    model = clone(prototype)

                    model.fit(
                        train[feature_columns],
                        train[target].astype(int)
                    )

                    p = model.predict_proba(
                        validation[feature_columns]
                    )[:, 1]

                    y = validation[target].astype(int)
                    base = train[target].mean()

                    losses.append(
                        brier_score_loss(y, p)
                    )

                    benchmark_losses.append(
                        float(np.mean((y - base) ** 2))
                    )

                    fold_accuracies.append(
                        balanced_accuracy_score(
                            y, (p >= 0.5).astype(int)
                        )
                    )

                if len(losses) == 3:
                    leaderboard.append({
                        "model": name,
                        "brier": float(np.mean(losses)),
                        "baseline_brier": float(
                            np.mean(benchmark_losses)
                        ),
                        "balanced_accuracy": float(
                            np.mean(fold_accuracies)
                        )
                    })

            except Exception as e:
                print(name, h, str(e), flush=True)

        leaderboard.sort(
            key=lambda row: row["brier"]
        )

        winners = [
            row["model"]
            for row in leaderboard
            if row["brier"] < row["baseline_brier"]
            and row["balanced_accuracy"] > 0.50
        ][:3]

        diagnostics[str(h)] = {
            "leaderboard": leaderboard,
            "selected_models": winners
        }

        if not winners:
            for symbol in results:
                results[symbol][f"prediction_{h}d"] = {
                    "horizon": h,
                    "status": "No signal",
                    "direction": "No signal",
                    "up_probability": None,
                    "reason": "No model beat validation baseline"
                }
            continue

        train = history[
            (history["date"] < calibration_start) &
            (history[end] < calibration_start)
        ]

        calibration = history[
            (history["date"] >= calibration_start) &
            (history["date"] < test_start) &
            (history[end] < test_start)
        ]

        test = history[
            history["date"] >= test_start
        ]

        train = sample_data(train)
        calibration = sample_data(calibration)
        test = sample_data(test)

        if (
            len(train) < 1000 or
            len(calibration) < 300 or
            len(test) < 300 or
            calibration[target].nunique() < 2 or
            test[target].nunique() < 2
        ):
            continue

        ensemble = []

        for name in winners:
            model = clone(candidates[name])
            model.fit(
                train[feature_columns],
                train[target].astype(int)
            )
            ensemble.append(model)

        def predict(frame):
            return np.mean([
                model.predict_proba(
                    frame[feature_columns]
                )[:, 1]
                for model in ensemble
            ], axis=0)

        calibration_prob = predict(calibration)

        calibration_model = calibrator(
            calibration_prob,
            calibration[target].astype(int)
        )

        test_prob = calibrate(
            calibration_model,
            predict(test)
        )

        evaluation = metrics(
            test[target].to_numpy(dtype=int),
            test_prob,
            float(train[target].mean())
        )

        reliable = (
            evaluation["accuracy"] >
            evaluation["baseline_accuracy"]
            and evaluation["balanced_accuracy"] > 51
            and evaluation["brier_score"] <
            evaluation["baseline_brier"]
        )

        diagnostics[str(h)]["evaluation"] = evaluation
        diagnostics[str(h)]["reliable"] = reliable

        probabilities = calibrate(
            calibration_model,
            predict(latest)
        )

        for symbol, probability in zip(
            latest["symbol"], probabilities
        ):

            direction = "No signal"

            if reliable:
                if probability >= 0.60:
                    direction = "Bullish"
                elif probability <= 0.40:
                    direction = "Bearish"
                else:
                    direction = "Neutral"

            results[symbol][f"prediction_{h}d"] = {
                "horizon": h,
                "status": (
                    "Available" if reliable
                    else "No signal"
                ),
                "direction": direction,
                "up_probability": (
                    round(float(probability) * 100, 2)
                    if reliable else None
                ),
                "models": winners,
                "validation_scope": "Shared market model",
                **evaluation
            }

    return results, diagnostics
