"""Результаты анализа, общие для интерфейса и следующих этапов."""
from dataclasses import dataclass, field
from fractions import Fraction


@dataclass(frozen=True)
class Token:
    table: int
    index: int
    text: str
    start: int
    end: int
    line: int
    column: int
    kind: str = ""

    @property
    def pair(self) -> str:
        return f"({self.table}, {self.index})"


@dataclass
class NumberEntry:
    value: Fraction
    spellings: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Diagnostic:
    message: str
    start: int
    end: int
    line: int
    column: int
    state: str
    edge: str


@dataclass(frozen=True)
class TraceStep:
    edge: str
    source: str
    target: str
    character: str
    line: int
    column: int
    actions: str


@dataclass
class AnalysisResult:
    source: str
    tokens: list[Token] = field(default_factory=list)
    identifiers: list[str] = field(default_factory=list)
    numbers: list[NumberEntry] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    trace: list[TraceStep] = field(default_factory=list)
    trace_truncated: bool = False

    @property
    def ok(self) -> bool:
        return not self.diagnostics

    @property
    def chain(self) -> str:
        return " ".join(t.pair for t in self.tokens)
