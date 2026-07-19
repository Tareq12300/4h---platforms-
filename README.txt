Crypto Hybrid Signals Bot

Files:
- bot.py: complete bot code
- .env.example: all Railway environment variables
- requirements.txt: Python dependencies
- Procfile: Railway start command

Important:
- Ordinary RSI has been removed completely.
- STOCH_RSI_PERIOD is only the internal RSI period required to calculate Stochastic RSI.
- CoinGecko Pro is selected with COINGECKO_API_MODE=pro.
- Exchange API keys are not required because the bot reads public market data.
