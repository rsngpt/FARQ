# FARQ (फ़र्क) - WhatsApp Intake & Financial Deepfake Verification Engine

**Team Off-Grid** · Amazon AI Cyber Security Hackathon Finale, Track 3: Financial Deepfakes · IIT Delhi  
*Client / Intake Engine:* **Roshan Gupta** | *Detection & ML Pipeline:* **Mana Sharma**

FARQ is a privacy-first, zero-browser WhatsApp verification bot designed for real-time financial deepfake detection. The entire verification lifecycle is controlled 100% via WhatsApp—featuring native 1-tap interactive polls, an instant 1930 Cyber Fraud Emergency fast-path, and high-impact visual verdict card images with signed court-admissible PDF reports.

---

## 🏗️ System Architecture

```
Victim / Citizen on WhatsApp
       │
       ▼ (Send "/farq" to activate intake session)
[Baileys WebSocket Engine]  <--- Direct binary WebSocket protocol (Zero Chromium, <50MB RAM)
       │
       ├──> [Session Gatekeeper] (Strict opt-in: /farq toggles ON/OFF, ignores group noise)
       │
       ├──> [HMAC-SHA256 Privacy Engine] (Keyed pepper hash: Zero raw phone numbers stored)
       │
       ├──> [Parallel Dispatcher] (Streams video via multipart POST /cases at millisecond zero)
       │           │
       │           ▼
       │     [Mana's GPU Forensics Backend] (FastAPI, PyTorch, Celery, Redis)
       │     • Acoustic & visual lip-sync mismatch (Wav2Lip / SyncNet)
       │     • Frame-by-frame 3D facial landmark tracking
       │     • Official speech archive cross-matching
       │     • OCR entity extraction (scammer UPI IDs, phone numbers, links)
       │
       ├──> [Interactive Polls Engine] (Sends 3 native 1-tap polls: Identity, Ask, Paid?)
       │           │
       │           ├──> (If user paid) ──► 🚨 Immediate 1930 Cyber Fraud Helpline Alert!
       │           └──> (PATCH /cases/{id}/answers) ──► Injects statement into police PDF
       │
       └──> [2.5s State-Machine Poller] (GET /cases/{id})
                   │
                   ▼ (Status: done)
          [WhatsApp Visual Verdict Card]
          • High-res generated PNG: 🚨 A HUGE SCAM ALERT / ⚠️ LIKELY NOT A SCAM / 🛡️ NO SCAM FOUND
          • Ultra-minimal caption with proof breakdown & scammer UPI/phone
          • Signed Evidence report (PDF) ready to file on cybercrime.gov.in
```

---

## 🚀 How to Run the Project on Your Own Device

Follow these step-by-step instructions to get FARQ running locally in under 3 minutes:

