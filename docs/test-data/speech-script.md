# Test recordings for M2 (speech-to-text and entity checks)

Two short recordings by a consenting team member. Everything in the scripts is
fictional: the speaker's "role", the organisation, the phone number, the UPI ID
and the website. `example.com` is a domain reserved for examples, so the link
can never point to a real site. 98765 43210 is a widely used placeholder
number; never dial it.

## How to record

- Use a phone's voice recorder in a quiet room, phone about 30 cm from your mouth.
- Speak at a normal pace, the way someone would in a WhatsApp video. Small
  slips are fine; don't restart for them.
- Any format the phone gives is fine (.m4a, .mp3, .ogg, .wav).
- Name the files `clip1-scam-<initials>.m4a` and `clip2-plain-<initials>.m4a`
  (same extension as recorded) and send them to the team lead.
- They go in the repo's `samples/` folder, which git ignores, so voice
  recordings are never committed or pushed.

## Consent (record as a separate file, `consent-<initials>.m4a`)

> My name is ____. I agree that my voice recordings may be used by Team
> Off-Grid to build and test the FARQ project during this hackathon, and
> deleted afterwards.

## Clip 1: mock scam pitch (about 45 seconds, Hindi and English mixed)

Read it as written. Hindi is in Roman letters so everyone can read it.

> Namaste doston. Main Rakesh Mehra, National Wealth Board ki taraf se baat
> kar raha hoon. Aaj main aapko ek special scheme ke baare mein bataunga.
>
> Is scheme mein aapko guaranteed forty percent return milega, sirf teen
> mahine mein. Yeh offer sirf is hafte tak hai, toh jaldi kijiye.
>
> Register karne ke liye hamare WhatsApp group mein join kijiye. Ya seedha
> call kijiye: nine eight seven six five, four three two one zero.
>
> Payment ke liye UPI ID hai: farq demo at ok fake bank. Ek baar phir: farq
> demo at ok fake bank.
>
> Zyada jaankari ke liye website dekhiye: bonus dot example dot com.
>
> Yaad rakhiye, aisa mauka baar baar nahi aata. Dhanyavaad.

**What M2 should find** (this is the answer key for the test):

| Kind | Expected value | Spoken as |
|---|---|---|
| Phone number | 9876543210 | "nine eight seven six five, four three two one zero" |
| UPI ID | farqdemo@okfakebank | "farq demo at ok fake bank" (twice) |
| Link | bonus.example.com | "bonus dot example dot com" |
| Returns promise | 40% guaranteed in 3 months | "guaranteed forty percent return ... teen mahine" |
| Group invite | WhatsApp group | "WhatsApp group mein join kijiye" |
| Urgency | this week only | "sirf is hafte tak" |

Spoken numbers, UPI IDs and links are hard for speech-to-text. That's
the point: the test shows how much FARQ recovers from speech alone, before
on-screen text (OCR) helps.

## Clip 2: plain announcement, no scam markers (about 20 seconds)

A control clip. FARQ should find no phone numbers, UPI IDs, links or returns
promises here.

> Namaste. Kal college auditorium mein subah das baje ek workshop hai, digital
> safety ke baare mein. Sabhi students aa sakte hain. Registration ki zaroorat
> nahi hai. Apne doston ko bhi bataiye. Dhanyavaad.
