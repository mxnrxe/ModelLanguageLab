from dataclasses import dataclass, field

from .models import Token
from .parser import PAIRS
from .semantic import SemanticAnalyzer, SemanticResult, Identifier, INT
from .tables import TL


# Исходные пары таблиц не меняются. Новые операции дополняют только ПОЛИЗ.
EXTRA = {op: len(TL) + i for i, op in enumerate(('JMP', '!F', 'R', 'W', '.', 'STEP'), 1)}


@dataclass(frozen=True)
class PolizItem:
    table: int
    index: int
    text: str
    line: int
    column: int

    @property
    def pair(self):
        return f'({self.table}, {self.index})'


@dataclass
class Compilation(SemanticResult):
    code: list[PolizItem] = field(default_factory=list)
    constants: list = field(default_factory=list)


class Compiler(SemanticAnalyzer):
    """Один синтаксически управляемый проход: синтаксис, типы и ПОЛИЗ."""

    def analyze(self, lexical, **kwargs):
        self.P = []
        checked = super().analyze(lexical, **kwargs)
        if checked.ok:
            self.put_op('.', self.eof)
        return Compilation(**vars(checked), code=self.P if checked.ok else [],
                           constants=[n.value for n in lexical.numbers])

    @property
    def free(self):
        return len(self.P) + 1

    def put_lex(self, table, index, text, token):
        self.P.append(PolizItem(table, index, text, token.line, token.column))

    def put_l(self, token):
        self.put_lex(token.table, token.index, token.text, token)

    def put_l5(self, token):
        self.put_lex(5, token.index, '&' + token.text, token)

    def put_op(self, op, token):
        table, index = (2, EXTRA[op]) if op in EXTRA else PAIRS[op]
        self.put_lex(table, index, '!' if op == 'JMP' else op, token)

    def make(self, label, token):
        self.put_lex(0, label, str(label), token)

    def reserve(self, token):
        position = self.free
        self.make(0, token)
        return position

    def patch(self, position, label):
        old = self.P[position - 1]
        self.P[position - 1] = PolizItem(0, label, str(label), old.line, old.column)

    def dec(self, type_name):
        super().dec(type_name)
        for entry in self.result.identifiers:
            if entry.declared:
                entry.address = entry.index

    def Mn(self):
        token = self.LEX
        super().Mn()
        if token.table in (3, 4) or token.text in ('true', 'false'):
            self.put_l(token)

    def checkop(self, operator):
        super().checkop(operator)
        self.put_op(operator.text, operator)

    def checknot(self, token):
        super().checknot(token)
        self.put_op('!', token)

    def assignment(self, counter=False):
        target = self.LEX
        self.put_l5(target)
        super().assignment(counter)
        self.put_op(':=', target)

    def St(self):
        if not self.EQ('readln'):
            return super().St()
        self.gl()
        while True:
            token = self.LEX
            self.Id()
            self.put_l5(token)
            self.put_op('R', token)
            if not self.EQ(','):
                return
            self.gl()

    def ExL(self):
        while True:
            start = self.LEX
            self.Ex('После writeln требуется выражение')
            self.take_type(start, 'Вывод')
            self.put_op('W', start)
            if not self.EQ(','):
                return
            self.gl()

    def Cond(self):
        token = self.LEX
        self.take('if', 'Cond')
        self.condition('Cond')
        false = self.reserve(token)
        self.put_op('!F', token)
        self.statement("После условия «if» требуется оператор его тела")
        if self.EQ('else'):
            end = self.reserve(token)
            self.put_op('JMP', token)
            self.patch(false, self.free)
            self.gl()
            self.statement("После «else» требуется оператор его ветви")
            self.patch(end, self.free)
        else:
            self.patch(false, self.free)

    def WhileSt(self):
        token = self.LEX
        self.take('while', 'WhileSt')
        beginning = self.free
        self.condition('WhileSt')
        end = self.reserve(token)
        self.put_op('!F', token)
        self.statement("После условия «while» требуется оператор тела цикла")
        self.make(beginning, token)
        self.put_op('JMP', token)
        self.patch(end, self.free)

    def temporary(self, token, suffix):
        index = len(self.result.identifiers) + 1
        name = f'@{suffix}{index}'
        self.result.identifiers.append(Identifier(index, name, INT, index))
        return Token(3, index, name, token.start, token.end, token.line, token.column)

    def ForSt(self):
        token = self.LEX
        self.take('for', 'ForSt')
        counter = self.LEX
        self.assignment(counter=True)
        bound = self.temporary(token, 'bound')
        step = self.temporary(token, 'step')
        self.take('to', 'ForSt')
        self.put_l5(bound)
        self.for_expression('Граница for')
        self.put_op(':=', token)
        self.put_l5(step)
        if self.EQ('step'):
            self.gl()
            self.for_expression('Шаг for')
        else:
            # Служебная целая константа 1: таблица 6 только внутреннего кода.
            self.put_lex(6, 1, '1', token)
        self.put_op(':=', token)
        self.put_l(step)
        self.put_op('STEP', token)
        beginning = self.free
        # (step > 0 and i <= bound) or (step < 0 and i >= bound).
        for comparison, sign in (('<=', '>'), ('>=', '<')):
            self.put_l(step)
            self.put_lex(6, 0, '0', token)
            self.put_op(sign, token)
            self.put_l(counter)
            self.put_l(bound)
            self.put_op(comparison, token)
            self.put_op('and', token)
        self.put_op('or', token)
        end = self.reserve(token)
        self.put_op('!F', token)
        self.statement("В цикле «for» после границы и шага требуется оператор тела")
        self.take('next', 'ForSt')
        self.put_l5(counter)
        self.put_l(counter)
        self.put_l(step)
        self.put_op('+', token)
        self.put_op(':=', token)
        self.make(beginning, token)
        self.put_op('JMP', token)
        self.patch(end, self.free)
