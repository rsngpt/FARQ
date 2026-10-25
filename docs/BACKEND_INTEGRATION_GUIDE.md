# FARQ: Complete Backend Integration Guide for Mana's LLM (Claude)

**Team Off-Grid** · Amazon AI Cyber Security Hackathon Finale, IIT Delhi · Track 3: Financial Deepfakes  
**Frontend / WhatsApp Owner:** Roshan Gupta  
**Backend / ML Pipeline Owner:** Mana Sharma  

> **Purpose of this document:**  
> Paste this file directly into Mana's AI coding assistant (Claude / Cursor). It contains everything Roshan has already built on the WhatsApp bot side, the exact API contracts, expected JSON payloads, and step-by-step instructions for wiring Mana's FastAPI/Celery backend to the live WhatsApp bot.

---

## 1. What Roshan Has Built on the WhatsApp Side

The entire user-facing WhatsApp experience is live, tested, and running via Baileys WebSocket:

1. **Intake & Streaming Engine (`src/whatsapp.js`):**
   - Connects directly to WhatsApp mobile WebSocket protocols (zero browser, lightweight Node.js runtime).
   - Ingests forwarded Videos (`.mp4`), Voice Notes (`.ogg`/`.mp3`), Images (`.jpeg`/`.png`), and Text claims.
   - Automatically stages files in `./media_storage/` and tracks jobs in `./media_storage/jobs.json`.

2. **Privacy & Security Layer (`src/crypto.js`):**
   - **Zero raw phone numbers:** All phone numbers/JIDs are hashed with a secret pepper using `HMAC-SHA256` to create an anonymous `user_ref`. The backend never sees or stores real phone numbers.
   - Verifies incoming backend callback HMAC signatures using `X-FARQ-Signature: sha256=<hash>`.

3. **Guided Questions State Machine (`src/questions.js`):**
   - While the backend processes, the bot immediately engages the user with 3 guided questions:
     - **Q1 (`claims_to_be`):** `official` | `famous_expert` | `bank_upi` | `family_friend` | `company_boss` | `not_sure`
     - **Q2 (`asks_for`):** `invest` | `send_money` | `otp_link_kyc` | `nothing_yet`
     - **Q3 (`money_sent`):** `true` | `false`
   - Automatically dispatches answers to the backend via `PATCH /cases/{case_id}/answers`.
   - **Emergency 1930 Fast-Path:** If the user answers `money_sent: true`, the bot **immediately interrupts** with the National Cyber Fraud 1930 helpline and bank freeze instructions before waiting for any verdict.

4. **Fraud Advisory Help Desk (`src/help.js`):**
   - When a user sends `/farq help` (or `help`/`menu`), the bot acts as a pre-triage consultant for Digital Arrest calls, viral trading schemes, and task scams.

5. **Responsible AI Verdict Renderer (`src/backend.js`):**
   - Renders incoming backend results into clean, high-impact WhatsApp markdown.
   - **Strict Rules Respected:**
     - Zero raw confidence percentages.
     - Only 3 valid verdicts: `CONFIRMED_SCAM`, `LIKELY_SCAM`, `NOT_VERIFIED`.
     - Displays source-map diffs (original speech vs altered scam words) and next steps.

---

## 2. Architecture & Ownership Boundary

```
  WhatsApp User (Phone)
        │
        ▼ (Forward Media / Text)
 [Roshan's WhatsApp Bot] ──(1. POST /cases)──────────► [Mana's FastAPI Backend]
        │                                                     │
        ├──(2. Instant Ack + Guided Questions)                ├──► Worker Queue (Celery)
        │                                                     ├──► Biomechanical Prosody Matcher
        ├──(3. PATCH /cases/{id}/answers)────────────────────►├──► Speech Archive Alignment
        │                                                     └──► Rules Engine & Bedrock Agent
        ▼                                                             │
 [Roshan's WhatsApp Bot] ◄──(4. POST /internal/case-result)──────────┘
        │
        ▼ (Renders ⚠️ LIKELY SCAM / 🚫 CONFIRMED SCAM / ❔ NOT VERIFIED)
  WhatsApp User (Phone)
```

---

## 3. The 4 Endpoints Mana Must Implement in FastAPI

All requests from Roshan carry `X-API-Key: <FARQ_API_KEY>` (except `GET /healthz`).

### Endpoint 1: Healthcheck
```http
GET /healthz
```
* **Response (200 OK):**
```json
{"status": "ok"}
```

