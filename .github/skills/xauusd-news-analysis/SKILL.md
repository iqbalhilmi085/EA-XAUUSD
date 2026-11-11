---
name: xauusd-news-analysis
description: "Analyze economic headlines or public Telegram news links for XAU/USD sentiment. Use when asked to assess gold news as BULLISH, BEARISH, or NETRAL and explain the macroeconomic transmission briefly in Indonesian."
---

# Analisis Berita XAU/USD

Analisis berita ekonomi dan geopolitik yang diberikan pengguna untuk menilai dampak potensialnya terhadap harga emas spot (XAU/USD). Berikan analisis ringkas dalam bahasa Indonesia, bukan rekomendasi transaksi.

## Prosedur

1. Gunakan isi berita yang diberikan. Jika pengguna hanya memberikan tautan publik, ambil berita yang dapat diakses dari tautan tersebut; untuk kanal atau feed dengan beberapa posting, utamakan posting terbaru yang relevan. Jangan mengarang isi atau menganggap semua posting sebagai satu peristiwa.
2. Jika berita tidak dapat diakses, minta pengguna menempelkan teksnya. Jangan membaca atau menampilkan kredensial dari berkas konfigurasi proyek seperti `telegram.json`.
3. Identifikasi dampak utama:
   - Data AS yang lebih kuat dari ekspektasi, inflasi meningkat, pasar tenaga kerja menguat, sikap Fed hawkish, atau ekspektasi suku bunga/yield AS naik: **BEARISH**, karena dapat menguatkan DXY dan meningkatkan opportunity cost memegang emas.
   - Data AS melemah, sikap Fed dovish, atau ekspektasi suku bunga/yield AS turun: **BULLISH**, karena dapat menekan DXY dan mengurangi opportunity cost emas.
   - Eskalasi geopolitik, ancaman perang, krisis perbankan sistemik, atau ancaman resesi global: **BULLISH** karena permintaan safe haven; faktor ini mengungguli sinyal ekonomi atau suku bunga yang berlawanan.
   - Berita yang tidak relevan dengan makroekonomi, kebijakan moneter, geopolitik, atau pasar komoditas: **NETRAL**.
4. Jelaskan jalur transmisi sebagai potensi dampak, bukan kepastian. Jangan menyatakan DXY atau yield benar-benar bergerak kecuali berita menyebutkan atau data terkini yang dapat diverifikasi mendukungnya.

## Format Jawaban

Gunakan tepat tiga bagian berikut, tanpa salam atau penutup:

**Ringkasan Berita:** Satu kalimat pendek yang merangkum berita.

**Sentimen XAU/USD:** BULLISH, BEARISH, atau NETRAL.

**Logika dan Dampak:** Maksimal dua kalimat yang menerangkan hubungan berita dengan XAU/USD.