### 1. Prerequisites
Make sure you have the following installed on your machine:
* **Node.js** (v18, v20, or v24 LTS): [nodejs.org](https://nodejs.org)
* **Python 3** (v3.9+): [python.org](https://python.org)
* **Pillow (PIL)** for generating high-definition visual verdict cards:
  ```bash
  pip3 install pillow
  ```

---

### 2. Clone the Repository
```bash
git clone https://github.com/rsngpt/FARQ.git
cd FARQ
```

---

### 3. Install Node.js Dependencies
```bash
npm install
```
*(Dependencies are ultra-lightweight: `@whiskeysockets/baileys`, `dotenv`, `pino`, `qrcode`, `mime-types`. No heavy browser automation or Puppeteer required!)*

---

### 4. Configure Environment Variables
Copy the example environment configuration:
```bash
cp .env.example .env
```

Open `.env` in any text editor. 

> [!NOTE]
> **Zero-Config Standalone Demo Mode:** FARQ works out-of-the-box in Standalone Local Demo Mode! If you don't have a live GPU backend running, leave `FARQ_API_KEY` empty or as default. The bot will automatically run local triage, deliver native WhatsApp interactive polls, trigger 1930 emergency fast-paths, and generate high-definition visual verdict cards!

```env
# Server Port
PORT=3000

# Backend Integration (Optional: Leave default for Standalone Local Demo Mode)
FARQ_API_BASE_URL="http://localhost:8000"
FARQ_API_KEY="your_api_key_or_leave_empty_for_standalone_demo"
BACKEND_TIMEOUT_MS=90000

# Security Pepper for HMAC-SHA256 User Anonymization
USER_HASH_PEPPER="farq_pepper_secret_2026"
FARQ_CALLBACK_SECRET="farq_callback_secret_2026"
```

If you are running the GPU forensics backend locally with Docker:
```bash
cd backend
docker compose up -d
```
And set `FARQ_API_BASE_URL="http://localhost:8000"` and `FARQ_API_KEY` to the value configured in `backend/.env`.

---

### 5. Start the Engine
```bash
npm start
```

---

### 6. Link Your WhatsApp Account
1. Once launched, a **QR code** will appear directly in your terminal.
2. *(Optional)* You can also open the local status dashboard at **[http://localhost:3000](http://localhost:3000)** to view the QR code in your web browser.
3. Open **WhatsApp** on your phone:
   * Go to **Settings** > **Linked Devices** > **Link a Device**.
   * Scan the QR code.
4. Once scanned, session credentials are securely cached in `./baileys_auth/`. You will not need to re-scan on subsequent restarts.

---

### 7. How to Test & Use on WhatsApp
Open a WhatsApp chat with the connected number:

1. **Activate the Engine:**
   * Send `/farq`
   * The bot will immediately reply: `🟢 FARQ Intake Engine: ONLINE`.
2. **Forward Any Suspicious Media:**
   * Forward any **Video, Voice Note, Image, or Text claim**.
   * The bot immediately begins uploading the media to the backend in the background.
3. **Answer the 1-Tap Interactive Polls:**
   * **Poll 1:** *Who is it claiming to be?* (Govt / VIP / Bank / Friend)
   * **Poll 2:** *What do they want?* (Invest / Transfer / OTP)
   * **Poll 3:** *Have you already sent money?* (Yes / No)
   * *If you select "Yes", the bot instantly triggers the 1930 Cyber Fraud Helpline alert.*
4. **Receive the Visual Verdict Card:**
   * In 20–30 seconds, the bot delivers:
     * 🖼️ **Visual Card Image**: `🚨 A HUGE SCAM ALERT`, `⚠️ LIKELY NOT A SCAM`, or `🛡️ NO SCAM FOUND`.
     * 📝 **Ultra-minimal caption**: Exact acoustic/visual mismatch proof + scammer UPI/phone.
     * 📄 **Signed Evidence Report (PDF)**: Court-admissible complaint docket.
5. **Close Session:**
   * Send `/farq` again (or `/farq quit`) to return the engine to `🔴 STANDBY`.

---

## 📁 Modular Project Structure

```
FARQ/
├── media_storage/            # Staged media files & generated verdict PNG cards
│   └── jobs.json             # Structured manifest of intake jobs (git-ignored)
│
├── baileys_auth/             # WhatsApp Multi-Device encrypted credentials (git-ignored)
│
├── src/
│   ├── config.js             # Environment variables & directory paths
│   ├── backend.js            # Live API integration (POST /cases, GET /cases, PATCH /answers)
│   ├── generate_card.py      # High-definition 1200x675 visual verdict card renderer (Pillow)
│   ├── image_card.js         # Node.js wrapper for asynchronous card generation
│   ├── interactive.js        # Native WhatsApp Polls & robust vote decryption (LID & JID)
│   ├── questions.js          # 3-question guided triage & dynamic complaint synchronizer
│   ├── session.js            # Strict opt-in session gatekeeper (/farq toggle & quit)
│   ├── crypto.js             # Keyed HMAC-SHA256 user privacy anonymizer
│   ├── dashboard.js          # Local web status & /jobs API (http://localhost:3000)
│   ├── help.js               # Advisory triage consultation helper desk
│   ├── storage.js            # Binary buffer streaming to disk & ledger
│   └── whatsapp.js           # Baileys client connection & event orchestrator
│
├── docs/
│   └── FARQ_SPEC.md          # Full product and functional specification
│
├── index.js                  # Clean main entry point
├── package.json              # Lightweight dependencies (<50MB RAM footprint)
├── .env.example              # Template environment variables
└── README.md                 # Complete project guide and documentation
```

---

## 🔒 Privacy & Responsible AI

* **Privacy by Design**: FARQ hashes citizen phone numbers using keyed `HMAC-SHA256` before transmission. Raw phone numbers are **never stored, logged, or sent** to the cloud GPU servers.
* **No Confusing Percentages**: Probabilistic scores like *"87.4% fake"* cause confusion. FARQ delivers 3 clear, evidence-backed verdicts:
  1. `CONFIRMED_SCAM`: High confidence alteration + original source located in official archives.
  2. `LIKELY_SCAM`: Acoustic/visual anomalies detected (lip movements do not match audio).
  3. `NOT_VERIFIED`: Inconclusive evidence; bot explicitly warns against paying strangers.
* **1930 Cybercrime Fast-Path**: Direct actionable instructions to freeze funds within the critical 2-hour golden window.

---

## 📄 License
ISC License · Built for the **Amazon AI Cyber Security Hackathon Finale 2026** (Track 3) by **Team Off-Grid**.
