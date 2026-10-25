# FARQ: Project Spec for the WhatsApp Side

**Team Off-Grid** (Mana Sharma, Roshan Gupta) · Amazon AI Cyber Security Hackathon finale, IIT Delhi · Track 3: Deepfake Detection for Financial Communications

> **How to use this doc:** paste it into Claude (or save it in the repo as `docs/FARQ_SPEC.md` and point Claude Code at it). It is the single source of truth for what the WhatsApp bot does, how it talks to the backend, and which rules it must never break. If something here conflicts with older notes, this doc wins.
>
> **Telegram is dropped.** WhatsApp is the only channel, including for reviewers.

---

## 1. The project in one minute

**FARQ** is a WhatsApp service that lets anyone check a suspicious financial video before acting on it. The user forwards the video (or voice note, image or text), and in the same chat gets a verdict, the reasons, and what to do next.

**The problem.** Indian investment scams use deepfake videos of public figures, such as the Finance Minister or the RBI Governor, promoting fake trading platforms. A Pune retiree lost ₹1.07 crore to one. PIB says these fakes are **collages**: the official's real face, their voice taken from other real videos, and AI used only to re-sync the lips. Most deepfake detectors call them real, because every piece is real except the lips.

**Our insight:** *"The face is real. The voice is real. The video is fake."* FARQ asks whether the real pieces belong together.

**Why WhatsApp:** India is WhatsApp's largest market, and the fakes spread there. The check happens where the scam arrives, before the person calls the number or pays. Verification happens from the asker's end.

---

## 2. Hackathon rules we signed (the bot must respect these)

1. **Clean-room:** all code is written during the 2-day event. Commit early and often; judges may audit commit history.
2. **Declared models/APIs only.** On the WhatsApp side this means the **WhatsApp Cloud API** (Meta). Anything else needs organiser approval first.
3. **Data:** synthetic, public or consented only. Fakes only of team members. No real personal data in logs or test data.
4. **Responsible AI** (on our form): no verdict from a single weak signal, no auto-blocking, human review before "Confirmed", and plain-language reasons instead of raw confidence scores.

**Judging rubric (100):** problem fit 20 · architecture and detection logic 20 · value and differentiation 15 · feasibility 15 · safety and responsible AI 15 · adoption 10 · communication 5.

---

## 3. How FARQ decides (backend, owned by Mana)

The bot does not need to implement any of this, but it must present the results correctly.

1. **Source map:** where did every second come from? Video frames are matched against official footage (vpdq hashes); spoken phrases are matched against the person's real speeches (Whisper transcript + BGE-M3 / exact phrase search).
2. **Find the original + diff:** align the fake with its source clip, show that only the mouth changed, and show which words changed.
3. **Audio-visual binding (main detector):** head and eyebrow motion follow the rhythm and pitch of the voice. In a stitched video, the lips are forged but the head and brows still move to the original words. The mouth is ignored and the voice is compared with the body.
4. **Supporting signals:** audio deepfake check, known-fake cache, scam-script matching (the same pitch reused across faces and languages), official lists (RBI Alert List, NSE caution notices, SEBI), and phone numbers / UPI IDs / links read from the video.

An **investigator agent** (Claude on Amazon Bedrock) writes a short, sourced explanation from these findings. A **rules engine, not the LLM**, sets the verdict:

| Verdict | Meaning | Who can set it |
|---|---|---|
| `CONFIRMED_SCAM` | Strong evidence **and** a human reviewer confirmed it | Reviewer only |
| `LIKELY_SCAM` | At least two independent strong signals | Rules engine |
| `NOT_VERIFIED` | Weak or conflicting evidence; we don't guess | Rules engine |

There is **no "genuine" verdict.** FARQ never tells a user a video is real.

---

## 4. System architecture

```
 User's WhatsApp
       │ forwards video / voice note / image / text
       ▼
 Meta WhatsApp Cloud API ──webhook──►  FARQ WhatsApp Bot  (Roshan)
                                        • verify webhook signature, dedupe
                                        • download media, ack + typing indicator
                                        • guided questions (buttons / lists)
                                        • submit case ────────────────┐
                                        • receive result, format reply│
                                        • reviewer flow on WhatsApp   │
                                        ▲                             ▼
                                        │ callback (signed)   FARQ Backend API (Mana)
                                        └──────────────────── • case pipeline (Celery: io/cpu/gpu)
                                                              • detectors, rules engine, agent
                                                              • reports, review queue, audit log
                                                              • Postgres + pgvector, S3-compatible store
```

