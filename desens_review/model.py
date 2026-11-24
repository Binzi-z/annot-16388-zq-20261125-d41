from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable


class Level(IntEnum):
    """Monotone classification watermarks. Higher is more sensitive."""

    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    SECRET = 3


@dataclass(frozen=True)
class ClassifiedSpan:
    """A classified interval in a source/archive text.

    Offsets are Python string offsets and are reported as half-open ``[start,
    end)`` intervals.  ``source_id`` is the identity checked by scoped
    downgrades; identical visible text does not make two spans the same source.
    """

    source_id: str
    start: int
    end: int
    level: int = Level.SECRET
    note: str = ""

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError(f"invalid span [{self.start}, {self.end})")
        if not 0 <= int(self.level) <= int(Level.SECRET):
            raise ValueError("level must be between PUBLIC and SECRET")


@dataclass(frozen=True)
class Downgrade:
    """An explicit downgrade declaration.

    It applies only when ``source_id`` matches and only caps the level at
    ``watermark``.  A revoked declaration is retained for audit but has no
    effect.  Setting ``proxy=True`` records that a proxy issued it; revoking it
    demonstrates "proxy downgrade revocation".
    """

    decl_id: str
    source_id: str
    watermark: int = Level.PUBLIC
    active: bool = True
    proxy: bool = False
    revocation_id: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not 0 <= int(self.watermark) <= int(Level.SECRET):
            raise ValueError("watermark must be between PUBLIC and SECRET")


@dataclass(frozen=True)
class Atom:
    """An alignable atom and its half-open character interval."""

    text: str
    start: int
    end: int
    index: int

    @property
    def width(self) -> int:
        return self.end - self.start


_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def word_atoms(text: str) -> list[Atom]:
    """Align on Unicode word/punctuation tokens while retaining char offsets."""

    return [
        Atom(match.group(0), match.start(), match.end(), index)
        for index, match in enumerate(_TOKEN_RE.finditer(text))
    ]


def character_atoms(text: str) -> list[Atom]:
    """Align on individual Unicode code points."""

    return [Atom(ch, i, i + 1, i) for i, ch in enumerate(text)]


@dataclass
class ReviewCase:
    case_id: str
    source_text: str
    target_text: str
    spans: list[ClassifiedSpan] = field(default_factory=list)
    downgrades: list[Downgrade] = field(default_factory=list)
    editor: str = ""
    parent_version: str = ""
    atom_mode: str = "word"
    alignment_model: str = "transport"

    def __post_init__(self) -> None:
        if self.atom_mode not in {"word", "char"}:
            raise ValueError("atom_mode must be 'word' or 'char'")
        if self.alignment_model not in {"transport", "ordered"}:
            raise ValueError("alignment_model must be 'transport' or 'ordered'")
        for span in self.spans:
            if span.end > len(self.source_text):
                raise ValueError(f"span {span.source_id} exceeds source text")

    def atoms(self, side: str) -> list[Atom]:
        text = self.source_text if side == "source" else self.target_text
        return character_atoms(text) if self.atom_mode == "char" else word_atoms(text)

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "source_text": self.source_text,
            "target_text": self.target_text,
            "spans": [vars(s) for s in self.spans],
            "downgrades": [vars(d) for d in self.downgrades],
            "editor": self.editor,
            "parent_version": self.parent_version,
            "atom_mode": self.atom_mode,
            "alignment_model": self.alignment_model,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewCase":
        return cls(
            case_id=data["case_id"],
            source_text=data["source_text"],
            target_text=data["target_text"],
            spans=[ClassifiedSpan(**s) for s in data.get("spans", [])],
            downgrades=[Downgrade(**d) for d in data.get("downgrades", [])],
            editor=data.get("editor", ""),
            parent_version=data.get("parent_version", ""),
            atom_mode=data.get("atom_mode", "word"),
            alignment_model=data.get("alignment_model", "transport"),
        )


def source_indices_for_span(span: ClassifiedSpan, atoms: Iterable[Atom]) -> set[int]:
    """Return atom indices overlapping a character span."""

    result: set[int] = set()
    for atom in atoms:
        if atom.start < span.end and atom.end > span.start:
            result.add(atom.index)
    return result
