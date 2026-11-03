import re

COMPETITION_LIFTS = {"squat": "squat", "bench press": "bench", "bench": "bench", "deadlift": "deadlift"}
GLOSSARY_NAMES = {"squat": "Squat", "bench": "Bench Press", "deadlift": "Deadlift"}
PRESCRIPTION_WORDS = {
    "heavy", "light", "single", "singles", "double", "triple", "backoff", "backoffs", "back", "off", "top", "set",
    "test", "deload", "opener", "second", "third", "attempt", "work", "working", "volume", "intensity", "comp", "competition",
}


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(name or "").lower()).strip()


def competition_lift(name: str) -> str | None:
    words = normalize(name).split()
    for size in (2, 1):
        head = " ".join(words[:size])
        if head in COMPETITION_LIFTS and all(word in PRESCRIPTION_WORDS or word.isdigit() for word in words[size:]):
            return COMPETITION_LIFTS[head]
    return None


def glossary_entry_for(name: str, glossary: list[dict]) -> dict | None:
    by_name = {normalize(entry.get("name")): entry for entry in glossary if entry.get("name")}
    entry = by_name.get(normalize(name))
    if entry:
        return entry
    lift = competition_lift(name)
    return by_name.get(normalize(GLOSSARY_NAMES[lift])) if lift else None
