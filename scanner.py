
import yfinance as yf
import csv
import math

symbols = [
    "RELIANCE", "TCS", "INFY",
    "HDFCBANK", "SBIN", "ITC",
    "TATASTEEL", "WIPRO", "ONGC",
    "NTPC", "POWERGRID", "YESBANK",
    "IDEA", "SUZLON", "IRFC",
    "RVNL", "PNB", "BANKBARODA",
    "COALINDIA", "BEL"
]

results = []

for symbol in symbols:
    try:
        stock = yf.Ticker(symbol + ".NS")
        data = stock.history(
            period="1mo",
            interval="1d",
            auto_adjust=False
        ).dropna(subset=["Close", "Volume"])

        if len(data) < 2:
            continue

        price = float(data["Close"].iloc[-1])
        previous = float(data["Close"].iloc[-2])
        volume = int(data["Volume"].iloc[-1])

        if previous <= 0 or price <= 0:
            continue

        change = ((price - previous) / previous) * 100

        if not all(math.isfinite(v) for v in [price, change]):
            continue

        results.append([
            symbol,
            round(price, 2),
            volume,
            round(change, 2)
        ])

        print(symbol, price, volume, change)

    except Exception as error:
        print(symbol, str(error))

if not results:
    raise RuntimeError("No market data retrieved")

with open("market_data.csv", "w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(["symbol", "price", "volume", "change"])
    writer.writerows(results)

print("Market scan completed:", len(results), "stocks")
