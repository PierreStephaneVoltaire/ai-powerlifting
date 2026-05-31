"""Tarot tool plugin — card draw, meaning lookup, and spread information.

Exports:
    get_schemas()     -> snake_case name -> JSON schema
    execute(name, args) -> async dispatcher for specialist path
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Card catalogue — all 78 Rider-Waite cards
# ---------------------------------------------------------------------------

MAJOR_ARCANA = [
    "the fool", "the magician", "the high priestess", "the empress",
    "the emperor", "the hierophant", "the lovers", "the chariot",
    "strength", "the hermit", "wheel of fortune", "justice",
    "the hanged man", "death", "temperance", "the devil",
    "the tower", "the star", "the moon", "the sun",
    "judgement", "the world",
]

MINOR_SUITS = ["wands", "cups", "swords", "pentacles"]
MINOR_VALUES = [
    "ace", "two", "three", "four", "five", "six", "seven",
    "eight", "nine", "ten", "page", "knight", "queen", "king",
]

MINOR_ARCANA = [
    f"{value} of {suit}" for suit in MINOR_SUITS for value in MINOR_VALUES
]

ALL_CARDS: List[str] = MAJOR_ARCANA + MINOR_ARCANA  # 78 total

# ---------------------------------------------------------------------------
# Slug mapping — card name -> filename slug
# ---------------------------------------------------------------------------

def _card_slug(card_name: str) -> str:
    """Convert a card name like 'the high priestess' to 'the_high_priestess'."""
    return card_name.replace(" ", "_")

# ---------------------------------------------------------------------------
# Image path resolution
# ---------------------------------------------------------------------------

_TAROT_ROOT = Path(__file__).resolve().parent
_ASSETS_DIR = _TAROT_ROOT / "assets" / "cards"


def _image_path(card_name: str) -> tuple:
    """Return (absolute_path | None, image_missing: bool) for a card PNG."""
    slug = _card_slug(card_name)
    path = _ASSETS_DIR / f"{slug}.png"
    if path.exists():
        return str(path), False
    return None, True

# ---------------------------------------------------------------------------
# Meanings data
# ---------------------------------------------------------------------------

_MEANINGS: Optional[Dict[str, Dict[str, str]]] = None


def _load_meanings() -> Dict[str, Dict[str, str]]:
    """Load meanings.json lazily. Keys are normalised card names."""
    global _MEANINGS
    if _MEANINGS is not None:
        return _MEANINGS
    meanings_path = _TAROT_ROOT / "data" / "meanings.json"
    if not meanings_path.exists():
        return {}
    with open(meanings_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    # Normalise keys: lowercase and strip, also build space-key index
    normalised = {}
    for k, v in raw.items():
        key = k.lower().strip()
        normalised[key] = v
        # Also index by spaces version (e.g. "the high priestess" -> "the_high_priestess" already a key)
        # and by underscore version (e.g. "the_high_priestess" -> "the high priestess")
        alt = key.replace("_", " ")
        if alt not in normalised:
            normalised[alt] = v
    _MEANINGS = normalised
    return _MEANINGS

# ---------------------------------------------------------------------------
# Spread definitions
# ---------------------------------------------------------------------------

SPREADS: Dict[int, Dict[str, Any]] = {
    1: {
        "name": "Single Card",
        "positions": ["The Draw"],
    },
    3: {
        "name": "Three-Card Spread",
        "positions": ["Past / Root", "Present / Situation", "Future / Outcome"],
    },
    6: {
        "name": "Six-Card Spread",
        "positions": [
            "The Present", "The Challenge", "The Past",
            "The Future", "The Hidden", "The Advice",
        ],
    },
    8: {
        "name": "Eight-Card Spread",
        "positions": [
            "The Situation", "The Challenge", "The Root",
            "The Recent Past", "The Best Outcome", "The Near Future",
            "The Self", "The Final Outcome",
        ],
    },
}

SUPPORTED_N = sorted(SPREADS.keys())

# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _normalise_card_name(raw: str) -> tuple:
    """Normalise a card name and detect orientation.

    Returns (normalised_name, orientation).
    """
    text = raw.strip().lower()
    orientation = "upright"

    if text.endswith(" reversed"):
        orientation = "reversed"
        text = text[: -len(" reversed")].strip()
    elif text.startswith("reversed "):
        orientation = "reversed"
        text = text[len("reversed "):].strip()

    return text, orientation

# ---------------------------------------------------------------------------
# Tool: tarot_draw_cards
# ---------------------------------------------------------------------------

def _draw_cards(
    n: int,
    allow_reversed: bool = True,
    spread_type: Optional[str] = None,
) -> Dict[str, Any]:
    if n not in SUPPORTED_N:
        return {"error": f"Unsupported spread size: {n}. Supported: {SUPPORTED_N}"}

    drawn = random.sample(ALL_CARDS, n)
    positions = SPREADS[n]["positions"]

    cards = []
    for i, card_name in enumerate(drawn):
        orientation = "upright"
        if allow_reversed and random.random() < 0.5:
            orientation = "reversed"

        img_path, img_missing = _image_path(card_name)

        entry: Dict[str, Any] = {
            "card_name": card_name.title(),
            "orientation": orientation,
            "position_label": positions[i] if i < len(positions) else f"Position {i + 1}",
            "image_path": img_path,
        }
        if img_missing:
            entry["image_missing"] = True

        cards.append(entry)

    return {
        "spread_name": SPREADS[n]["name"],
        "n": n,
        "allow_reversed": allow_reversed,
        "cards": cards,
    }

# ---------------------------------------------------------------------------
# Tool: tarot_card_meaning
# ---------------------------------------------------------------------------

def _card_meaning(card_name: str, orientation: Optional[str] = None) -> Dict[str, Any]:
    normalised, detected_orientation = _normalise_card_name(card_name)
    final_orientation = orientation or detected_orientation

    meanings = _load_meanings()
    entry = meanings.get(normalised)

    # Fallback: try alternate key formats
    if entry is None:
        for alt in [
            normalised.replace(" ", "_"),          # spaces -> underscores
            normalised.replace("_", " "),          # underscores -> spaces
        ]:
            entry = meanings.get(alt)
            if entry is not None:
                break

    # Fallback: try without/with leading "the "
    if entry is None:
        if normalised.startswith("the "):
            entry = meanings.get(normalised[4:])
        if entry is None and not normalised.startswith("the "):
            entry = meanings.get(f"the {normalised}")

    if entry is None:
        return {"error": f"Unknown card: {card_name}"}

    return {
        "card_name": normalised.title(),
        "orientation": final_orientation,
        "upright": entry.get("upright", ""),
        "reversed": entry.get("reversed", ""),
    }

# ---------------------------------------------------------------------------
# Tool: tarot_spread_info
# ---------------------------------------------------------------------------

def _spread_info(n: int) -> Dict[str, Any]:
    if n not in SPREADS:
        return {"error": f"Unsupported spread size: {n}. Supported: {SUPPORTED_N}"}
    spread = SPREADS[n]
    return {
        "name": spread["name"],
        "n": n,
        "positions": spread["positions"],
    }

# ---------------------------------------------------------------------------
# Plugin contract: get_schemas()
# ---------------------------------------------------------------------------

def get_schemas() -> Dict[str, Dict[str, Any]]:
    return {
        "tarot_draw_cards": {
            "name": "tarot_draw_cards",
            "description": (
                "Randomly draws N cards from a full 78-card Rider-Waite tarot deck, "
                "with optional reversals. Returns each card's name, orientation, "
                "position label, and image path. Emit a FILES: line for each image_path "
                "that is not null so Discord delivers them as attachments."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {
                        "type": "integer",
                        "description": "Number of cards to draw. Supported values: 1, 3, 6, 8.",
                    },
                    "allow_reversed": {
                        "type": "boolean",
                        "description": "Whether reversed cards are possible. Defaults to true.",
                        "default": True,
                    },
                    "spread_type": {
                        "type": "string",
                        "description": (
                            "The spread label to use for position naming. If omitted, "
                            "default position labels are used for the given n."
                        ),
                    },
                },
                "required": ["n"],
            },
        },
        "tarot_card_meaning": {
            "name": "tarot_card_meaning",
            "description": (
                "Returns the traditional Rider-Waite meaning of a named card in upright "
                "or reversed orientation. Use when the operator asks what a card means, "
                "asks about tarot rules, or wants educational context about a specific card."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "card_name": {
                        "type": "string",
                        "description": (
                            "The card name as spoken naturally. E.g. 'three of swords', "
                            "'the high priestess', 'ace of wands', 'six of cups reversed'. "
                            "The tool normalises casing and orientation."
                        ),
                    },
                    "orientation": {
                        "type": "string",
                        "description": "upright or reversed. Defaults to upright if not specified.",
                    },
                },
                "required": ["card_name"],
            },
        },
        "tarot_spread_info": {
            "name": "tarot_spread_info",
            "description": (
                "Returns the name, position labels, and typical use case for a spread "
                "of a given size. Use when recommending a spread before drawing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {
                        "type": "integer",
                        "description": "Spread size. Supported: 1, 3, 6, 8.",
                    },
                },
                "required": ["n"],
            },
        },
    }


# ---------------------------------------------------------------------------
# Plugin contract: execute()
# ---------------------------------------------------------------------------

async def execute(name: str, args: Dict[str, Any]) -> str:
    """Route tarot tool calls."""
    if name == "tarot_draw_cards":
        result = _draw_cards(
            n=int(args["n"]),
            allow_reversed=args.get("allow_reversed", True),
            spread_type=args.get("spread_type"),
        )
    elif name == "tarot_card_meaning":
        result = _card_meaning(
            card_name=args["card_name"],
            orientation=args.get("orientation"),
        )
    elif name == "tarot_spread_info":
        result = _spread_info(n=int(args["n"]))
    else:
        result = {"error": f"Unknown tarot tool: {name}"}

    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)
