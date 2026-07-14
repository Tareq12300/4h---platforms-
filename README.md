# Crypto Signals Bot 4H — Railway

بوت تيليجرام لتحليل العملات على فريم 4 ساعات، مع الاعتماد على بيانات:

- Gate.io
- KuCoin
- MEXC
- OKX

لا يحتاج إلى CoinMarketCap أو مفتاح CMC.

## الملفات

- `bot.py`: الكود الرئيسي.
- `requirements.txt`: مكتبات Python.
- `railway.json`: إعداد البناء والتشغيل في Railway.
- `Procfile`: أمر تشغيل احتياطي.
- `runtime.txt`: إصدار Python.
- `.env.example`: جميع متغيرات البيئة المطلوبة.

## الرفع إلى Railway

1. فك ضغط الملف.
2. ارفع محتويات المجلد إلى مستودع GitHub، أو استخدم Railway CLI.
3. أنشئ مشروعًا جديدًا في Railway واربط المستودع.
4. أضف المتغيرات الموجودة في `.env.example` داخل تبويب Variables.
5. لا تضف `CMC_API_KEY`؛ البوت لا يستخدم CoinMarketCap.

## المتغيرات المطلوبة

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHANNEL_ID`

بقية المتغيرات لها قيم افتراضية داخل الكود.

## ملاحظات

- يجب إضافة البوت مشرفًا في القناة ومنحه صلاحية إرسال الرسائل.
- قاعدة SQLite وملف السجل داخل حاوية Railway قد يُفقدان عند إعادة النشر ما لم تضف Volume دائمًا.
- للحفاظ على سجل التعلم ونتائج الإشارات، اربط Railway Volume بمسار مثل `/data` ثم غيّر:
  - `DB_FILE=/data/signals_bot.db`
  - `HISTORY_FILE=/data/signals_history.json`
