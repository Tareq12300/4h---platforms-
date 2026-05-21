import os
import time
import threading
import requests
import pandas as pd
from flask import Flask

app = Flask(__name__)

# =========================
# VARIABLES
# =========================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CMC_API_KEY = os.getenv("CMC_API_KEY")

TRADE_MODE = os.getenv("TRADE_MODE", "both").lower()

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))
CMC_TOP_N = int(os.getenv("CMC_TOP_N", "1000"))

MAX_MARKET_CAP = float(os.getenv("MAX_MARKET_CAP", "100000000"))

SCALP_TIMEFRAME = os.getenv("SCALP_TIMEFRAME", "15m")
SCALP_STOCH_RSI_MAX = float(os.getenv("SCALP_STOCH_RSI_MAX", "30"))
SCALP_VOLUME_RATIO = float(os.getenv("SCALP_VOLUME_RATIO", "1.0"))

SWING_TIMEFRAME = os.getenv("SWING_TIMEFRAME", "4h")
SWING_STOCH_RSI_MAX = float(os.getenv("SWING_STOCH_RSI_MAX", "30"))
SWING_VOLUME_RATIO = float(os.getenv("SWING_VOLUME_RATIO", "1.0"))

ENABLE_GATE = os.getenv("ENABLE_GATE", "true").lower() == "true"

sent_signals = set()

# =========================
# EXCLUDED COINS
# =========================

STABLECOINS = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD",
    "FDUSD", "USDD", "USDE", "PYUSD",
    "FRAX", "LUSD"
}

MEME_COINS = {
    "DOGE", "SHIB", "PEPE", "FLOKI",
    "BONK", "WIF", "BRETT", "MEME",
    "TURBO", "POPCAT", "MOG", "BOME",
    "PONKE", "NEIRO", "WOJAK"
}

GAMBLING_COINS = {
    "FUN", "WIN", "ROLL", "BET"
}

PREDICTION_MARKET_COINS = {
    "POLY", "POLS", "SX", "UMA", "REP"
}

GAMING_COINS = {
    "AXS", "SAND", "MANA", "GALA",
    "ENJ", "PIXEL", "BEAM", "YGG",
    "ILV", "MAGIC"
}

EXCHANGE_COINS = {
    "BNB", "OKB", "KCS", "GT",
    "BGB", "HT", "CRO", "MX", "LEO"
}

EXCLUDED_SYMBOLS = (
    STABLECOINS
    | MEME_COINS
    | GAMBLING_COINS
    | PREDICTION_MARKET_COINS
    | GAMING_COINS
    | EXCHANGE_COINS
)

# =========================
# TELEGRAM
# =========================

def send_telegram(message):

    try:

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            },
            timeout=10
        )

    except Exception as e:
        print("Telegram Error:", e)

# =========================
# CMC
# =========================

def get_cmc_symbols():

    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"

    headers = {
        "X-CMC_PRO_API_KEY": CMC_API_KEY
    }

    params = {
        "start": 1,
        "limit": CMC_TOP_N,
        "convert": "USD"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=20
        )

        data = response.json().get("data", [])

        coins = []

        for coin in data:

            symbol = coin.get("symbol")

            if not symbol:
                continue

            if symbol in EXCLUDED_SYMBOLS:
                continue

            quote = coin.get("quote", {}).get("USD", {})

            market_cap = quote.get("market_cap")
            volume_24h = quote.get("volume_24h")

            if not market_cap:
                continue

            if market_cap > MAX_MARKET_CAP:
                continue

            coins.append({
                "symbol": symbol,
                "market_cap": market_cap,
                "volume_24h": volume_24h or 0,
                "change_24h": quote.get("percent_change_24h") or 0
            })

        return coins

    except Exception as e:
        print("CMC Error:", e)
        return []

# =========================
# GATE API
# =========================

