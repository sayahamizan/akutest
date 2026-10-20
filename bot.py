import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

import requests

import config

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "state.json"
TZ = ZoneInfo(config.TIMEZONE)


def now_local():
    return datetime.now(TZ)


def load_state():
    if not STATE_FILE.exists():
        return {"date": "", "completed": [], "last_run": ""}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if data.get("date") != now_local().date().isoformat():
            return {"date": now_local().date().isoformat(), "completed": [], "last_run": ""}
        data.setdefault("completed", [])
        return data
    except (json.JSONDecodeError, OSError):
        return {"date": now_local().date().isoformat(), "completed": [], "last_run": ""}


def save_state(state):
    state["date"] = now_local().date().isoformat()
    state["last_run"] = now_local().isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_env(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment secret/variable belum ditetapkan: {name}")
    return value


def get_candles(symbol):
    api_key = get_env("TWELVE_DATA_API_KEY")
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": config.TIMEFRAME,
        "outputsize": config.OUTPUTSIZE,
        "apikey": api_key,
        "timezone": config.TIMEZONE,
        "format": "JSON",
    }
    response = requests.get(url, params=params, timeout=config.TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") == "error" or "values" not in payload:
        raise RuntimeError(f"Twelve Data untuk {symbol}: {payload.get('message', payload)}")

    # Twelve Data lazimnya mengembalikan nilai terbaru dahulu. Susun menaik.
    values = sorted(payload["values"], key=lambda c: c.get("datetime", ""))
    if len(values) < 40:
        raise RuntimeError(f"Data tidak mencukupi untuk {symbol}: hanya {len(values)} candle")

    required = ("datetime", "open", "high", "low", "close")
    candles = []
    previous_dt = None
    for row in values:
        if any(row.get(k) in (None, "") for k in required):
            continue
        candle = {"datetime": row["datetime"]}
        for key in ("open", "high", "low", "close"):
            candle[key] = float(row[key])
        if candle["high"] < max(candle["open"], candle["close"], candle["low"]):
            continue
        if candle["low"] > min(candle["open"], candle["close"], candle["high"]):
            continue
        if previous_dt == candle["datetime"]:
            continue
        candles.append(candle)
        previous_dt = candle["datetime"]

    if len(candles) < 40:
        raise RuntimeError(f"Candle sah tidak mencukupi untuk {symbol}")

    # Time Series timestamp lazimnya ialah masa pembukaan candle. Jangan guna
    # candle H4 terakhir sebagai candle tertutup jika tempoh 4 jam belum berlalu.
    latest_start = datetime.fromisoformat(candles[-1]["datetime"])
    if latest_start.tzinfo is None:
        latest_start = latest_start.replace(tzinfo=TZ)
    else:
        latest_start = latest_start.astimezone(TZ)
    if now_local() < latest_start + timedelta(hours=4):
        print(f"Menapis candle H4 yang mungkin masih terbentuk: {symbol} {candles[-1]['datetime']}")
        candles = candles[:-1]

    if len(candles) < 40:
        raise RuntimeError(f"Candle H4 yang telah ditutup tidak mencukupi untuk {symbol}")
    return candles


def rsi_wilder(closes, period=14):
    if len(closes) <= period:
        return None
    gains, losses = [], []
    for a, b in zip(closes[:-1], closes[1:]):
        delta = b - a
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0 if avg_gain else 50.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def ema(series, period):
    if not series:
        return []
    alpha = 2 / (period + 1)
    out = [series[0]]
    for value in series[1:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def indicators(candles):
    closes = [c["close"] for c in candles]
    fast = ema(closes, 12)
    slow = ema(closes, 26)
    macd_line = [a - b for a, b in zip(fast, slow)]
    signal_line = ema(macd_line, 9)
    return {
        "rsi_14": rsi_wilder(closes, 14),
        "macd_12_26_9": round(macd_line[-1], 6),
        "macd_signal_9": round(signal_line[-1], 6),
        "macd_histogram": round(macd_line[-1] - signal_line[-1], 6),
    }


def candle_data_for_prompt(candles):
    # Data penuh disertakan, tetapi dipotong ke 120 candle terakhir untuk kawalan token.
    return candles[-120:]


def ask_groq(symbol, candles, ind):
    api_key = get_env("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", config.GROQ_MODEL_DEFAULT)
    url = "https://api.groq.com/openai/v1/chat/completions"
    system = """Anda penganalisis teknikal ICT/Smart Money Concepts. Gunakan HANYA candle OHLC dan indikator yang diberi.
Jangan reka harga, zon, candle atau fakta. Candle diberi dalam urutan masa menaik. Anggap candle terakhir dalam data mungkin belum lengkap jika status tutup tidak dapat disahkan; jangan gunakan ia sebagai pengesahan BOS/MSS.
Kenal pasti swing, BOS/CHoCH/MSS jika ada bukti jelas, liquidity, FVG/OB jika dapat disahkan, dealing range, premium/discount, RSI dan MACD. Data hanya H4; jangan dakwa telah mengesahkan timeframe lebih tinggi.
Keluarkan JSON sahaja dengan keys:
bias (Bullish/Bearish/Neutral), decision (BUY/SELL/VOID), confidence (Low/Medium; jangan guna High),
summary, entry_zone (string atau null), stop_loss (string atau null), take_profit (array of strings),
conditions (array strings), invalidation (string), risks (array strings), full_report (string).
BUY/SELL hanya jika ada setup bersyarat yang jelas dan paras entry, invalidation/SL serta sasaran dapat disokong candle. Jika tidak, decision=VOID dan entry_zone/stop_loss=null. Jangan mengeluarkan nasihat kewangan atau menjanjikan keuntungan. Semua paras harga mesti berasal daripada data yang diberi atau dikira secara jelas daripada data tersebut."""
    user = {
        "instrument": symbol,
        "timeframe": config.TIMEFRAME,
        "data_timezone": config.TIMEZONE,
        "candles_chronological_ohlc": candle_data_for_prompt(candles),
        "calculated_indicators": ind,
        "latest_candle": candles[-1],
        "important": "Nyatakan tarikh/masa candle terakhir. Jangan mendakwa candle terakhir telah tutup jika tidak dapat disahkan. Analisis ini untuk perancangan hari/minggu, bukan execution automatik."
    }
    payload = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": 3500,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)}
        ],
    }
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"Groq API {resp.status_code}: {resp.text[:1000]}")
    content = resp.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Groq tidak memulangkan JSON yang sah: {content[:500]}") from exc


