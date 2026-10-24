"""Find phone numbers, UPI IDs, links and scam-pitch markers in text.

Pure functions over plain strings, used on OCR lines and transcript segments.
Hindi patterns include the different spellings OCR and Whisper produce for the
same English loanword (गारंटीड / गैरेंटीड, ग्रुप / ग्रूप).
"""

import re
from dataclasses import dataclass

from farq.text import normalise

# Indian mobile numbers: optional +91 / 91 / 0, then 10 digits starting 6-9,
# allowing spaces or hyphens between digits ("98765 43210").
PHONE = re.compile(r"(?<![\d+])(?:\+?91[\s-]?|0)?([6-9](?:[\s-]?\d){9})(?!\d)")

# UPI IDs: name@handle, where the handle has no dot (that would be an email).
UPI = re.compile(r"(?<![\w.@-])([a-z0-9][a-z0-9._-]{1,63})@([a-z][a-z0-9]{1,31})\b(?![.@])", re.I)

# Links: with a scheme, or a bare domain on a common top-level domain.
LINK = re.compile(
    r"(?<![@\w.-])((?:https?://)?(?:[a-z0-9-]+\.)+"
    r"(?:com|in|net|org|co|io|info|xyz|top|app|me|link|site|online|club|biz|live|shop)"
    r"(?:/[^\s)]*)?)(?![\w-])",
    re.I,
)
GROUP_LINK = re.compile(r"chat\.whatsapp\.com|t\.me/|telegram\.me/", re.I)

# Pitch markers: (kind, pattern, plain-language reason for the user).
MARKERS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "guaranteed_returns",
        re.compile(
            r"guarantee\w*|assured\s+returns?|risk[\s-]?free|गारंटी\w*|गैरेंटी\w*|गॅरंटी\w*",
            re.I,
        ),
        "It promises guaranteed or risk-free returns, which real investments can't.",
    ),
    (
        "group_invite",
        re.compile(
            r"(whats\s?app|telegram)\s+group|join\s+(our|the)\s+group|"
            r"(वाट्?सएप|व्हाट्सएप|वाटसप|वॉट्सऐप|whatsapp|टेलीग्राम)\s*(ग्रुप|ग्रूप|गरुप|group)|"
            r"(ग्रुप|ग्रूप|गरुप)\s*(में)?\s*(जॉइन|जोइन|ज्वाइन|join)",
            re.I,
        ),
        "It asks you to join a WhatsApp or Telegram group.",
    ),
    (
        "urgency",
        re.compile(
            r"only\s+(today|this\s+week)|limited\s+(time|offer|period)|hurry|"
            r"सिर्फ\s+(आज|इस\s+हफ्?त?े)|इस\s+हफ्?ते\s+तक|इस\s+हफते|जल्दी\s+(करें|कीजिए)",
            re.I,
        ),
        "It pressures you to act quickly.",
    ),
]


@dataclass(frozen=True)
class Found:
    kind: str  # phone, upi_id, link, group_link, or a marker kind
    value: str  # cleaned value (digits only for phones)
    snippet: str  # the text it was found in (normalised)
    start: int = 0  # character position of the match in the snippet


def find_entities(text: str) -> list[Found]:
    text = normalise(text)
    found: list[Found] = []
    for m in PHONE.finditer(text):
        found.append(Found("phone", re.sub(r"\D", "", m.group(1)), text, m.start()))
    for m in UPI.finditer(text):
        found.append(Found("upi_id", f"{m.group(1)}@{m.group(2)}".lower(), text, m.start()))
    for m in LINK.finditer(text):
        url = m.group(1).rstrip(".,")
        kind = "group_link" if GROUP_LINK.search(url) else "link"
        found.append(Found(kind, url.lower(), text, m.start()))
    return found


def find_markers(text: str) -> list[Found]:
    text = normalise(text)
    return [
        Found(kind, m.group(0), text, m.start())
        for kind, pattern, _ in MARKERS
        if (m := pattern.search(text))
    ]


MARKER_REASONS = {kind: reason for kind, _, reason in MARKERS}
