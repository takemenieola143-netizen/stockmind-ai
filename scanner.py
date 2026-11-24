
import json, datetime, time
import pandas as pd
import yfinance as yf
from pathlib import Path

# Starter universe; optionally supply symbols.csv
symbols = 'RELIANCE TCS INFY HDFCBANK SBIN ITC LT AXISBANK ICICIBANK WIPRO ONGC NTPC POWERGRID TATAMOTORS TATASTEEL COALINDIA BEL IRFC YESBANK IDEA SUZLON NHPC'.split()

if Path('symbols.csv').exists():
    symbols = pd.read_csv('symbols.csv')['symbol'].dropna().astype(str).unique().tolist()

results = []
failed = []

for start in range(0, len(symbols), 50):
    batch = symbols[start:start+50]
    tickers = [s+'.NS' for s in batch]

    try:
        data = yf.download(
            tickers,
            period='max',
            auto_adjust=True,
            group_by='ticker',
            threads=4,
            progress=False
        )
    except Exception:
        failed.extend(batch)
        continue

    for s, t in zip(batch, tickers):
        try:
            d = data[t].dropna(subset=['Close','Volume'])
            c = d.Close
            v = d.Volume

            if len(c) < 201:
                raise ValueError('insufficient history')

            delta = c.diff()

            gain = delta.clip(lower=0).ewm(
                alpha=1/14,
                adjust=False,
                min_periods=14
            ).mean()

            loss = (-delta.clip(upper=0)).ewm(
                alpha=1/14,
                adjust=False,
                min_periods=14
            ).mean()

            rsi = (100-100/(1+gain/loss)).fillna(50)

            ma20 = c.rolling(20).mean()
            ma50 = c.rolling(50).mean()
            ma200 = c.rolling(200).mean()

            macd = (
                c.ewm(span=12,adjust=False).mean()
                - c.ewm(span=26,adjust=False).mean()
            )

            signal = macd.ewm(
                span=9,
                adjust=False
            ).mean()

            sd = c.rolling(20).std()
            p = float(c.iloc[-1])

            atr = pd.concat([
                d.High-d.Low,
                (d.High-c.shift()).abs(),
                (d.Low-c.shift()).abs()
            ],axis=1).max(axis=1).rolling(14).mean().iloc[-1]

            score = (
                25*int(p>ma50.iloc[-1])
                +25*int(p>ma200.iloc[-1])
                +25*int(macd.iloc[-1]>signal.iloc[-1])
                +25*int(50<=rsi.iloc[-1]<=70)
            )

            position = (c>ma200).shift(1).fillna(False)
            ret = c.pct_change().fillna(0)

            test = (
                (1+ret*position).iloc[-252:].prod()-1
            )

            results.append(dict(
                symbol=s,
                price=round(p,2),
                volume=int(v.iloc[-1]),
                change=round((p/c.iloc[-2]-1)*100,2),
                date=str(d.index[-1].date()),
                rsi=round(float(rsi.iloc[-1]),2),
                macd=round(float(macd.iloc[-1]),3),
                signal=round(float(signal.iloc[-1]),3),
                sma20=round(float(ma20.iloc[-1]),2),
                sma50=round(float(ma50.iloc[-1]),2),
                sma200=round(float(ma200.iloc[-1]),2),
                ema20=round(float(c.ewm(
                    span=20,
                    adjust=False
                ).mean().iloc[-1]),2),
                upper=round(float((ma20+2*sd).iloc[-1]),2),
                lower=round(float((ma20-2*sd).iloc[-1]),2),
                high=round(float(d.High.max()),2),
                low=round(float(d.Low.min()),2),
                drawdown=round((p/d.High.max()-1)*100,2),
                score=score,
                stop=round(max(0,p-2*atr),2),
                target=round(p+4*atr,2),
                backtest=round(float(test)*100,2),
                history=[
                    round(float(x),2)
                    for x in c.tail(90)
                ]
            ))

        except Exception as e:
            failed.append(s)
            print(s,e)

    time.sleep(2)

if not results:
    raise RuntimeError(
        'No usable market data; previous snapshot preserved'
    )

Path('market_data.json').write_text(
    json.dumps(
        dict(
            generated=datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            requested=len(symbols),
            failed=failed,
            stocks=results
        ),
        allow_nan=False
    )
)