def telegram_send(text):
    token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_env("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Had Telegram lazimnya 4096 aksara; pecahkan laporan panjang.
    chunks = [text[i:i+3800] for i in range(0, len(text), 3800)] or ["(laporan kosong)"]
    for chunk in chunks:
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        }, timeout=30)
        if not resp.ok:
            raise RuntimeError(f"Telegram API {resp.status_code}: {resp.text[:500]}")


def fmt_price(value):
    return "Tidak disahkan" if value is None else str(value)


def make_messages(symbol, candles, ind, analysis):
    latest = candles[-1]
    decision = str(analysis.get("decision", "VOID")).upper()
    if decision not in {"BUY", "SELL", "VOID"}:
        decision = "VOID"
    bias = analysis.get("bias", "Neutral")
    entry = analysis.get("entry_zone")
    sl = analysis.get("stop_loss")
    tps = analysis.get("take_profit") or []
    if not isinstance(tps, list):
        tps = [str(tps)]
    tp_text = ", ".join(str(x) for x in tps) if tps else "Tidak disahkan"
    summary = (
        f"📊 ICT/SMC H4 — {symbol}\n"
        f"🕒 Candle terakhir: {latest['datetime']} ({config.TIMEZONE})\n"
        f"Bias: {bias} | Keputusan: {decision}\n"
        f"Entry: {fmt_price(entry)}\n"
        f"SL: {fmt_price(sl)}\n"
        f"TP: {tp_text}\n"
        f"RSI(14): {ind['rsi_14']} | MACD hist: {ind['macd_histogram']}\n"
        f"Syarat: {'; '.join(map(str, analysis.get('conditions') or ['Tiada pengesahan tambahan']))}\n"
        "Nota: pelan bersyarat, bukan arahan execution. Semak laporan penuh dalam mesej seterusnya."
    )
    full = (
        f"📑 LAPORAN ICT/SMC PENUH — {symbol} (H4)\n"
        f"Tarikh/masa candle terakhir: {latest['datetime']} ({config.TIMEZONE})\n"
        f"OHLC terakhir: O={latest['open']} H={latest['high']} L={latest['low']} C={latest['close']}\n"
        f"RSI(14)={ind['rsi_14']}; MACD(12,26,9)={ind['macd_12_26_9']}; "
        f"Signal={ind['macd_signal_9']}; Histogram={ind['macd_histogram']}\n\n"
        f"Ringkasan: {analysis.get('summary', 'Tiada ringkasan')}\n\n"
        f"Struktur / liquidity / POI / premium-discount / OTE / PO3:\n"
        f"{analysis.get('full_report', 'Tiada laporan terperinci dibekalkan.')}\n\n"
        f"Invalidation: {analysis.get('invalidation', 'Tidak disahkan')}\n"
        f"Risiko/batasan: {'; '.join(map(str, analysis.get('risks') or ['Data H4 sahaja; sahkan sendiri sebelum trade.']))}\n\n"
        "Peringatan: AI boleh tersilap. Tiada jaminan keuntungan. Jangan gunakan sebagai satu-satunya asas keputusan trade."
    )
    return summary, full


def get_next_symbol(state):
    completed = set(state.get("completed", []))
    for symbol in config.SYMBOLS:
        if symbol not in completed:
            return symbol
    return None


def slot_is_due(now):
    start = now.replace(hour=config.START_HOUR, minute=config.START_MINUTE, second=0, microsecond=0)
    if now < start:
        return False
    elapsed = int((now - start).total_seconds() // 60)
    return elapsed >= 0 and elapsed % config.SLOT_MINUTES == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Analisis pair seterusnya sekarang, tanpa menunggu slot.")
    args = parser.parse_args()
    state = load_state()
    symbol = get_next_symbol(state)

    if symbol is None:
        print("Semua 29 instrumen telah dianalisis untuk hari ini.")
        return 0

    now = now_local()
    if not args.once and not slot_is_due(now):
        print(f"Belum slot analisis. Masa tempatan sekarang: {now.isoformat()}")
        return 0

    print(f"Memulakan analisis {symbol} pada {now.isoformat()}")
    try:
        candles = get_candles(symbol)
        ind = indicators(candles)
        analysis = ask_groq(symbol, candles, ind)
        summary, full = make_messages(symbol, candles, ind, analysis)
        telegram_send(summary)
        telegram_send(full)
        state.setdefault("completed", []).append(symbol)
        save_state(state)
        print(f"Selesai {symbol}; {len(state['completed'])}/{len(config.SYMBOLS)} pair hari ini.")
        return 0
    except Exception as exc:
        # Jangan tandakan pair selesai jika mana-mana API gagal; slot seterusnya akan cuba lagi.
        print(f"RALAT untuk {symbol}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
