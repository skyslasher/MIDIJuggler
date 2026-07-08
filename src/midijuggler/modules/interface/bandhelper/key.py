"""Parse musical keys for BandHelper / song context."""

from __future__ import annotations

import re
from dataclasses import dataclass

NOTE_TO_PITCH_CLASS: dict[str, int] = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "Fb": 4,
    "F": 5,
    "E#": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
    "Cb": 11,
}

PITCH_CLASS_TO_ROOT: tuple[str, ...] = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)

_KEY_RE = re.compile(
    r"^\s*([A-Ga-g])\s*([#b]?)\s*(m(?:in(?:or)?)?|maj(?:or)?)?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedKey:
    root: int
    minor: bool
    raw: str

    @property
    def root_name(self) -> str:
        return PITCH_CLASS_TO_ROOT[self.root % 12]

    @property
    def mode(self) -> str:
        return "minor" if self.minor else "major"


def parse_key(value: str) -> ParsedKey | None:
    """Parse common chord key spellings such as C, Am, Bb, F# minor."""

    text = str(value).strip()
    if not text:
        return None

    match = _KEY_RE.match(text)
    if match is None:
        return None

    letter = match.group(1).upper()
    accidental = match.group(2) or ""
    mode_token = (match.group(3) or "").lower()
    note_name = f"{letter}{accidental}"
    root = NOTE_TO_PITCH_CLASS.get(note_name)
    if root is None:
        return None

    if mode_token.startswith("m") and not mode_token.startswith("maj"):
        minor = True
    elif mode_token.startswith("maj"):
        minor = False
    else:
        minor = text.lower().endswith("m") and not text.lower().endswith("maj")

    return ParsedKey(root=root, minor=minor, raw=text)


def parse_key_root(value: object) -> int | None:
    """Parse a root pitch class from an int or note-name string."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if 0 <= value <= 11:
            return value
        return None
    if isinstance(value, float) and value.is_integer() and 0 <= int(value) <= 11:
        return int(value)

    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        number = int(text)
        return number if 0 <= number <= 11 else None

    parsed = parse_key(text)
    return parsed.root if parsed is not None else None


def parse_key_mode(value: object) -> bool | None:
    """Return True for minor, False for major."""

    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in {0, 1}:
            return bool(value)
        return None
    if isinstance(value, float) and value.is_integer() and int(value) in {0, 1}:
        return bool(int(value))

    text = str(value).strip().lower()
    if text in {"minor", "min", "m"}:
        return True
    if text in {"major", "maj", "dur"}:
        return False
    return None
