
import csv
import io
import math
import sys
import zipfile

from datetime import date
from urllib.request import Request, urlopen


def download_nse_market(trading_date):

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

    print("Downloading NSE market:", trading_date)

    with urlopen(request, timeout=60) as response:
        content = response.read()

    with zipfile.ZipFile(io.BytesIO(content)) as archive:

        files = [
            name for name in archive.namelist()
            if name.lower().endswith(".csv")
        ]

        if len(files) != 1:
            raise ValueError("Unexpected NSE report")

        text = archive.read(files[0]).decode(
            "utf-8-sig"
        )

    reader = csv.DictReader(io.StringIO(text))

    required = {
        "TckrSymb", "SctySrs", "TradDt",
        "OpnPric", "HghPric", "LwPric",
        "ClsPric", "TtlTradgVol"
    }

    if not required.issubset(
        set(reader.fieldnames or [])
    ):
        raise ValueError("Invalid report columns")

    candles = {}
    rejected = 0
    duplicates = set()

    for row in reader:

        if row["SctySrs"].strip() != "EQ":
            continue

        symbol = row["TckrSymb"].strip()

        if not symbol:
            rejected += 1
            continue

        if row["TradDt"].strip() != trading_date:
            raise ValueError("Trading date mismatch")

        if symbol in candles or symbol in duplicates:
            duplicates.add(symbol)
            candles.pop(symbol, None)
            continue

        try:

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
                ["open", "high", "low",
                 "close", "volume"]
            ]

            if not all(
                math.isfinite(v) for v in values
            ):
                raise ValueError("Invalid numbers")

            if not (
                0 < candle["low"]
                <= min(candle["open"], candle["close"])
                <= max(candle["open"], candle["close"])
                <= candle["high"]
                and candle["volume"] >= 0
            ):
                raise ValueError("Invalid candle")

            candles[symbol] = candle

        except (ValueError, TypeError):

            rejected += 1

    if not candles:
        raise RuntimeError("No valid NSE candles")

    print("NSE market download successful")
    print("Trading date:", trading_date)
    print("Valid equity candles:", len(candles))
    print("Rejected rows:", rejected)
    print("Duplicate symbols:", len(duplicates))

    return candles


if __name__ == "__main__":

    trading_date = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "2026-11-25"
    )

    market = download_nse_market(trading_date)

    assert len(market) >= 2000, (
        "Insufficient market coverage"
    )

    print("Market coverage test: PASSED")
    print("NSE batch engine: PASSED")