def fetch_gate_klines(symbol, timeframe):

    url = "https://api.gateio.ws/api/v4/spot/candlesticks"

    params = {
        "currency_pair": f"{symbol}_USDT",
        "interval": timeframe,
        "limit": 120
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        data = response.json()

        if not isinstance(data, list):
            return None

        if not data:
            return None

        df = pd.DataFrame(
            data,
            columns=[
                "time",
                "volume_quote",
                "close",
                "high",
                "low",
                "open",
                "volume"
            ]
        )

        df = df.iloc[::-1].reset_index(drop=True)

        return df

    except Exception as e:
        print(f"Gate Error {symbol}:", e)
        return None

# =========================
# INDICATORS
# =========================

def calculate_stoch_rsi(df):

    df = df.copy()

    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    min_rsi = rsi.rolling(14).min()
    max_rsi = rsi.rolling(14).max()

    stoch = (rsi - min_rsi) / (max_rsi - min_rsi) * 100

    k = stoch.rolling(3).mean()
    d = k.rolling(3).mean()

    if pd.isna(k.iloc[-1]):
        return None, None

    return round(float(k.iloc[-1]), 2), round(float(d.iloc[-1]), 2)

def calculate_macd(df):

    df = df.copy()

    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()

    macd = ema12 - ema26

    signal = macd.ewm(span=9, adjust=False).mean()

    hist = macd - signal

    current = hist.iloc[-1]
    previous = hist.iloc[-2]

    macd_ok = current > 0 and current > previous

    return macd_ok, round(float(current), 8)

def calculate_volume_ratio(df):

    df = df.copy()

    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

    current_volume = df["volume"].iloc[-1]

    avg_volume = df["volume"].iloc[-21:-1].mean()

    if avg_volume == 0:
        return 0

    return round(float(current_volume / avg_volume), 2)

# =========================
# HELPERS
# =========================

def format_money(value):

    try:

        value = float(value)

        if value >= 1_000_000_000:
            return f"${value / 1_000_000_000:.2f}B"

        if value >= 1_000_000:
            return f"${value / 1_000_000:.2f}M"

        if value >= 1_000:
            return f"${value / 1_000:.2f}K"

        return f"${value:.2f}"

    except:
        return "N/A"

# =========================
# TARGETS
# =========================

def build_targets(price, mode):

    if mode == "scalping":

        targets = [1.5, 3, 5]
        stop_loss = 2

    else:

        targets = [5, 10, 15, 25, 40]
        stop_loss = 8

    lines = []

    for i, pct in enumerate(targets, start=1):

        target_price = price * (1 + pct / 100)

        lines.append(
            f"TP{i}: ${target_price:.8f} (+{pct}%)"
        )

    sl_price = price * (1 - stop_loss / 100)

    return "\n".join(lines), f"${sl_price:.8f}"

# =========================
# SCAN
# =========================

def scan_coin(
    symbol_data,
    timeframe,
    mode,
    stoch_limit,
    volume_limit
):

    symbol = symbol_data["symbol"]

    df = fetch_gate_klines(symbol, timeframe)

    if df is None:
        return

    try:

        k, d = calculate_stoch_rsi(df)

        if k is None:
            return

        macd_ok, macd_hist = calculate_macd(df)

        if not macd_ok:
            return

        volume_ratio = calculate_volume_ratio(df)

        if volume_ratio < volume_limit:
            return

        signal_key = f"{symbol}-{mode}-{timeframe}"

        if signal_key in sent_signals:
            return

        if k < stoch_limit:

            sent_signals.add(signal_key)

            price = float(df["close"].iloc[-1])

            targets_text, stop_loss_text = build_targets(
                price,
                mode
            )

            title = (
                "⚡ SCALPING ALERT"
                if mode == "scalping"
                else "📈 SWING ALERT"
            )

            message = f"""
{title}

💎 {symbol}/USDT
🏦 Exchange: Gate

⏱ Timeframe:
{timeframe}

💰 Price:
${price:.8f}

📉 Stoch RSI K:
{k}

📉 Stoch RSI D:
{d}

📊 MACD Histogram:
{macd_hist}

🔥 Volume Ratio:
{volume_ratio}x

🏦 Market Cap:
{format_money(symbol_data['market_cap'])}

💧 24H Volume:
{format_money(symbol_data['volume_24h'])}

📈 24H Change:
{round(symbol_data['change_24h'], 2)}%

🎯 Targets:
{targets_text}

🛑 Stop Loss:
{stop_loss_text}
"""

            send_telegram(message)

            print(f"Signal Sent: {symbol}")

    except Exception as e:
        print("Scan Error:", e)

# =========================
# LOOP
# =========================

def scanner_loop():

    send_telegram(
        "🚀 البوت اشتغل بنجاح\n\n"
        "✅ Gate Only\n"
        "✅ Scalping + Swing\n"
        "✅ Stoch RSI أقل من 30\n"
        "✅ MACD إيجابي وصاعد\n"
        "✅ Volume Ratio\n"
        "✅ Market Cap أقل من 100M\n"
        "✅ استبعاد الميم والعملات المحظورة\n\n"
        "📡 بدأ فحص السوق..."
    )

    while True:

        print("Scanning Coins...")

        coins = get_cmc_symbols()

        print(f"Coins Loaded: {len(coins)}")

        for coin in coins:

            if TRADE_MODE in ["scalping", "both"]:

                scan_coin(
                    coin,
                    SCALP_TIMEFRAME,
                    "scalping",
                    SCALP_STOCH_RSI_MAX,
                    SCALP_VOLUME_RATIO
                )

            if TRADE_MODE in ["swing", "both"]:

                scan_coin(
                    coin,
                    SWING_TIMEFRAME,
                    "swing",
                    SWING_STOCH_RSI_MAX,
                    SWING_VOLUME_RATIO
                )

            time.sleep(0.2)

        print("Scan Complete")

        time.sleep(CHECK_INTERVAL)

# =========================
# FLASK
# =========================

@app.route("/")
def home():
    return "Bot Running"

threading.Thread(
    target=scanner_loop,
    daemon=True
).start()

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080))
    )
