"""抓取加密资产日频收盘价（Binance 公共行情接口，无需 API Key）。

用法：python3 fetch_data.py
输出：data/<SYMBOL>.csv，两列 date,close
"""
import csv
import json
import os
import time
import urllib.request

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
DAYS = 730                      # 约两年日频数据
URL = ("https://api.binance.com/api/v3/klines"
       "?symbol={symbol}&interval=1d&limit={limit}")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def fetch(symbol, days=DAYS, retries=3):
    url = URL.format(symbol=symbol, limit=days)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:                     # 网络抖动时退避重试
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    return []


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for symbol in SYMBOLS:
        rows = fetch(symbol)
        path = os.path.join(OUT_DIR, f"{symbol}.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["date", "close"])
            for candle in rows:
                # kline: [open_time_ms, open, high, low, close, volume, ...]
                day = time.strftime("%Y-%m-%d", time.gmtime(candle[0] / 1000))
                writer.writerow([day, float(candle[4])])
        print(f"{symbol}: {len(rows)} 条日线 -> {path}")


if __name__ == "__main__":
    main()
