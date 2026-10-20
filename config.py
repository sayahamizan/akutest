"""Tetapan bot. Jangan masukkan API key di sini."""
TIMEZONE = "Asia/Kuala_Lumpur"
START_HOUR = 8
START_MINUTE = 0
SLOT_MINUTES = 5

# 7 major + 21 cross = 28 pasangan forex standard, ditambah XAU/USD.
SYMBOLS = [
    "EUR/USD", "GBP/USD", "AUD/USD", "NZD/USD", "USD/CAD", "USD/CHF", "USD/JPY",
    "EUR/GBP", "EUR/AUD", "EUR/NZD", "EUR/CAD", "EUR/CHF", "EUR/JPY",
    "GBP/AUD", "GBP/NZD", "GBP/CAD", "GBP/CHF", "GBP/JPY",
    "AUD/NZD", "AUD/CAD", "AUD/CHF", "AUD/JPY",
    "NZD/CAD", "NZD/CHF", "NZD/JPY",
    "CAD/CHF", "CAD/JPY", "CHF/JPY",
    "XAU/USD",
]

TIMEFRAME = "4h"
OUTPUTSIZE = 180
TIMEOUT_SECONDS = 30
GROQ_MODEL_DEFAULT = "llama-3.3-70b-versatile"

# Waktu tempatan untuk slot pertama. 29 pair mengambil 145 minit.
# Slot terakhir dijadualkan pada 10:20 jika bermula 08:00.
