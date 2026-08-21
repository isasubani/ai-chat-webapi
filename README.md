# 🤖 AI Chat Webapp — AI Chat Web API Bridge

> Ubah sesi AI chat browser kamu (Gemini, Claude, Qwen, DeepSeek, dll.) menjadi API endpoint yang kompatibel dengan OpenAI — tanpa bayar API key!

---

## 🎯 Tujuan Project

Banyak layanan AI terbaik seperti **Google Gemini**, **Anthropic Claude**, **Qwen**, dan **DeepSeek** tersedia **gratis** melalui antarmuka web browser mereka. Namun untuk digunakan oleh AI coding client seperti **OpenCode**, **Continue**, **Cursor**, atau aplikasi lain, biasanya diperlukan API key berbayar.

**AI Chat Webapp hadir sebagai solusi:**

Project ini bertindak sebagai **jembatan (bridge/proxy)** yang:
1. Mengambil sesi login kamu dari browser (session cookie)
2. Meneruskan request dari AI client ke layanan AI chat
3. Mengembalikan response dalam format **OpenAI-compatible API**

Dengan kata lain, kamu bisa menikmati model AI premium **secara gratis** hanya dengan menggunakan akun web yang sudah kamu miliki.

```
AI Client (OpenCode, Continue, dll.)
        ↓  request OpenAI format
   AI Chat Webapp (localhost:3001)
        ↓  session cookie
  Gemini / Claude / Qwen / DeepSeek Web
        ↓  response
   AI Chat Webapp → format ulang ke OpenAI
        ↓
AI Client menerima response ✅
```

---

## ✨ Fitur

- 🔌 **OpenAI-Compatible API** — endpoint `/v1/chat/completions` & `/v1/models`
- 🌐 **Dashboard Web** — konfigurasi langsung dari browser, tidak perlu edit file
- 📋 **Application Logs** — monitor aktivitas request secara real-time
- 🔑 **Multi-Session** — dukung berbagai AI dengan session cookie masing-masing
- 🔐 **API Key Auth** — proteksi endpoint dengan Bearer token custom
- ⚡ **Streaming Support** — respons streaming (SSE) didukung penuh
- 🛡️ **Dashboard Auth** — halaman dashboard dilindungi password (disimpan di SQLite)

---

## 🚀 Cara Penggunaan

### 1. Install Dependencies

```bash
# Buat virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

### 2. Jalankan Server

```bash
python api-gemini-ai-chat.py
```

Server akan berjalan di: `http://localhost:3001`

### 3. Login ke Dashboard

Buka browser dan akses `http://localhost:3001` — kamu akan diarahkan ke halaman login.

> **Kredensial default:**
> - Password: `admin123`

> [!IMPORTANT]
> Segera ganti password default setelah pertama kali login! Buka Settings → scroll ke bawah → bagian **Ganti Password Dashboard**.

### 4. Konfigurasi via Dashboard

Buka browser dan akses `http://localhost:3001`, lalu isi:

| Field | Deskripsi |
|-------|-----------|
| **Base URL** | Endpoint API ini (default: `http://localhost:3001/v1`) |
| **Available Models** | Nama model yang ingin didaftarkan (pisah koma) |
| **Provider API Key** | Kunci Bearer Token untuk autentikasi client |
| **Google SESSION_COOKIE** | Cookie sesi dari browser (lihat cara mendapatkan di bawah) |

### 5. Cara Mendapatkan Session Cookie (Gemini)

1. Buka dan login ke [gemini.google.com](https://gemini.google.com)
2. Tekan **F12** → buka tab **Application** → **Cookies**
3. Cari cookie bernama `__Secure-1PSID` atau `__Secure-1PSIDTS`
4. Copy value-nya dan paste ke dashboard

### 6. Hubungkan ke AI Client

Konfigurasi AI client kamu (contoh: OpenCode) dengan:

```
Base URL : http://localhost:3001/v1
API Key  : (sesuai yang kamu set di dashboard)
Model    : gemini-web
```

---

## 🛠️ Tech Stack

| Teknologi | Kegunaan |
|-----------|----------|
| **FastAPI** | Web framework & API server |
| **Uvicorn** | ASGI server |
| **gemini-webapi** | Library untuk mengakses Gemini via session cookie |
| **Jinja2** | Template engine untuk dashboard UI |
| **SQLite** | Menyimpan konfigurasi (session cookie, API key, dll.) |

---

## 📂 Struktur Project

```
gemini-ai-chat/
├── api-gemini-ai-chat.py   # Entry point — FastAPI app & semua routes
├── requirements.txt        # Python dependencies
├── templates/
│   ├── login.html          # Halaman login dashboard
│   ├── settings.html       # Dashboard konfigurasi
│   └── logs.html           # Halaman application logs
└── README.md
```

---

## ⚠️ Disclaimer

- Project ini dibuat untuk **keperluan pribadi / self-hosted**.
- Penggunaan session cookie untuk scraping mungkin melanggar Terms of Service layanan terkait. Gunakan dengan bijak dan tanggung jawab.
- Jangan pernah share atau commit session cookie kamu ke repositori publik.

---

## 📄 License

MIT License — bebas digunakan dan dimodifikasi.
