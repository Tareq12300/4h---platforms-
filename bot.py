import os
import logging
import asyncio
from datetime import datetime

import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CMC_KEY = os.environ["CMC_API_KEY"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))

CMC_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"

sent_alerts = set()


def fetch_coins(limit=1000):
    params = {
        "limit": limit,
        "start": 1,
        "convert": "USD",
        "sort": "market_cap",
    }

    headers = {
        "X-CMC_PRO_API_KEY": CMC_KEY,
        "Accept": "application/json",
    }

    r = requests.get(CMC_URL, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()["data"]


def fmt_price(p):
    if p >= 1:
        return f"${p:.4f}"
    return f"${p:.8f}"


def fmt_num(n):
    if n >= 1e9:
        return f"${n/1e9:.2f}B"
    if n >= 1e6:
        return f"${n/1e6:.2f}M"
    if n >= 1e3:
        return f"${n/1e3:.2f}K"
    return f"${n:.2f}"


def analyze_coin(c):
    q = c.get("quote", {}).get("USD", {})

    price = q.get("price") or 0
    h1 = q.get("percent_change_1h") or 0
    h24 = q.get("percent_change_24h") or 0
    d7 = q.get("percent_change_7d") or 0
    vol = q.get("volume_24h") or 0
    mcap = q.get("market_cap") or 1

    rsi_raw = 50 + (h24 * 2) + (d7 * 0.5)
    rsi = max(5, min(95, rsi_raw))

    macd = h24 - (d7 / 7)
    vol_ratio = (vol / mcap) * 10 if mcap else 0

    confidence = 0

    if rsi < 45:
        confidence += 25
    if macd > 0:
        confidence += 25
    if vol_ratio >= 1.2:
        confidence += 25
    if h1 > 0:
        confidence += 15
    if h24 > -10:
        confidence += 10

    return {
        "rank": c.get("cmc_rank"),
        "name": c.get("name"),
        "symbol": c.get("symbol"),
        "price": price,
        "h1": h1,
        "h24": h24,
        "d7": d7,
        "vol": vol,
        "mcap": mcap,
        "rsi": rsi,
        "macd": macd,
        "vol_ratio": vol_ratio,
        "confidence": confidence,
    }


def build_alert(c):
    return (
        f"🚀 *تنبيه فرصة عملة*\n\n"
        f"🪙 العملة: *{c['name']} ({c['symbol']})*\n"
        f"💰 السعر: `{fmt_price(c['price'])}`\n"
        f"🏦 Market Cap: {fmt_num(c['mcap'])}\n"
        f"💧 Volume 24H: {fmt_num(c['vol'])}\n\n"
        f"📊 RSI: `{c['rsi']:.0f}`\n"
        f"📈 MACD: `{c['macd']:+.2f}`\n"
        f"🔥 Volume Ratio: `{c['vol_ratio']:.2f}x`\n\n"
        f"⏱ 1H: `{c['h1']:+.2f}%`\n"
        f"📅 24H: `{c['h24']:+.2f}%`\n"
        f"📆 7D: `{c['d7']:+.2f}%`\n\n"
        f"🎯 الثقة: *{c['confidence']}%*\n\n"
        f"⚠️ تحليل فقط وليس نصيحة مالية"
    )


async def auto_scanner(app):
    await asyncio.sleep(5)

    while True:
        try:
            if not CHANNEL_ID:
                logger.warning("TELEGRAM_CHANNEL_ID غير موجود")
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            logger.info("🔍 جاري فحص العملات...")

            raw = fetch_coins(1000)
            coins = [analyze_coin(c) for c in raw]

            signals = [
                c for c in coins
                if c["rsi"] < 45
                and c["macd"] > 0
                and c["vol_ratio"] >= 1.2
                and c["confidence"] >= 70
            ]

            signals = sorted(signals, key=lambda x: x["confidence"], reverse=True)[:5]

            for coin in signals:
                key = f"{coin['symbol']}_{datetime.utcnow().strftime('%Y%m%d')}"

                if key in sent_alerts:
                    continue

                await app.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=build_alert(coin),
                    parse_mode=ParseMode.MARKDOWN
                )

                sent_alerts.add(key)
                await asyncio.sleep(2)

            logger.info(f"Signals Found: {len(signals)}")

        except Exception as e:
            logger.error(f"Scanner Error: {e}")

        await asyncio.sleep(CHECK_INTERVAL)


async def cmd_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ جاري تحليل العملات...")

    try:
        raw = fetch_coins(1000)
        coins = [analyze_coin(c) for c in raw]

        signals = [
            c for c in coins
            if c["rsi"] < 45
            and c["macd"] > 0
            and c["vol_ratio"] >= 1.2
        ]

        signals = sorted(signals, key=lambda x: x["confidence"], reverse=True)[:5]

        if not signals:
            await update.message.reply_text("❌ لا توجد فرص حالياً")
            return

        for coin in signals:
            await update.message.reply_text(
                build_alert(coin),
                parse_mode=ParseMode.MARKDOWN
            )

    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")


async def startup(app):
    logger.info("🚀 تشغيل التنبيهات التلقائية")
    asyncio.create_task(auto_scanner(app))

    if CHANNEL_ID:
        await app.bot.send_message(
            chat_id=CHANNEL_ID,
            text="🚀 البوت شغّال ويراقب العملات الآن"
        )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("scan", cmd_scan))

    app.post_init = startup

    logger.info("🚀 البوت شغّال!")

    app.run_polling()


if __name__ == "__main__":
    main()