---

### Endpoint 2: Submit Case (Ingestion)
```http
POST /cases
Headers:
  X-API-Key: <FARQ_API_KEY>
  Content-Type: multipart/form-data (for media) OR application/json (for text)
```

#### A) When User Sends a Video, Audio, or Image (Multipart):
| Field | Type | Description |
|---|---|---|
| `file` | Binary | The raw video/audio/image file stream |
| `media_type` | string | `"video"` \| `"audio"` \| `"image"` |
| `idempotency_key` | string | Unique case/message ID (e.g. `c_m1a2b3c4...`). Backend dedupes on this. |
| `user_ref` | string | Privacy-safe HMAC-SHA256 hash of the sender's phone number |
| `caption` | string | Text/caption accompanying the media (optional) |
| `is_forwarded` | string | `"true"` \| `"false"` |
| `frequently_forwarded`| string | `"true"` \| `"false"` (>5 times viral velocity) |
| `language` | string | `"en"` \| `"hi"` |
| `received_at` | string | ISO 8601 UTC timestamp |

#### B) When User Sends a Text Claim (JSON):
```json
{
  "media_type": "text",
  "text": "The Finance Minister announced a new 40% guaranteed trading scheme on WhatsApp.",
  "idempotency_key": "c_m1a2b3c4...",
  "user_ref": "a3efcbb07759f739...",
  "is_forwarded": true,
  "frequently_forwarded": false,
  "language": "en",
  "received_at": "2026-10-24T16:20:00Z"
}
```

#### Expected Backend Response:
* **If Queueing for Celery Worker (Standard): Return `202 Accepted`**
```json
{
  "case_id": "c_7f3a8b9c1d2e",
  "status": "queued",
  "eta_seconds": 45
}
```
* **If Exact Media Hash is Already a Confirmed Scam in Cache: Return `200 OK`** with the full result schema immediately.

---

### Endpoint 3: Receive User Answers to Guided Questions
```http
PATCH /cases/{case_id}/answers
Headers:
  X-API-Key: <FARQ_API_KEY>
  Content-Type: application/json
```
Roshan's bot sends these as the user answers questions on WhatsApp:
```json
{
  "claims_to_be": "official",
  "asks_for": "invest",
  "money_sent": false
}
```
* **Allowed Values:**
  - `claims_to_be`: `"official"` | `"famous_expert"` | `"bank_upi"` | `"family_friend"` | `"company_boss"` | `"not_sure"`
  - `asks_for`: `"invest"` | `"send_money"` | `"otp_link_kyc"` | `"nothing_yet"`
  - `money_sent`: `true` | `false`
* **How Mana's Pipeline Uses This:**
  - If `claims_to_be: "official"`, immediately narrow the speech search space to the **Official VIP/Parliamentary speech archive** (cutting search time from 40s to 3s).
  - If `money_sent: true`, bump the Celery task to the **High-Priority Queue**.
* **Response (200 OK):**
```json
{"status": "answers_recorded", "case_id": "c_7f3a8b9c1d2e"}
```

---

### Endpoint 4: Polling Fallback
```http
GET /cases/{case_id}
Headers:
  X-API-Key: <FARQ_API_KEY>
```
* **While processing:**
```json
{"case_id": "c_7f3a...", "status": "processing", "stage": "checking_sources"}
```
* **When done:** Returns the **Section 5.6 Result Schema** (see below).

---

## 4. The Exact Result Schema Mana Must Return

Whether delivered via callback (`POST {BOT_BASE_URL}/internal/case-result`) or polling (`GET /cases/{id}`), the result **must** match this JSON schema:

