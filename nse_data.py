
import csv
import io
import json
import math
import sys
import zipfile

from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen


def download_nse_candle(symbol, trading_date):

    symbol = symbol.strip().upper()
    symbol = symbol.removesuffix(".NS")

    day = date.fromisoformat(trading_date)
    stamp = day.strftime("%Y%m%d")

    filename = (
        f"BhavCopy_NSE_CM_0_0_0_"
        f"{stamp}_F_0000.csv.zip"
    )

    url = (
        "https://nsearchives.nseindia.com"
        "/content/cm/" + filename
    )

    request = Request(
        url,
        headers={
            "User-Agent": "StockMind Research",
            "Accept": "application/zip"
        }
    )

    print("Requesting NSE report:", trading_date)

    with urlopen(request, timeout=30) as response:
        content = response.read()

    with zipfile.ZipFile(io.BytesIO(content)) as archive:

        files = [
            name for name in archive.namelist()
            if name.lower().endswith(".csv")
        ]

        if len(files) != 1:
            raise ValueError("Unexpected report format")

        text = archive.read(files[0]).decode(
            "utf-8-sig"
        )

    reader = csv.DictReader(io.StringIO(text))

    matches = []

    for row in reader:

        if (
            row["TckrSymb"].strip() == symbol
            and row["SctySrs"].strip() == "EQ"
        ):

            matches.append(row)

    if len(matches) != 1:
        raise ValueError(
            "Unique NSE equity record unavailable"
        )

    row = matches[0]

    if row["TradDt"].strip() != trading_date:
        raise ValueError("Trading date mismatch")

    candle = {
        "symbol": symbol,
        "date": trading_date,
        "open": float(row["OpnPric"]),
        "high": float(row["HghPric"]),
        "low": float(row["LwPric"]),
        "close": float(row["ClsPric"]),
        "volume": float(row["TtlTradgVol"]),
        "source": "NSE Bhavcopy"
    }

    values = [
        candle[k] for k in
        ["open", "high", "low", "close", "volume"]
    ]

    if not all(math.isfinite(v) for v in values):
        raise ValueError("Invalid numeric data")

    if not (
        candle["low"] > 0
        and candle["high"] >= max(
            candle["open"], candle["close"]
        )
        and candle["low"] <= min(
            candle["open"], candle["close"]
        )
        and candle["volume"] >= 0
    ):
        raise ValueError("Invalid candle")

    return candle


if __name__ == "__main__":

    symbol = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "DIXON"
    )

    trading_date = (
        sys.argv[2]
        if len(sys.argv) > 2
        else "2026-11-25"
    )

    candle = download_nse_candle(
        symbol, trading_date
    )

    print("NSE download successful")
    print("Symbol:", candle["symbol"])
    print("Trading date:", candle["date"])
    print("Candle validation: PASSED")

    market_file = Path("market_data.json")

    if market_file.exists():

        market = json.loads(
            market_file.read_text(encoding="utf-8")
        )

        stock = next(
            (
                s for s in market.get("stocks", [])
                if s.get("symbol") == candle["symbol"]
            ),
            None
        )

        if stock:

            same_date = (
                stock.get("date") == candle["date"]
            )

            scanner_price = float(stock["price"])

            same_price = (
                abs(scanner_price - candle["close"])
                <= 0.05
            )

            print("Date matches scanner:", same_date)
            print("Price matches scanner:", same_price)

    print("NSE diagnostic completed")
