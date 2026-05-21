import os
import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CMC_KEY = os.environ["CMC_API_KEY"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CMC_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"

# ─── Fetch Data ──────────────────────────────────────────────────────────────

async def fetch_coins(limit=1000, start=1):
    params = {
        "limit": limit,
        "start": start,
        "convert": "USD",
        "sort": "market_cap",
    }
    headers = {"X-CMC_PRO_API_KEY": CMC_KEY, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(CMC_URL, params=params, headers=headers)
        r.raise_for_status()
        return r.json()["data"]

def enrich(coins):
    result = []
    for c in coins:
        q = c.get("quote", {}).get("USD", {})
        h1  = q.get("percent_change_1h") or 0
        h24 = q.get("percent_change_24h") or 0
        d7  = q.get("percent_change_7d") or 0
        vol = q.get("volume_24h") or 0
        mcap = q.get("market_cap") or 1
        price = q.get("price") or 0

        rsi_raw = 50 + (h24 * 2) + (d7 * 0.5)
        rsi = max(5, min(95, rsi_raw))
        macd = h24 - (d7 / 7)
        vol_ratio = (vol / mcap) * 10 if mcap else 0

        result.append({
            "rank": c.get("cmc_rank", 0),
            "id": c.get("id"),
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
        })
    return result

# ─── Formatters ──────────────────────────────────────────────────────────────

def fmt_price(p):
    if p >= 1000: return f"${p:,.0f}"
    if p >= 1:    return f"${p:.2f}"
    if p >= 0.01: return f"${p:.4f}"
    return f"${p:.8f}"

def fmt_num(n):
    if n >= 1e9: return f"${n/1e9:.2f}B"
    if n >= 1e6: return f"${n/1e6:.2f}M"
    if n >= 1e3: return f"${n/1e3:.2f}K"
    return f"${n:.2f}"

def pct(n):
    arrow = "🟢" if n >= 0 else "🔴"
    sign  = "+" if n >= 0 else ""
    return f"{arrow} {sign}{n:.2f}%"

def rsi_label(r):
    if r < 30: return "ذروة بيع 🟢"
    if r > 70: return "ذروة شراء 🔴"
    return "محايد ⚪"

def vol_label(v):
    if v > 3:   return "🚀 ضخم جداً"
    if v > 2:   return "🔥 مرتفع كبير"
    if v > 1.5: return "📈 مرتفع"
    if v < 0.3: return "📉 منخفض جداً"
    return "⚪ طبيعي"

def coin_card(c, show_rank=True):
    rank = f"#{c['rank']} " if show_rank else ""
    lines = [
        f"*{rank}{c['name']} ({c['symbol']})*",
        f"💰 السعر: `{fmt_price(c['price'])}`",
        f"⏱ 1 ساعة:  {pct(c['h1'])}",
        f"📅 24 ساعة: {pct(c['h24'])}",
        f"📆 7 أيام:  {pct(c['d7'])}",
        f"📊 RSI: `{c['rsi']:.0f}` — {rsi_label(c['rsi'])}",
        f"📈 MACD: `{c['macd']:+.2f}`",
        f"💧 حجم 24h: {fmt_num(c['vol'])} — {vol_label(c['vol_ratio'])}",
        f"🏦 Market Cap: {fmt_num(c['mcap'])}",
    ]
    return "\n".join(lines)

# ─── Commands ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *أهلاً في بوت كريبتو سكانر* 📡\n\n"
        "يراقب *1000 عملة* من CoinMarketCap\n\n"
        "*الأوامر المتاحة:*\n"
        "🔍 /scan — سكانر الفرص (RSI + MACD + حجم)\n"
        "📉 /oversold — عملات في ذروة البيع (RSI < 30)\n"
        "📈 /overbought — عملات في ذروة الشراء (RSI > 70)\n"
        "🔥 /volume — أعلى حجم تداول غير طبيعي\n"
        "🚀 /gainers — أعلى ارتفاع 24 ساعة\n"
        "📉 /losers — أعلى انخفاض 24 ساعة\n"
        "🔎 /find <اسم أو رمز> — ابحث عن عملة معينة\n"
        "📊 /top50 — أفضل 50 عملة حسب Market Cap\n"
        "ℹ️ /help — مساعدة وشرح المؤشرات"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📚 *شرح المؤشرات*\n\n"
        "*RSI (مؤشر القوة النسبية):*\n"
        "• أقل من 30 → ذروة بيع، قد يرتد\n"
        "• أعلى من 70 → ذروة شراء، قد يتراجع\n"
        "• 30-70 → منطقة محايدة\n\n"
        "*MACD:*\n"
        "• موجب → زخم صاعد\n"
        "• سالب → زخم هابط\n\n"
        "*حجم التداول (Vol Ratio):*\n"
        "• x3+ → ضخم جداً، انتبه للحركة\n"
        "• x2+ → مرتفع كبير\n"
        "• x1.5+ → مرتفع\n\n"
        "⚠️ *هذا البوت للتحليل والتعليم فقط، ليس نصيحة مالية.*"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def cmd_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ جاري تحليل 1000 عملة...")
    try:
        raw = await fetch_coins(1000)
        coins = enrich(raw)

        # Coins with RSI oversold + MACD positive + high volume = best setup
        best = [c for c in coins if c["rsi"] < 40 and c["macd"] > 0 and c["vol_ratio"] > 1.2]
        best = sorted(best, key=lambda c: c["vol_ratio"], reverse=True)[:10]

        if not best:
            best = sorted(coins, key=lambda c: c["vol_ratio"], reverse=True)[:10]

        now = datetime.now().strftime("%H:%M:%S")
        text = f"🔍 *سكانر الفرص — {now}*\n_(RSI منخفض + MACD إيجابي + حجم مرتفع)_\n\n"
        text += "\n\n─────────────────\n\n".join(coin_card(c) for c in best[:5])
        text += f"\n\n📊 _تم تحليل {len(coins)} عملة_"

        keyboard = [[InlineKeyboardButton("🔄 تحديث", callback_data="scan")]]
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                            reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")

async def cmd_oversold(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ جاري البحث عن ذروة البيع...")
    try:
        raw = await fetch_coins(1000)
        coins = enrich(raw)
        oversold = sorted([c for c in coins if c["rsi"] < 30], key=lambda c: c["rsi"])[:10]

        if not oversold:
            await msg.edit_text("✅ لا توجد عملات في ذروة البيع حالياً (RSI < 30)")
            return

        now = datetime.now().strftime("%H:%M:%S")
        text = f"📉 *ذروة البيع — {now}*\n_(RSI أقل من 30 — فرصة ارتداد محتملة)_\n\n"
        text += "\n\n─────────────────\n\n".join(coin_card(c) for c in oversold[:5])

        keyboard = [[InlineKeyboardButton("🔄 تحديث", callback_data="oversold")]]
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                            reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")

async def cmd_overbought(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ جاري البحث عن ذروة الشراء...")
    try:
        raw = await fetch_coins(1000)
        coins = enrich(raw)
        overbought = sorted([c for c in coins if c["rsi"] > 70], key=lambda c: -c["rsi"])[:10]

        if not overbought:
            await msg.edit_text("✅ لا توجد عملات في ذروة الشراء حالياً (RSI > 70)")
            return

        now = datetime.now().strftime("%H:%M:%S")
        text = f"📈 *ذروة الشراء — {now}*\n_(RSI أعلى من 70 — احتمال تراجع)_\n\n"
        text += "\n\n─────────────────\n\n".join(coin_card(c) for c in overbought[:5])

        keyboard = [[InlineKeyboardButton("🔄 تحديث", callback_data="overbought")]]
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                            reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")

async def cmd_volume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ جاري البحث عن أعلى الأحجام...")
    try:
        raw = await fetch_coins(1000)
        coins = enrich(raw)
        top_vol = sorted(coins, key=lambda c: c["vol_ratio"], reverse=True)[:10]

        now = datetime.now().strftime("%H:%M:%S")
        text = f"🔥 *أعلى حجم تداول غير طبيعي — {now}*\n\n"
        text += "\n\n─────────────────\n\n".join(coin_card(c) for c in top_vol[:5])

        keyboard = [[InlineKeyboardButton("🔄 تحديث", callback_data="volume")]]
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                            reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")

async def cmd_gainers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ جاري جلب أعلى الارتفاعات...")
    try:
        raw = await fetch_coins(1000)
        coins = enrich(raw)
        gainers = sorted(coins, key=lambda c: c["h24"], reverse=True)[:10]

        now = datetime.now().strftime("%H:%M:%S")
        text = f"🚀 *أعلى ارتفاع 24 ساعة — {now}*\n\n"
        text += "\n\n─────────────────\n\n".join(coin_card(c) for c in gainers[:5])

        keyboard = [[InlineKeyboardButton("🔄 تحديث", callback_data="gainers")]]
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                            reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")

async def cmd_losers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ جاري جلب أعلى الانخفاضات...")
    try:
        raw = await fetch_coins(1000)
        coins = enrich(raw)
        losers = sorted(coins, key=lambda c: c["h24"])[:10]

        now = datetime.now().strftime("%H:%M:%S")
        text = f"📉 *أعلى انخفاض 24 ساعة — {now}*\n\n"
        text += "\n\n─────────────────\n\n".join(coin_card(c) for c in losers[:5])

        keyboard = [[InlineKeyboardButton("🔄 تحديث", callback_data="losers")]]
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                            reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")

async def cmd_find(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("❓ استخدام: /find BTC\nأو: /find bitcoin")
        return
    query = " ".join(ctx.args).lower()
    msg = await update.message.reply_text(f"🔎 جاري البحث عن: {query.upper()}...")
    try:
        raw = await fetch_coins(1000)
        coins = enrich(raw)
        found = [c for c in coins if query in c["symbol"].lower() or query in c["name"].lower()]

        if not found:
            await msg.edit_text(f"❌ لم يتم العثور على '{query}' في أول 1000 عملة")
            return

        text = f"🔎 *نتائج البحث: {query.upper()}*\n\n"
        text += "\n\n─────────────────\n\n".join(coin_card(c) for c in found[:3])
        if len(found) > 3:
            text += f"\n\n_... و {len(found)-3} نتائج أخرى_"

        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")

async def cmd_top50(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ جاري جلب أفضل 50 عملة...")
    try:
        raw = await fetch_coins(50)
        coins = enrich(raw)
        now = datetime.now().strftime("%H:%M:%S")

        lines = [f"📊 *أفضل 50 عملة — {now}*\n"]
        for c in coins:
            arrow = "🟢" if c["h24"] >= 0 else "🔴"
            sign = "+" if c["h24"] >= 0 else ""
            lines.append(
                f"#{c['rank']} *{c['symbol']}* — {fmt_price(c['price'])} {arrow}{sign}{c['h24']:.1f}%"
            )

        text = "\n".join(lines)
        keyboard = [[InlineKeyboardButton("🔄 تحديث", callback_data="top50")]]
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                            reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")

# ─── Callback (Refresh Buttons) ───────────────────────────────────────────────

CALLBACK_MAP = {
    "scan": cmd_scan,
    "oversold": cmd_oversold,
    "overbought": cmd_overbought,
    "volume": cmd_volume,
    "gainers": cmd_gainers,
    "losers": cmd_losers,
    "top50": cmd_top50,
}

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Fake an update with message for reuse
    update.message = query.message
    handler = CALLBACK_MAP.get(query.data)
    if handler:
        await handler(update, ctx)

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("help",       cmd_help))
    app.add_handler(CommandHandler("scan",       cmd_scan))
    app.add_handler(CommandHandler("oversold",   cmd_oversold))
    app.add_handler(CommandHandler("overbought", cmd_overbought))
    app.add_handler(CommandHandler("volume",     cmd_volume))
    app.add_handler(CommandHandler("gainers",    cmd_gainers))
    app.add_handler(CommandHandler("losers",     cmd_losers))
    app.add_handler(CommandHandler("find",       cmd_find))
    app.add_handler(CommandHandler("top50",      cmd_top50))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("🚀 البوت شغّال!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
