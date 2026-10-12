"""Независимый интерпретатор XML для тестов; программа его не использует."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict
from language.models import AnalysisResult, Diagnostic, NumberEntry, Token, TraceStep
from language.numbers import convert_number, NumericLimitError
from language.tables import TW, TL

TRANSITIONS = []
ENTRY_ACTIONS = {}
root = ET.parse(Path(__file__).resolve().parents[1] / "docs" / "Схема.drawio")
for cell in root.iter("mxCell"):
    if cell.get("edge") == "1":
        TRANSITIONS.append((cell.get("id"), cell.get("logicalSource"), cell.get("logicalTarget"),
            json.loads(cell.get("guard")), tuple(json.loads(cell.get("actions")))))
    if cell.get("role") == "state":
        ENTRY_ACTIONS[cell.get("logicalState")] = json.loads(cell.get("entryActions", "[]"))

EOF = "EOF"
BOUNDARY = set(" \t\n+-*/()[],:%!$<>=}{") | {EOF}


def let(ch: str) -> bool:
    return len(ch) == 1 and ("a" <= ch <= "z" or "A" <= ch <= "Z")


def digit(ch: str) -> bool:
    return len(ch) == 1 and "0" <= ch <= "9"


class XmlOracle:
    def analyze(self, source: str, *, trace: bool = True) -> AnalysisResult:
        self.result = AnalysisResult(source.replace("\r\n", "\n").replace("\r", "\n"))
        self.text = self.result.source
        self.CS, self.CH, self.S, self.B, self.z = "START", EOF, "", "", 0
        self.pos = -1
        self.start = 0
        self.line = self.column = 1
        self.start_line = self.start_column = 1
        self._ti = {}
        self._tn = {}
        self._word_table = {s: i for i, (s, _) in enumerate(TW, 1)}
        self._delimiter_table = {"\n" if s == "NL" else s: i for i, (s, _) in enumerate(TL, 1)}
        outgoing = defaultdict(list)
        for edge in TRANSITIONS:
            outgoing[edge[1]].append(edge)
        while self.CS not in ("V", "ER"):
            matches = [e for e in outgoing[self.CS] if self._guard(e[3])]
            if len(matches) != 1:
                raise RuntimeError(f"Автомат недетерминирован: {self.CS}, {self.CH!r}")
            edge_id, previous, target, _, actions = matches[0]
            if previous == "H" and target != "H":
                self.start, self.start_line, self.start_column = self.pos, self.line, self.column
            incoming = ENTRY_ACTIONS.get(target, ())
            if trace:
                if len(self.result.trace) < 100000:
                    self.result.trace.append(TraceStep(edge_id, previous, target, self.CH,
                        self.line, self.column, ", ".join(actions + tuple(incoming))))
                else:
                    self.result.trace_truncated = True
            try:
                for action in actions:
                    self._action(action, edge_id)
                self.CS = target
                for action in incoming:
                    self._action(action, edge_id)
            except NumericLimitError as error:
                self._error(str(error), edge_id)
                self.CS = "ER"
        return self.result

    def gc(self) -> None:
        if self.pos >= 0:
            if self.CH == "\n":
                self.line += 1
                self.column = 1
            elif self.CH != EOF:
                self.column += 1
        self.pos += 1
        self.CH = self.text[self.pos] if self.pos < len(self.text) else EOF

    def nill(self) -> None:
        self.S = ""

    def add(self) -> None:
        self.S += self.CH

    def look(self, table: int) -> None:
        self.z = (self._word_table if table == 1 else self._delimiter_table).get(self.S, 0)

    def put(self, table: int, kind: str = "") -> None:
        if table == 3:
            if self.S not in self._ti:
                self.result.identifiers.append(self.S)
                self._ti[self.S] = len(self.result.identifiers)
            self.z = self._ti[self.S]
        elif table == 4:
            value = convert_number(self.B, kind)
            if value not in self._tn:
                self.result.numbers.append(NumberEntry(value))
                self._tn[value] = len(self.result.numbers)
            self.z = self._tn[value]
            record = self.result.numbers[self.z - 1]
            if self.B not in record.spellings:
                record.spellings.append(self.B)
            if kind not in record.kinds:
                record.kinds.append(kind)
        else:
            raise ValueError(table)

    def out(self, table: int, index: int, kind: str = "") -> None:
        if table == 1:
            end = self.start + len(self.S)
        elif table == 2:
            spelling = TL[index - 1][0]
            end = self.start + (1 if spelling == "NL" else len(spelling))
        elif table == 3:
            end = self.start + len(self.S)
        else:
            end = self.start + len(self.B)
        self.result.tokens.append(Token(table, index, self.text[self.start:end], self.start,
            end, self.start_line, self.start_column, kind))

    def _guard(self, guard: dict) -> bool:
        t, ch = guard["type"], self.CH
        if t == "always": return True
        if t == "chars": return ch in guard["chars"] if ch != EOF else False
        if t == "letters": return let(ch)
        if t == "alnum": return let(ch) or digit(ch)
        if t == "not_alnum": return not (let(ch) or digit(ch))
        if t == "num_start": return digit(ch) or ch == "."
        if t == "not_num_start": return not (digit(ch) or ch == ".")
        if t == "not_chars": return ch not in set(guard["chars"]) and not (guard.get("exclude_eof") and ch == EOF)
        if t == "eof": return ch == EOF
        if t == "z_nonzero": return self.z != 0
        if t == "z_zero": return self.z == 0
        if t == "H_other": return not (let(ch) or digit(ch) or ch in set(" \t.{:<>") or ch == EOF)
        if t == "boundary": return ch in BOUNDARY - set(guard.get("except", ""))
        if t == "numeric_other": return ch not in (set(guard["explicit"]) | (BOUNDARY - set(guard["boundary_except"])))
        raise ValueError(t)

    def _action(self, action: str, edge_id: str) -> None:
        if action == "gc": self.gc()
        elif action == "nill": self.nill()
        elif action == "add": self.add()
        elif action == "B_start": self.B = self.CH
        elif action == "B_reset": self.B = ""
        elif action == "B_append": self.B += self.CH
        elif action == "look_TW": self.look(1)
        elif action == "look_TL": self.look(2)
        elif action == "put_TI": self.put(3)
        elif action.startswith("out:"):
            parts = action.split(":")
            self.out(int(parts[1]), int(parts[2]) if len(parts) == 3 else self.z)
        elif action.startswith("number:"):
            kind = action.split(":")[1]
            self.put(4, kind)
            self.out(4, self.z, kind)
        elif action.startswith("error:"):
            if self.CS == "C":
                message = "Незавершённый комментарий: ожидается }"
            elif self.CS not in ("H", "OP", "DV", "CM", "CB"):
                message = "Некорректная или незавершённая запись числа"
            else:
                message = "Недопустимый символ " + repr(self.CH)
            self._error(message, edge_id)
        else:
            raise ValueError(f"Неизвестное действие {action}")

    def _error(self, message: str, edge_id: str) -> None:
        self.result.diagnostics.append(Diagnostic(message, max(0, self.start),
            min(len(self.text), self.pos + (self.CH != EOF)), self.line, self.column,
            self.CS, edge_id))
