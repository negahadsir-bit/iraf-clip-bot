from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Sentence:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Clip:
    rank: int
    start: float
    end: float
    reason: str
    text: str = ""
    top: bool = False