**Ownership boundary:** Roshan owns everything between Meta and the backend API: webhooks, the conversation, message formatting, media download, and the reviewer UX on WhatsApp. Mana owns the backend API and everything behind it.

**Deployment:** only public-facing endpoints are exposed (the bot's Meta webhook, and the backend API for the bot). Use a Cloudflare Tunnel or Caddy. Everything else binds to localhost. Use `127.0.0.1`, not `localhost`, on Windows (IPv6 hang).

---

## 5. The API contract (bot ↔ backend)

> **This replaces the earlier draft** (`POST /api/deepfake/analyze` returning `is_deepfake` + `confidence`). That draft breaks three rules we signed: a boolean "authentic" result means calling videos genuine, a raw confidence number gets shown to users, and a synchronous call doesn't fit a pipeline that can take up to 60 seconds. Field names below are the target; confirm the final names with Mana against the backend (it already has `POST /cases` and `/healthz` behind an `X-API-Key`).

### 5.1 Auth and basics
- Every request carries `X-API-Key: <shared secret>` (except `GET /healthz`).
- Backend → bot callbacks carry `X-FARQ-Signature: sha256=<HMAC of body with shared secret>`; the bot verifies it.
- JSON uses snake_case. Times are ISO 8601 UTC.

### 5.2 `GET /healthz`
Response: `{"status": "ok"}`

### 5.3 `POST /cases`: submit a check
**Multipart** (image / video / audio):

| Field | Type | Notes |
|---|---|---|
| `file` | binary | The downloaded media |
| `media_type` | `video` \| `audio` \| `image` | |
| `idempotency_key` | string | The WhatsApp message ID (`wamid...`). The backend dedupes on it. |
| `user_ref` | string | **Keyed hash** of the sender's number (HMAC-SHA256 with a secret pepper). Never the raw number. |
| `caption` | string, optional | Text sent with the media |
| `is_forwarded` | bool | From the webhook `context.forwarded` |
| `frequently_forwarded` | bool | From `context.frequently_forwarded` (forwarded more than 5 times) |
| `wa_sha256` | string, optional | The `sha256` from the webhook media object |
| `language` | `en` \| `hi` | Detected or chosen |
| `received_at` | ISO time | |

**JSON** (text claim): `{"media_type": "text", "text": "...", "idempotency_key": "...", "user_ref": "...", "is_forwarded": true, "frequently_forwarded": false, "language": "en", "received_at": "..."}`

**Response `202`:**
```json
{"case_id": "c_7f3a...", "status": "queued", "eta_seconds": 45}
```
If the media is an already-confirmed fake, the backend may return `200` with `"status": "done"` and the full result (section 5.6) immediately.

### 5.4 `PATCH /cases/{case_id}/answers`: send the user's answers
Answers to the guided questions usually arrive after submission (we ask while the backend works).
```json
{"claims_to_be": "official", "asks_for": "invest", "money_sent": false}
```
Allowed values:
- `claims_to_be`: `family_friend` | `bank_upi` | `official` | `famous_expert` | `company_boss` | `not_sure`
- `asks_for`: `send_money` | `invest` | `otp_link_kyc` | `nothing_yet`
- `money_sent`: `true` | `false`

Answers can only make FARQ **more** careful (raise priority, add checks). They can never lower a verdict.

### 5.5 Getting results
- **Primary:** the backend POSTs the result to the bot at `POST {BOT_BASE_URL}/internal/case-result` (signed, see 5.1).
- **Optional progress:** `POST {BOT_BASE_URL}/internal/case-progress` with `{"case_id": "...", "stage": "reading_video" | "checking_sources" | "analysing" | "writing_report"}`. Send at most one progress message to the user per case.
- **Fallback:** the bot polls `GET /cases/{case_id}` every 3 s, for at most 90 s.

### 5.6 Result schema
```json
{
  "case_id": "c_7f3a...",
  "status": "done",
  "verdict": "LIKELY_SCAM",
  "headline": "This video has been altered.",
  "summary": "The face and voice are both the Finance Minister's, but they were not recorded together.",
  "reasons": [
    {"text": "The video matches a real speech from 28 Dec 2025, but the words were changed.", "evidence_id": "ev_12"},
    {"text": "Her head and eyebrow movements don't match this voice (less in sync than 97% of her real videos).", "evidence_id": "ev_15"},
    {"text": "The phone number in the video is on an NSE caution notice.", "evidence_id": "ev_19"}
  ],
  "signals": [
    {"name": "voice_body_match", "level": "high", "explanation": "Less in sync than 97% of her real videos"},
    {"name": "voice_clone", "level": "medium", "explanation": "Some signs of a synthetic voice"}
  ],
  "original": {
    "found": true,
    "title": "PIB: event in West Godavari",
    "url": "https://...",
    "date": "2025-12-28",
    "changed_words": [{"original": "skills hub", "fake": "trading platform"}]
  },
  "source_map": [
    {"start_s": 0, "end_s": 18, "source": "PIB video, 28 Dec 2025", "url": "https://..."},
    {"start_s": 18, "end_s": 41, "source": "No source found", "url": null}
  ],
  "timeline_image_url": "https://.../c_7f3a/timeline.png",
  "next_steps": [
    "Do not call the number or pay.",
    "If you have already paid, call 1930 now."
  ],
  "report": {
    "available": true,
    "complaint_text": "On 24 Oct 2026 I received a video ...",
    "pdf_url": "https://.../c_7f3a/evidence.pdf"
  },
  "campaign": {"case_count": 14, "first_seen": "2026-10-24T05:10:00Z"},
  "review": {"status": "pending"},
  "model_versions": {"voice_body_match": "v1.2", "voice_clone": "wavlm-head-0.3"},
  "timings_ms": {"total": 41200}
}
```

Rules for the bot when rendering:
- `level` is always `low` | `medium` | `high`. **Never show a number** unless it is inside the backend's `explanation` text (e.g. "97% of her real videos"), which is a calibrated comparison, not a probability.
- If `original.found` is false or `source_map` is empty, skip those sections.
- File URLs are short-lived signed links. Download, upload to WhatsApp as media, then send. Don't forward the raw link.

### 5.7 Reviewer endpoints
- `GET /review/queue`: pending `LIKELY_SCAM` cases, ordered **money already sent > frequently forwarded > other**.
- `POST /review/{case_id}` with `{"decision": "confirm" | "reject", "reviewer_ref": "<keyed hash>", "note": "optional"}`.
  - **confirm:** the verdict becomes `CONFIRMED_SCAM`, the fake is cached, and later forwards are answered instantly.
  - **reject:** the verdict becomes `NOT_VERIFIED`.
  - Either way the backend sends an updated result callback, and the bot sends the user a short update.

### 5.8 Errors
```json
{"error": {"code": "unsupported_media", "message": "Couldn't open this file."}}
```
Codes: `unsupported_media`, `too_large`, `duplicate` (return the existing `case_id`), `rate_limited`, `internal`. The bot shows a friendly message for each and never exposes internal details.

---

## 6. Bot responsibilities (Roshan)

### 6.1 Webhook handling
1. **Verification handshake:** answer Meta's `hub.challenge` when `hub.verify_token` matches.
2. **Signature check:** verify `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with the app secret). Reject on mismatch.
3. **Return 200 immediately**, then process asynchronously. Meta retries if you're slow.
4. **Dedupe** on the message ID (`wamid`), since Meta can deliver the same webhook more than once.
5. **Rate limit** per user (e.g. 10 checks per hour) with a polite message. This also stops scammers testing their fakes against us.

### 6.2 Media download
- The webhook gives a media `id` (and possibly a `url`). Get the URL, then download it **with the access token**.
- Media URLs expire after **5 minutes**; media IDs stay downloadable for **7 days**. If a download fails with 404, fetch a fresh URL and retry once.
- Inbound files over 100 MB fail at Meta (error `131052`); tell the user the file is too large.
- Keep media in memory or a temp folder only long enough to upload it to the backend, then delete it. Never log media or raw phone numbers.

### 6.3 Immediate acknowledgement
- Mark the message as read and show the **typing indicator** (the same call, with `typing_indicator: {"type": "text"}`). It lasts up to 25 s or until you reply.
- Then send: *"Got it. Checking this now, usually under a minute. Two quick questions while I check:"*

### 6.4 Guided questions (asked while the backend works)
WhatsApp limits: **reply buttons max 3** per message (title ≤ 20 chars); **list messages up to 10 rows** (row title ≤ 24 chars). Interactive messages work within the 24-hour customer service window.

1. **List:** "Who is it claiming to be?" → Family or friend · Bank or UPI app · Govt / RBI / SEBI / police · Famous person or expert · Company or boss · Not sure
2. **Buttons:** "What do they want?" → Send money · Invest / join app · OTP, link or KYC
3. **Buttons:** "Have you already sent money?" → Yes · Not yet

**If money was sent: stop and send immediately**, before any verdict:
> 🚨 *Call 1930 now* (national cyber fraud helpline) and call your bank's official number to block the payment. The sooner you report, the better the chance of recovery. I'll keep checking the video and send you a report you can file.

Questions are **optional**. If the user ignores them, the check continues. Send the answers with `PATCH /cases/{id}/answers` as they arrive.

### 6.5 Conversation states
`IDLE` → `ACKED` (media received, case submitted) → `ASKING` (questions out) → `WAITING_RESULT` → `RESULT_SENT` → (`REPORT_SENT`) → `IDLE`.
- New media during `WAITING_RESULT` starts a separate case. Keep state per user, keyed by `user_ref`, with a timeout of 15 minutes.
- Plain text that isn't an answer: treat it as a text claim to check, or show the help menu if it's "hi", "help" or "menu".

### 6.6 Delivering the verdict
Send in this order (2–3 messages, never a wall):
1. **The verdict card (text).**
2. **The timeline image** (if `timeline_image_url`), with the caption "Where this video came from".
3. **Buttons:** "Get police report" (only for `LIKELY_SCAM` / `CONFIRMED_SCAM` or when money was sent) · "What should I do?" · "Check another".

**Message copy (English; make a Hindi version with the same structure):**

`LIKELY_SCAM`
```
⚠️ *LIKELY SCAM*
*{headline}*
{summary}

*Why:*
• {reasons[0].text}
• {reasons[1].text}
• {reasons[2].text}

*Original found:* {original.title}, {original.date}
_Words changed:_ "{original}" → "{fake}"

*What to do:*
• {next_steps[0]}
• {next_steps[1]}

_A reviewer is checking this. I'll update you._
```

`CONFIRMED_SCAM`: same layout, header `🚫 *CONFIRMED SCAM*`, footer `_Confirmed by a FARQ reviewer._`

`NOT_VERIFIED`
```
❔ *NOT VERIFIED*
I couldn't find enough evidence either way, so I won't guess.

*Warning signs I noticed:*
• {reasons...}

*Before you act:* call the official number of the person or organisation
(from their website, not from the video). Real officials never ask you to
invest through WhatsApp or pay a stranger's UPI ID.
```

**Never write** "genuine", "real", "safe" or "100%", and never show a raw score.

### 6.7 Police report flow
When the user taps **Get police report**:
1. Send the PDF from `report.pdf_url` as a **document** message (filename `FARQ_evidence_{case_id}.pdf`).
2. Send `report.complaint_text` as a text message they can copy.
3. Send:
> File it yourself at *cybercrime.gov.in* (Report Cyber Crime → Financial Fraud). Paste the text above and attach the PDF. If money was lost, *call 1930* first.

FARQ never files on the user's behalf.

### 6.8 Reviewer flow (on WhatsApp)
- Reviewers are team members' numbers, listed in `REVIEWER_NUMBERS`. Hash them like any other user.
- When a case becomes `LIKELY_SCAM`, send each reviewer:
  - a short summary (headline, top reasons, campaign count);
  - the timeline image;
  - buttons **Confirm** · **Reject** · **Open case**.
- Free-form messages only work within 24 hours of the reviewer's last message. Have reviewers message the bot ("review on") at the start of each session. Otherwise use an approved **utility template** (`farq_review_request`) to open the conversation.
- On a tap, call `POST /review/{case_id}`, then thank the reviewer ("Saved. Case confirmed.").
- When the user's case is updated, send them a one-line update: "Update: a reviewer confirmed this is a scam." or "Update: a reviewer couldn't confirm this, so it stays not verified."

### 6.9 Commands
| User sends | Bot does |
|---|---|
| `hi`, `help`, `menu` | Short intro + how to use + privacy line |
| `delete my data` | Calls the backend to delete the user's cases; confirms |
| `hindi` / `english` | Switches language |

**First-ever message to a user (privacy notice):**
> Hi, I'm FARQ. Forward me any suspicious video, voice note or message about money and I'll check it. I delete your media after checking unless you ask for a report. I never see your contacts or other chats. Send "delete my data" anytime.

---

## 7. WhatsApp setup checklist (Meta)
1. Meta developer app with WhatsApp; a **real phone number** registered (Meta's test number only reaches pre-registered numbers, so judges couldn't use it).
2. Display name **FARQ** approved; profile picture = FARQ logo (our only visual identity in WhatsApp).
3. **Permanent token** from a system user (temporary tokens expire quickly).
4. Webhook subscribed to the `messages` field; callback URL via Cloudflare Tunnel or Caddy.
5. Template `farq_review_request` (utility) submitted early; approval isn't instant.
6. Test interactive lists/buttons, a document send and an image send on real phones.

## 8. Environment variables (bot)
```
WA_PHONE_NUMBER_ID=
WA_ACCESS_TOKEN=          # permanent system-user token
WA_APP_SECRET=            # for X-Hub-Signature-256
WA_VERIFY_TOKEN=          # for the webhook handshake
FARQ_API_BASE_URL=        # backend, e.g. https://api.<tunnel>/
FARQ_API_KEY=             # X-API-Key for the backend
FARQ_CALLBACK_SECRET=     # HMAC for backend -> bot callbacks
BOT_BASE_URL=             # public URL of this bot (for callbacks)
USER_HASH_PEPPER=         # secret pepper for keyed phone hashes
REVIEWER_NUMBERS=         # comma-separated E.164 numbers
DEFAULT_LANGUAGE=en
```
Never commit `.env`. Commit `.env.example` only.

## 9. Safety and privacy rules (the bot side)
1. Never say a video is genuine, real or safe. The best result is `NOT_VERIFIED`.
2. Never show raw scores or percentages, except the backend's calibrated comparison wording.
3. Never block, report or contact anyone automatically. The user decides; reviewers confirm.
4. Store phone numbers only as keyed hashes. No raw numbers in logs, the database or backend calls.
5. Delete downloaded media after upload. Don't log message contents beyond what debugging needs, and strip it before the demo.
6. Answers can only increase caution.
7. Rate-limit per user, and give the same style of reply whether or not something was found, so scammers can't probe the system.
8. Signed calls both ways: verify Meta's signature, the backend's callback signature, and send the API key.

## 10. What to build, in order (WhatsApp side)
1. Webhook (handshake, signature check, 200 fast, dedupe) + echo reply on a real number.
2. Media download + ack + typing indicator.
3. `POST /cases` to the backend (start against a mock that returns a fixed result).
4. Callback endpoint + polling fallback + verdict rendering (all three verdicts).
5. Guided questions + `PATCH /answers` + the money-sent fast path.
6. Timeline image + police report (document + text).
7. Reviewer flow (buttons, template, user update).
8. Commands, privacy notice, Hindi copy, rate limits.
9. End-to-end test with the real backend; measure time from forward to verdict.

**Mock first:** build a tiny mock backend that returns the section 5.6 example after 5 seconds, so the bot can be finished without waiting on the detectors.

## 11. Demo (what the bot must nail)
1. Mana is "enrolled" (her real clips are in the library).
2. On stage, a fresh stitched fake is made from one of her clips. A generic detector says "likely real".
3. The fake is forwarded to FARQ on a real phone. The audience sees the instant ack, the two taps, then the verdict: *"Altered. The face and voice are both hers, but they weren't recorded together."* Then the reasons, the original, the changed words and the timeline image.
4. The knockout chart (original audio back in, the lines snap into step) is shown from the backend demo panel.
5. Tap **Get police report** to show the PDF arriving in WhatsApp.
6. A reviewer confirms on a second phone; the first phone gets "Confirmed". A second forward of the same fake gets an answer in seconds.

**Latency targets:** known fake under 10 s; new video under 60 s.

## 12. Out of scope (do not build)
Telegram; Circle (asking the real person); name checks (CNAP / UPI / SEBI @valid); institution "never says" records; outbreak alerts; our own number-reputation database; Android app; voice-note replies; warning cards; physics / room-acoustics checks; watermarking. Live-call help only if time remains, as a simple text flow.

## 13. Glossary
- **Case:** one check of one forwarded item.
- **Evidence row:** one finding, with its source, strength, reason and model version.
- **Collage / stitched fake:** a real face + a voice from elsewhere + AI-synced lips.
- **Source map:** a timeline of which original each segment came from.
- **Level:** low / medium / high, calibrated against the person's real videos.
- **24-hour window:** free-form and interactive messages are only allowed within 24 h of the user's last message; outside it you need an approved template.
- **1930:** India's national cyber fraud helpline. **cybercrime.gov.in:** the national portal for filing complaints.
