import re
from dataclasses import dataclass, field

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "for", "to", "is", "are", "was", "were", "be", "been",
    "what", "which", "who", "how", "why", "when", "where", "do", "does", "did", "about", "with", "from",
    "latest", "new", "recent", "current", "any", "me", "my", "tell", "show", "give", "this", "that", "these",
    "those", "it", "its", "at", "by", "as", "into", "over", "past", "last", "tell", "can", "you",
}

_TIME_PATTERNS = [
    (re.compile(r"\b(today|past 24 hours|last 24 hours)\b", re.I), "1d"),
    (re.compile(r"\b(this week|past week|last week|past 7 days|last 7 days)\b", re.I), "7d"),
    (re.compile(r"\b(this month|past month|last month|past 30 days|last 30 days)\b", re.I), "30d"),
    (re.compile(r"\b(this year|past year|last year|past 12 months)\b", re.I), "365d"),
    (re.compile(r"\b(?:past|last)\s+(\d+)\s+(day|week|month)s?\b", re.I), None),
]

_INTENTS = [
    ("trend", re.compile(r"\b(trend|trending|emerging|growing|rising|popular|momentum)\b", re.I)),
    ("comparison", re.compile(r"\b(vs|versus|compare|difference between)\b", re.I)),
    ("explanation", re.compile(r"\b(what is|explain|how does|why)\b", re.I)),
]


class InvalidQuery(ValueError):
    """The query has nothing searchable in it."""


# "quoted phrases" and runs of 2+ Capitalised words ("Claude Code", "Open Source") are kept whole.
_QUOTED = re.compile(r'"([^"]{2,80})"')
_ENTITY = re.compile(r"\b[A-Z][A-Za-z0-9\-\.]*(?:\s+[A-Z][A-Za-z0-9\-\.]*)+\b")


@dataclass
class ProcessedQuery:
    original: str
    cleaned: str
    keywords: list[str] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)
    intent: str = "general"
    time_range: str | None = None


def extract_phrases(text: str) -> list[str]:
    found: list[str] = [m.lower() for m in _QUOTED.findall(text)]
    for m in _ENTITY.findall(_QUOTED.sub(" ", text)):
        words = m.split()
        # A leading question word ("What Are ...") is not part of an entity.
        while words and words[0].lower() in STOPWORDS:
            words.pop(0)
        if len(words) >= 2:
            found.append(" ".join(words).lower())
    return list(dict.fromkeys(found))


def detect_time_range(text: str) -> str | None:
    for pat, val in _TIME_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        if val:
            return val
        n, unit = int(m.group(1)), m.group(2).lower()
        days = n * {"day": 1, "week": 7, "month": 30}[unit]
        return f"{days}d"
    return None


def process_query(query: str, default_time_range: str = "30d") -> ProcessedQuery:
    cleaned = re.sub(r"\s+", " ", query or "").strip()
    if len(cleaned) < 3:
        raise InvalidQuery("Query is empty or too short")
    phrases = extract_phrases(cleaned)
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-\+\.#]*", cleaned.lower())
    keywords: list[str] = []
    for t in tokens:
        t = t.strip(".-")
        if len(t) > 1 and t not in STOPWORDS and t not in keywords:
            keywords.append(t)
    if not keywords and not phrases:
        raise InvalidQuery("Query contains no searchable terms")
    intent = next((name for name, pat in _INTENTS if pat.search(cleaned)), "general")
    return ProcessedQuery(
        original=query,
        cleaned=cleaned,
        keywords=keywords,
        phrases=phrases,
        intent=intent,
        time_range=detect_time_range(cleaned) or default_time_range,
    )
