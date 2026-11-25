import json
import math
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


def analyse_chart(symbol, data, now=None):
    now = now or datetime.now(ZoneInfo('Asia/Kolkata'))
    now = now.astimezone(ZoneInfo('Asia/Kolkata'))
    data = data.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data.index = pd.to_datetime(data.index)
    if data.index.tz is not None:
        data.index = data.index.tz_convert('Asia/Kolkata').tz_localize(None)
    data = data.sort_index()
    data = data[~data.index.duplicated(keep='last')]
    dates = data.index.date
    data = data[dates <= now.date()]
    if now.time() < time(16, 0):
        data = data[data.index.date < now.date()]
    columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    data = data[columns].apply(pd.to_numeric, errors='coerce')
    data = data.dropna()
    data = data[data.apply(lambda r: all(math.isfinite(v) for v in r), axis=1)]
    data = data[(data.Low > 0) & (data.High >= data[['Open','Close']].max(axis=1)) & (data.Low <= data[['Open','Close']].min(axis=1)) & (data.Volume >= 0)]
    if len(data) < 51:
        raise ValueError('At least 51 valid daily candles required')
    o, h, l, c, v = (data[k] for k in columns)
    a, b = data.iloc[-2], data.iloc[-1]
    body = abs(b.Close - b.Open)
    span = b.High - b.Low
    lower = min(b.Open, b.Close) - b.Low
    upper = b.High - max(b.Open, b.Close)
    patterns = []
    if span > 0:
        if body <= 0.1 * span:
            patterns.append('Doji')
        elif lower >= 2 * body and upper <= body:
            patterns.append('Hammer-shaped candle')
        elif upper >= 2 * body and lower <= body:
            patterns.append('Shooting-star-shaped candle')
    if a.Close < a.Open and b.Close > b.Open and b.Open <= a.Close and b.Close >= a.Open:
        patterns.append('Bullish engulfing')
    if a.Close > a.Open and b.Close < b.Open and b.Open >= a.Close and b.Close <= a.Open:
        patterns.append('Bearish engulfing')
    support = float(l.iloc[-21:-1].min())
    resistance = float(h.iloc[-21:-1].max())
    avg_volume = float(v.iloc[-21:-1].mean())
    rel_volume = float(b.Volume / avg_volume) if avg_volume > 0 else None
    true_range = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr = float(true_range.tail(14).mean())
    close = float(b.Close)
    trend = 'Up' if close > c.tail(20).mean() > c.tail(50).mean() else 'Down' if close < c.tail(20).mean() < c.tail(50).mean() else 'Mixed'
    entry = round(max(resistance, float(b.High)) + 0.1 * atr, 2)
    stop = round(float(l.tail(5).min()) - 0.1 * atr, 2)
    risk = entry - stop
    plan = None
    if 0 < stop < entry and atr > 0 and risk / entry <= 0.08:
        plan = {'entry_trigger': entry, 'stop_loss': stop, 'target': round(entry + 2 * risk, 2), 'risk_pct': round(100*risk/entry, 2), 'reward_risk': 2}
    candles = []
    for date, row in data.tail(90).iterrows():
        candles.append({'date': date.date().isoformat(), **{k.lower(): float(row[k]) for k in columns}})
    return {'symbol': symbol, 'price_date': data.index[-1].date().isoformat(), 'generated': now.isoformat(), 'close': close, 'trend': trend, 'patterns': patterns, 'support_20d': support, 'resistance_20d': resistance, 'relative_volume': rel_volume, 'atr_14': atr, 'breakout': bool(close > resistance and rel_volume is not None and rel_volume >= 1.5), 'reference_plan': plan, 'decision': 'WAIT', 'reason': 'Chart research only; freshness, fundamentals, news and validated trade performance not confirmed', 'candles': candles}


if __name__ == '__main__':
    import yfinance as yf
    symbol = (sys.argv[1] if len(sys.argv) > 1 else 'DIXON').upper()
    ticker = symbol if symbol.endswith('.NS') else symbol + '.NS'
    data = yf.download(ticker, period='1y', interval='1d', auto_adjust=False, progress=False, threads=False)
    result = analyse_chart(symbol, data)
    Path('chart_data.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print('Chart report saved:', symbol, result['price_date'])
