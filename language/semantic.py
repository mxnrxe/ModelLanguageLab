from dataclasses import dataclass, field

from .parser import Parser, SyntaxDiagnostic


INT, REAL, BOOL = "integer", "real", "boolean"
TYPES = {"%": INT, "!": REAL, "$": BOOL}
NUMERIC = (INT, REAL)
TOP = {
    (op, left, right): (
        BOOL if op in ("<>", "=", "<", "<=", ">", ">=")
        else REAL if op == "/" or REAL in (left, right) else INT
    )
    for op in ("+", "-", "*", "/", "<>", "=", "<", "<=", ">", ">=")
    for left in NUMERIC for right in NUMERIC
}
TOP.update({(op, BOOL, BOOL): BOOL for op in ("=", "and", "or")})


@dataclass
class Identifier:
    index: int
    name: str
    type: str | None = None
    address: int | None = None

    @property
    def declared(self):
        return self.type is not None


@dataclass(frozen=True)
class StackStep:
    action: str
    stack: tuple[str, ...]
    line: int
    column: int


@dataclass
class SemanticResult:
    identifiers: list[Identifier] = field(default_factory=list)
    diagnostics: list[SyntaxDiagnostic] = field(default_factory=list)
    trace: list[StackStep] = field(default_factory=list)
    trace_truncated: bool = False
    consumed: int = 0
    total: int = 0

    @property
    def ok(self):
        return not self.diagnostics


class _SemanticError(Exception):
    pass


