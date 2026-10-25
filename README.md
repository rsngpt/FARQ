# FARQ - WhatsApp Intake & Deepfake Verification Engine

FARQ is an automated WhatsApp verification bot designed for end-to-end deepfake and misinformation analysis. The entire workflow is controlled 100% via WhatsApp chat—allowing professional live demos without touching the host laptop.

---

## 🏗️ Architecture

```
Presenter on WhatsApp
       │
       ▼ (Send "/farq" to activate)
[Baileys WebSocket Engine]  <--- Direct encrypted mobile protocol (Zero Chromium)
       │
       ├──> [Session Manager] (Chat-driven: /farq toggles ON/OFF, stays idle otherwise)
       │
       ├──> [Media Storage] (Downloads raw images/videos/audio to ./media_storage/)
       │
       └──> [Deepfake Backend Client] (src/backend.js)
                   │
                   ▼ (HTTP POST Multipart/JSON via Cloudflare Tunnel or Cloud)
          [FastAPI Deepfake Model Engine]
                   │
                   ▼ (JSON Verdict: verdict, reasons, entities, signed report)
          [WhatsApp Verdict Card] (🚫 CONFIRMED_SCAM / ⚠️ LIKELY_SCAM / ❔ NOT_VERIFIED)
```

---

## 📱 Chat-Controlled Demo Lifecycle (Zero-Laptop Operation)

1. **Activate from Chat:**
   * Send `/farq` from any WhatsApp chat.
   * Bot replies: `🟢 FARQ Intake Engine: ONLINE` and checks backend health.
2. **Forward or Send Suspicious Content:**
   * Forward any **Photo, Video, Audio clip, or Text claim**.
   * Bot immediately begins streaming to Mana's backend via `POST /cases`.
   * Concurrently sends **3 Guided Context Questions** (`claims_to_be`, `asks_for`, `money_sent`).
   * **1930 Cyber Fraud Fast-Path**: If money was paid, immediately issues national helpline and bank-freeze warning.
   * Returns a detailed analysis card:
     * 🚫 **CONFIRMED SCAM** (Source found in official archives, altered signals verified)
     * ⚠️ **LIKELY SCAM** (Acoustic/visual mismatch, face and voice not recorded together)
     * ❔ **NOT VERIFIED** (Inconclusive; warns against paying strangers)
     * 📄 **Signed Evidence Report (PDF)** (Court-admissible police docket ready to file)
3. **Close Session & Put Server to Standby:**
   * Send `/farq` again (or `/farq quit`).
   * Bot replies: `🔴 FARQ Intake Engine: STANDBY`.
   * **The bot stays completely silent and idle (0% server load) until `/farq` is called again.**

---

## 📁 Modular Project Structure

```
farq/
├── media_storage/            # Staged media files & jobs.json manifest
│   ├── jobs.json             # Structured manifest of all intake jobs
│   └── *.jpeg / *.mp4        # Downloaded images, videos, audio clips
│
├── baileys_auth/             # WhatsApp Multi-Device encrypted credentials
│
├── src/
│   ├── config.js             # Central paths, backend URL & environment variables
│   ├── backend.js            # Sends media/text to backend & formats WhatsApp cards
│   ├── storage.js            # Saves media to disk & updates jobs.json
│   ├── session.js            # Tracks active user sessions (/farq toggle & quit)
│   ├── dashboard.js          # Local web status & /jobs API (http://localhost:3000)
│   └── whatsapp.js           # Baileys client connection & event handlers
│
├── mock_backend.py           # FastAPI reference server for deepfake model integration
├── index.js                  # Clean main entry point
├── package.json              # Lightweight dependencies (No Puppeteer / Chrome)
└── .gitignore                # Protects session keys and user media
```

---

## 🚀 Running the Bot

### 1. Start the Bot
```bash
npm start
```
* The bot connects via Baileys WebSocket and listens for `/farq`.
* Session credentials are saved in `baileys_auth/`, so re-scanning is not required.

---

## 🤝 Teammate Backend Integration (No Localhost Limitation)

Your teammate can develop their Python model on their own machine and connect directly to your bot over the internet.

### Option A: Free Cloudflare Tunnel (Recommended)
1. Your teammate runs their FastAPI backend on port 5001:
   ```bash
   python3 mock_backend.py
   ```
2. Your teammate exposes it to the internet with 1 command (zero signup):
   ```bash
   cloudflared tunnel --url http://localhost:5001
   ```
3. Cloudflare gives a free HTTPS URL (e.g. `https://funny-dog-123.trycloudflare.com`).
4. Update `DEEPFAKE_BACKEND_URL` in your `.env`:
   ```env
   DEEPFAKE_BACKEND_URL="https://funny-dog-123.trycloudflare.com/api/deepfake/analyze"
   ```

### Option B: Cloud Hosting
Deploy `mock_backend.py` or your teammate's model to **Railway**, **Render**, or **Hugging Face Spaces**, and set the public URL in `.env`.
