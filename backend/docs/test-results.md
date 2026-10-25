# FARQ test-set results

Run 2026-10-25 02:57 UTC against http://127.0.0.1:8000. All videos made from the team's consented clips with FFmpeg; 'squeezed' = 480p, H.264 CRF 30, AAC 64k (an approximation of WhatsApp).

| Group | Expected | Correct | Total |
|---|---|---|---|
| genuine | NOT_VERIFIED | 1 | 1 |
| genuine (squeezed) | NOT_VERIFIED | 1 | 1 |
| copy | NOT_VERIFIED | 4 | 4 |
| copy (squeezed) | NOT_VERIFIED | 4 | 4 |
| stitched | LIKELY_SCAM | 4 | 4 |
| stitched (squeezed) | LIKELY_SCAM | 4 | 4 |

Upload to verdict: median 72.8 s, slowest 156.5 s (18 videos).

| Group | Video | Verdict | Correct | Seconds |
|---|---|---|---|---|
| genuine | lib-05-forwarding | NOT_VERIFIED | yes | 94.5 |
| copy | lib-01-intro | NOT_VERIFIED | yes | 138.9 |
| copy | lib-02-upi | NOT_VERIFIED | yes | 156.5 |
| copy | lib-03-saving | NOT_VERIFIED | yes | 132.9 |
| copy | lib-04-hometown | NOT_VERIFIED | yes | 153.7 |
| stitched | stitched-lib-01-intro-voice-lib-02-upi | LIKELY_SCAM | yes | 64.5 |
| stitched | stitched-lib-01-intro-voice-lib-03-saving | LIKELY_SCAM | yes | 61.5 |
| stitched | stitched-lib-01-intro-voice-lib-04-hometown | LIKELY_SCAM | yes | 62.6 |
| stitched | stitched-lib-02-upi-voice-lib-01-intro | LIKELY_SCAM | yes | 81.3 |
| genuine | lib-05-forwarding (squeezed) | NOT_VERIFIED | yes | 28.1 |
| copy | lib-01-intro (squeezed) | NOT_VERIFIED | yes | 61.2 |
| copy | lib-02-upi (squeezed) | NOT_VERIFIED | yes | 72.8 |
| copy | lib-03-saving (squeezed) | NOT_VERIFIED | yes | 61.0 |
| copy | lib-04-hometown (squeezed) | NOT_VERIFIED | yes | 75.3 |
| stitched | stitched-lib-01-intro-voice-lib-02-upi (squeezed) | LIKELY_SCAM | yes | 54.9 |
| stitched | stitched-lib-01-intro-voice-lib-03-saving (squeezed) | LIKELY_SCAM | yes | 54.3 |
| stitched | stitched-lib-01-intro-voice-lib-04-hometown (squeezed) | LIKELY_SCAM | yes | 48.5 |
| stitched | stitched-lib-02-upi-voice-lib-01-intro (squeezed) | LIKELY_SCAM | yes | 85.1 |