class SemanticAnalyzer(Parser):
    """Семантические действия при рекурсивном спуске по готовым лексемам."""

    def analyze(self, lexical, *, syntax=None, trace=True):
        self.result = SemanticResult(
            [Identifier(i, name) for i, name in enumerate(lexical.identifiers, 1)],
            total=len(lexical.tokens),
        )
        self.stack = []
        self.declaration_stack = []
        self.declaration_tokens = []
        self.declaring = False
        self.trace_enabled = trace
        if syntax is not None and not syntax.ok:
            self.result.diagnostics.extend(syntax.diagnostics)
            return self.result
        try:
            parsed = super().analyze(lexical)
            self.result.diagnostics.extend(parsed.diagnostics)
        except _SemanticError:
            pass
        self.result.consumed = self.position
        return self.result

    def fail(self, token, rule, message, expected=(), found=None):
        self.result.diagnostics.append(SyntaxDiagnostic(
            message, rule, tuple(expected), token.text if found is None else found,
            token.start, token.end, token.line, token.column, "semantic",
        ))
        raise _SemanticError

    def record(self, token, action):
        if not self.trace_enabled:
            return
        if len(self.result.trace) >= 3000:
            self.result.trace_truncated = True
            return
        self.result.trace.append(StackStep(action, tuple(self.stack), token.line, token.column))

    @staticmethod
    def inst(stack, value):
        stack.append(value)

    @staticmethod
    def outst(stack):
        return stack.pop()

    def instl(self, token):
        """Сохранить номер TI и позицию имени для диагностики объявления."""
        self.inst(self.declaration_stack, token.index)
        self.declaration_tokens.append(token)

    def Dc(self):
        self.inst(self.declaration_stack, 0)
        self.declaring = True
        try:
            super().Dc()
            type_symbol = self.tokens[self.position - 1].text
            self.dec(TYPES[type_symbol])
        finally:
            self.declaring = False
            self.declaration_stack.clear()
            self.declaration_tokens.clear()

    def dec(self, type_name):
        declarations = []
        index = self.outst(self.declaration_stack)
        while index != 0:
            declarations.append((index, self.declaration_tokens.pop()))
            index = self.outst(self.declaration_stack)
        # Проверяем в порядке исходного текста и вносим типы одной группой.
        pending = {}
        for index, token in reversed(declarations):
            self.decid(index, token, type_name, pending)
        for index, declared_type in pending.items():
            self.result.identifiers[index - 1].type = declared_type

    def decid(self, index, token, type_name, pending):
        if index in pending or self.result.identifiers[index - 1].declared:
            self.fail(token, "Dc", f"Повторное объявление «{token.text}».")
        pending[index] = type_name

    def Id(self):
        token = self.LEX
        super().Id()
        if self.declaring:
            self.instl(token)
        else:
            return self.checkid(token)

    def checkid(self, token):
        entry = self.result.identifiers[token.index - 1]
        if not entry.declared:
            self.fail(token, "Id", f"Идентификатор «{token.text}» не объявлен к месту использования.")
        return entry.type

    def push_expression(self, token, value):
        self.inst(self.stack, value)
        self.record(token, f"Поместить {value}: {token.text}")

    def Mn(self):
        token = self.LEX
        if token.table == 3:
            # Id проверяет имя и возвращает его тип; здесь тип нужен стеку.
            self.push_expression(token, self.Id())
            return
        super().Mn()
        if token.table == 4:
            self.push_expression(token, REAL if token.kind == "REAL" else INT)
        elif token.text in ("true", "false"):
            self.push_expression(token, BOOL)
        elif token.text == "!":
            self.checknot(token)

    def checknot(self, token):
        operand = self.outst(self.stack)
        self.require(token, operand, BOOL, "Mn", "Операция !")
        self.inst(self.stack, BOOL)
        self.record(token, "! boolean → boolean")

    def begin_binary(self, operator):
        self.push_expression(operator, operator.text)

    def end_binary(self, operator):
        self.checkop(operator)

    @staticmethod
    def gettype(op, left, right):
        return TOP.get((op, left, right))

    def checkop(self, operator):
        right = self.outst(self.stack)
        op = self.outst(self.stack)
        left = self.outst(self.stack)
        result = self.gettype(op, left, right)
        if result is None:
            self.fail(operator, "Ex", f"Операция «{op}» недопустима для {left} и {right}.",
                      found=f"{left}, {right}")
        self.inst(self.stack, result)
        self.record(operator, f"{left} {op} {right} → {result}")

    def require(self, token, actual, expected, rule, context):
        if actual != expected:
            self.fail(token, rule, f"{context}: нужен тип {expected}, получен {actual}.",
                      (expected,), actual)

    def take_type(self, token, context):
        result = self.outst(self.stack)
        self.record(token, f"{context}: снять тип {result}")
        return result

    def assignment(self, counter=False):
        target = self.LEX
        super().Asg()
        actual = self.take_type(target, "Присваивание")
        expected = self.result.identifiers[target.index - 1].type
        self.eqtype(target, actual, expected, counter=counter)

    def eqtype(self, target, actual, expected, *, counter=False):
        if counter:
            self.require(target, expected, INT, "ForSt", "Счётчик for")
            self.require(target, actual, INT, "ForSt", "Начальное значение for")
        elif actual != expected and (expected, actual) != (REAL, INT):
            self.require(target, actual, expected, "Asg", "Присваивание")

    def Asg(self):
        self.assignment()

    def condition(self, rule):
        opening = self.LEX
        word = 'if' if rule == 'Cond' else 'while'
        self.take("(", rule, f"После «{word}» требуется условие в круглых скобках: «( ... )».")
        start = self.LEX
        self.Ex(f"В скобках после «{word}» ожидается выражение условия")
        self.take(")", rule, self.missing_close(')', opening))
        self.eqbool(start, rule)

    def eqbool(self, start, rule):
        self.require(start, self.take_type(start, "Условие"), BOOL, rule, "Условие")

    def Cond(self):
        self.take("if", "Cond")
        self.condition("Cond")
        self.statement("После условия «if» требуется оператор его тела")
        if self.EQ("else"):
            self.gl()
            self.statement("После «else» требуется оператор его ветви")

    def WhileSt(self):
        self.take("while", "WhileSt")
        self.condition("WhileSt")
        self.statement("После условия «while» требуется оператор тела цикла")

    def for_expression(self, context):
        start = self.LEX
        position = self.position
        self.Ex(f"{context}: ожидается выражение")
        if context == 'Шаг for' and self.position == position + 1 and start.table == 3 and self.EQ(':='):
            self.error('St', 'выражение шага после step', token=start,
                message=(f'После «step» пропущено выражение шага перед присваиванием «{start.text} :=». '
                         f'Укажите шаг, например: «step 1 {start.text} := ...»; '
                         'шагом также может быть идентификатор или составное выражение.'))
        self.require(start, self.take_type(start, context), INT, "ForSt", context)

    def ForSt(self):
        self.take("for", "ForSt")
        self.assignment(counter=True)
        self.take("to", "ForSt")
        self.for_expression("Граница for")
        if self.EQ("step"):
            self.gl()
            self.for_expression("Шаг for")
        self.statement("В цикле «for» после границы и шага требуется оператор тела")
        self.take("next", "ForSt")

    def ExL(self):
        while True:
            start = self.LEX
            self.Ex()
            self.take_type(start, "Вывод")
            if not self.EQ(","):
                return
            self.gl()