```json
{
  "case_id": "c_7f3a8b9c1d2e",
  "status": "done",
  "verdict": "LIKELY_SCAM",
  "headline": "This video has been altered.",
  "summary": "The face and voice are both the Finance Minister's, but they were not recorded together.",
  "reasons": [
    {
      "text": "The video matches a real speech from 28 Dec 2025, but the words were changed.",
      "evidence_id": "ev_12"
    },
    {
      "text": "Her head and eyebrow movements don't match this voice (less in sync than 97% of her real videos).",
      "evidence_id": "ev_15"
    },
    {
      "text": "The phone number in the video is on an NSE caution notice.",
      "evidence_id": "ev_19"
    }
  ],
  "signals": [
    {
      "name": "voice_body_match",
      "level": "high",
      "explanation": "Less in sync than 97% of her real videos"
    },
    {
      "name": "voice_clone",
      "level": "medium",
      "explanation": "Some signs of a synthetic voice"
    }
  ],
  "original": {
    "found": true,
    "title": "PIB: West Godavari Youth Event",
    "url": "https://pib.gov.in/speeches/...",
    "date": "2025-12-28",
    "changed_words": [
      {
        "original": "skills hub",
        "fake": "trading platform"
      }
    ]
  },
  "source_map": [
    {"start_s": 0, "end_s": 18, "source": "PIB video, 28 Dec 2025", "url": "https://..."},
    {"start_s": 18, "end_s": 41, "source": "No source found", "url": null}
  ],
  "timeline_image_url": "https://storage.farq.ai/evidence/c_7f3a/timeline.png",
  "next_steps": [
    "Do not call the number or pay any registration fees.",
    "If you have already paid, call 1930 immediately to freeze accounts."
  ],
  "report": {
    "available": true,
    "complaint_text": "On 24 Oct 2026 I received a fraudulent investment video promoting a fake trading platform...",
    "pdf_url": "https://storage.farq.ai/evidence/c_7f3a/evidence.pdf"
  },
  "campaign": {
    "case_count": 14,
    "first_seen": "2026-10-24T05:10:00Z"
  },
  "review": {
    "status": "pending"
  }
}
```

### ⚠️ Strict Responsible AI Rules:
1. `verdict` can ONLY be: `"CONFIRMED_SCAM"` | `"LIKELY_SCAM"` | `"NOT_VERIFIED"`.
2. **Never output "GENUINE", "REAL", or "SAFE".** If evidence is weak, output `"NOT_VERIFIED"`.
3. **Never output raw probability numbers or percentages** (e.g. `0.94` or `94%`). All signals must use `level: "low" | "medium" | "high"`.

---

## 5. Reviewer Workflow on WhatsApp (`POST /review/{case_id}`)

When a case is `LIKELY_SCAM`, reviewers (team members) receive a message on WhatsApp with **Confirm** and **Reject** buttons.

When a reviewer taps a button, Roshan's bot calls:
```http
POST /review/{case_id}
Headers:
  X-API-Key: <FARQ_API_KEY>
  Content-Type: application/json

Body:
{
  "decision": "confirm",          // "confirm" or "reject"
  "reviewer_ref": "hmac_hash...",
  "note": "Verified against Sansad TV original speech"
}
```
* **If confirmed:** Verdict updates to `"CONFIRMED_SCAM"`, the fake is cached in Redis/Postgres for instant 0.1s responses to future users, and an update is pushed to the user's WhatsApp.

---

## 6. How to Connect Roshan's Bot and Mana's Backend (No Localhost Limitation)

### Step 1: Mana Starts Her Backend
Mana runs her FastAPI backend on port `5001`:
```bash
uvicorn main:app --host 0.0.0.0 --port 5001 --reload
```

### Step 2: Mana Exposes It via Cloudflare Tunnel (1 Command, Zero Signup)
```bash
cloudflared tunnel --url http://localhost:5001
```
Cloudflare outputs an HTTPS link, e.g.:
`https://swift-falcon-42.trycloudflare.com`

### Step 3: Link It in Roshan's `.env`
In Roshan's `farq/.env`:
```env
FARQ_API_BASE_URL="https://swift-falcon-42.trycloudflare.com"
FARQ_API_KEY="farq_secret_key_2026"
```

The moment this is set:
* The WhatsApp bot automatically verifies `GET /healthz`.
* All incoming WhatsApp videos/audios stream directly into Mana's Celery pipeline!

---

## 7. Checklist for Mana's Claude Assistant:
1. [ ] Implement `GET /healthz` returning `{"status": "ok"}`.
2. [ ] Implement `POST /cases` accepting `multipart/form-data` and returning `202 Accepted` with `case_id`.
3. [ ] Implement `PATCH /cases/{case_id}/answers` to receive guided question answers.
4. [ ] Implement `GET /cases/{case_id}` returning the Section 5.6 Result Schema.
5. [ ] Wire the 4 forensic modules (Anchor Simulation Diff, Biomechanical Prosody Correlation, Acoustic Plosive Inversion, Macroblock Parsing).
6. [ ] Share the `cloudflared` HTTPS URL with Roshan!
