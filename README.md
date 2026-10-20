# ICT/SMC H4 Daily Rotation Bot — Twelve Data + Groq + Telegram

Bot peribadi yang menganalisis **satu instrumen setiap 5 minit**, menggunakan candle H4 daripada Twelve Data, meminta ringkasan bersyarat daripada Groq, kemudian menghantar hasil ke Telegram.

## Jadual contoh

08:00 EUR/USD, 08:05 EUR/GBP, 08:10 EUR/NZD ... satu instrumen setiap slot. Setiap instrumen dianalisis sekali sehari. Selepas semua 29 instrumen selesai, bot tidak membuat analisis lagi sehingga hari berikutnya.

> GitHub Actions `schedule` bukan jam masa nyata yang dijamin. Ia boleh lewat, terutama ketika beban tinggi. Untuk aliran 29 instrumen, sediakan tetingkap kira-kira 2 jam 25 minit dan pantau tab Actions.

## Senarai 29 instrumen

28 pasangan standard (7 major + 21 cross) dan XAU/USD. Senarai boleh diubah dalam `config.py`.

## Apa yang dihantar ke Telegram

- Mesej ringkas: bias, zon entry bersyarat, SL, TP, status BUY/SELL/VOID.
- Pautan `Laporan ICT/SMC penuh` ke mesej penuh yang dihantar sebagai mesej Telegram berasingan. Telegram Bot API tidak menyediakan pautan umum yang stabil kepada mesej dalam chat peribadi; oleh itu bot menghantar laporan penuh sebagai mesej kedua dan meletakkan arahan “lihat mesej penuh” dalam ringkasan. Dalam group/channel yang mempunyai pautan mesej, boleh ditambah pautan khusus kemudian.

## Pasang

1. Buat repositori GitHub **private atau public**. Public biasanya mengelakkan caj minit GitHub Actions standard, tetapi kod dan sejarah repo boleh dilihat umum. Jangan simpan API key dalam fail.
2. Upload semua fail projek ini ke repo.
3. Di GitHub: **Settings → Secrets and variables → Actions → New repository secret**, tambah:
   - `TWELVE_DATA_API_KEY`
   - `GROQ_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. Semak `config.py`, khususnya `SYMBOLS`, `TIMEZONE` dan `START_HOUR`.
5. Aktifkan Actions dan jalankan workflow `ICT SMC Daily Rotation` secara manual sekali untuk ujian.
6. Workflow memulakan satu slot setiap lima minit, dari masa mula yang ditetapkan. State disimpan dalam fail `state.json` dan di-commit oleh workflow supaya giliran kekal antara runner.

## Penjadualan & zon waktu

GitHub cron menggunakan UTC. Workflow berjalan setiap 5 minit sepanjang hari, tetapi skrip hanya menjalankan analisis dalam tetingkap masa yang ditetapkan (default 08:00–10:25 waktu Malaysia) dan satu pair bagi setiap slot 5 minit. GitHub Actions cron boleh lewat atau terlepas; jika slot terlepas, skrip memilih instrumen seterusnya yang belum dianalisis hari itu apabila workflow berjalan semula. Untuk elak slot lari akibat kelewatan, `state.json` menjejak tarikh dan pair yang telah selesai, bukan nombor slot semata-mata.

## Had dan keselamatan

- Kod ini tidak membuka trade dan bukan nasihat kewangan. Output BUY/SELL/VOID ialah analisis bersyarat, bukan arahan automatik untuk berdagang.
- Candle H4 yang masih terbentuk tidak boleh dianggap candle tutup. Skrip meminta candle yang telah ditutup dan menapis candle paling terkini jika ia kelihatan masih terbuka; namun endpoint/data provider boleh mempunyai kelewatan atau metadata terhad.
- Analisis AI bukan pengesanan ICT matematik yang sempurna. Untuk audit yang ketat, tambah pengiraan struktur/FVG/OB secara deterministik dan semakan manusia.
- API percuma mempunyai had dan model Groq yang tersedia boleh berubah. Tukar `GROQ_MODEL` melalui GitHub Variables jika model default tidak lagi tersedia.
- 29 permintaan candle sehari biasanya lebih rendah daripada had harian 800 yang disebut dalam pelan free, tetapi kredit dan had sebenar bergantung kepada akaun/endpoint.
- Jangan letakkan secrets di dalam `config.py`, commit log, atau mesej Telegram.

## Uji lokal

Python 3.11+:

```bash
pip install -r requirements.txt
export TWELVE_DATA_API_KEY="..."
export GROQ_API_KEY="..."
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
python bot.py --once
```

`--once` menganalisis instrumen belum selesai yang seterusnya tanpa menunggu waktu slot. Ia masih menandakan pair sebagai selesai untuk tarikh semasa.
