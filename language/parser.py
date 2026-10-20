from dataclasses import dataclass, field

from .models import AnalysisResult, Token
from .tables import TW, TL


SYMBOLS = {(table, i): ("/n" if word == "NL" else word)
           for table, words in ((1, TW), (2, TL))
           for i, (word, _) in enumerate(words, 1)}
PAIRS = {word: pair for pair, word in SYMBOLS.items()}


@dataclass(frozen=True)
class SyntaxDiagnostic:
    message: str
    rule: str
    expected: tuple[str, ...]
    found: str
    start: int
    end: int
    line: int
    column: int
    phase: str = "syntax"


@dataclass
class SyntaxResult:
    diagnostics: list[SyntaxDiagnostic] = field(default_factory=list)
    consumed: int = 0
    total: int = 0

    @property
    def ok(self) -> bool:
        return not self.diagnostics


class _ParseError(Exception):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic


class Parser:
    """Один метод на синтаксический нетерминал; Id и Nb — готовые лексемы.

    Пробелы и комментарии уже обработаны лексером. /n — терминал Sep,
    его нельзя произвольно пропускать. После end не допускаются лексемы.
    else относится к ближайшему ещё не завершённому if.
    """

    def analyze(self, lexical: AnalysisResult) -> SyntaxResult:
        self.tokens = lexical.tokens
        self.position = 0
        self.depth = 0
        source = lexical.source
        self.eof = Token(0, 0, "EOF", len(source), len(source),
                         source.count("\n") + 1, len(source.rsplit("\n", 1)[-1]) + 1)
        result = SyntaxResult(total=len(self.tokens))
        if not lexical.ok:
            d = lexical.diagnostics[0]
            result.diagnostics.append(SyntaxDiagnostic(
                "Синтаксический разбор не запущен: " + d.message,
                d.state, (), source[d.start:d.end] or "EOF",
                d.start, d.end, d.line, d.column, "lexical"))
            return result
        try:
            self.Pr()
        except _ParseError as error:
            result.diagnostics.append(error.diagnostic)
        result.consumed = self.position
        return result

    @property
    def LEX(self) -> Token:
        return self.tokens[self.position] if self.position < len(self.tokens) else self.eof

    def gl(self):
        """Перейти к следующей лексеме, не читая исходные символы повторно."""
        if self.position < len(self.tokens):
            self.position += 1

    def EQ(self, symbol: str) -> bool:
        return (self.LEX.table, self.LEX.index) == PAIRS[symbol]

    def ID(self) -> bool:
        return self.LEX.table == 3

    def NUM(self) -> bool:
        return self.LEX.table == 4

    def one_of(self, *symbols) -> bool:
        return any(self.EQ(symbol) for symbol in symbols)

    def error(self, rule, *expected, message=None, phase="syntax"):
        token = self.LEX
        found = ("конец файла" if token.table == 0 else
                 "/n" if self.EQ("/n") else token.text)
        choices = ", ".join(f"«{item}»" for item in expected)
        text = message or f"Ожидалось: {choices}. Получено: «{found}»."
        raise _ParseError(SyntaxDiagnostic(text, rule, tuple(expected), found,
                                           token.start, token.end, token.line, token.column, phase))

    def take(self, symbol, rule):
        if not self.EQ(symbol):
            self.error(rule, symbol)
        self.gl()

    def enter(self, rule):
        # Ограничение реализации, а не ограничение грамматики.
        # Списки и длинные выражения обрабатываются циклами, без этого лимита.
        self.depth += 1
        if self.depth > 80:
            self.error(rule, message="Превышен предел вложенности анализатора (80 уровней).",
                       phase="limit")

    def Pr(self):
        """Pr → StL end."""
        self.StL()
        self.take("end", "Pr")
        if self.LEX.table != 0:
            self.error("Pr", "конец файла", message="После end не должно быть лексем, включая /n.")

    def StL(self):
        """StL → (Dc | St) Sep { (Dc | St) Sep }; не пустой."""
        while True:
            if self.EQ("dim"):
                self.Dc()
            else:
                self.St()
            self.Sep()
            if self.EQ("end"):
                return
            if self.LEX.table == 0:
                self.error("Pr", "end")

    def Sep(self):
        """Sep → : | /n."""
        if not self.one_of(":", "/n"):
            self.error("Sep", ":", "/n")
        self.gl()

    def Dc(self):
        """Dc → dim IdL Tp."""
        self.take("dim", "Dc")
        self.IdL()
        self.Tp()

    def IdL(self):
        """IdL → Id { , Id }."""
        self.Id()
        while self.EQ(","):
            self.gl()
            self.Id()

    def Tp(self):
        if not self.one_of("%", "!", "$"):
            self.error("Tp", "%", "!", "$")
        self.gl()

    def St(self):
        """St → Cmp | Asg | Cond | ForSt | WhileSt | readln IdL | writeln ExL."""
        self.enter("St")
        try:
            if self.EQ("["):
                self.Cmp()
            elif self.ID():
                self.Asg()
            elif self.EQ("if"):
                self.Cond()
            elif self.EQ("for"):
                self.ForSt()
            elif self.EQ("while"):
                self.WhileSt()
            elif self.EQ("readln"):
                self.gl()
                self.IdL()
            elif self.EQ("writeln"):
                self.gl()
                self.ExL()
            else:
                self.error("St", "идентификатор", "[", "if", "for", "while", "readln", "writeln")
        finally:
            self.depth -= 1

    def Cmp(self):
        """Cmp → [ St CmpL ]; пустой блок и разделитель перед ] запрещены."""
        self.take("[", "Cmp")
        self.St()
        self.CmpL()
        self.take("]", "Cmp")

    def CmpL(self):
        """CmpL → ε | CmpL Sep St; эквивалентно { Sep St }."""
        while self.one_of(":", "/n"):
            self.Sep()
            self.St()

    def Asg(self):
        self.Id()
        self.take(":=", "Asg")
        self.Ex()

    def Cond(self):
        self.take("if", "Cond")
        self.take("(", "Cond")
        self.Ex()
        self.take(")", "Cond")
        self.St()
        if self.EQ("else"):
            self.gl()
            self.St()

    def ForSt(self):
        self.take("for", "ForSt")
        self.Asg()
        self.take("to", "ForSt")
        self.Ex()
        if self.EQ("step"):
            self.gl()
            self.Ex()
        self.St()
        self.take("next", "ForSt")

    def WhileSt(self):
        self.take("while", "WhileSt")
        self.take("(", "WhileSt")
        self.Ex()
        self.take(")", "WhileSt")
        self.St()

    def ExL(self):
        self.Ex()
        while self.EQ(","):
            self.gl()
            self.Ex()

    def Ex(self):
        """Ex → Op | Ex Rel Op; допускается несколько отношений."""
        self.Op()
        while self.one_of("<>", "=", "<", "<=", ">", ">="):
            self.Rel()
            self.Op()

    def Rel(self):
        if not self.one_of("<>", "=", "<", "<=", ">", ">="):
            self.error("Rel", "<>", "=", "<", "<=", ">", ">=")
        self.gl()

    def Op(self):
        """Op → Sl { Add Sl }."""
        self.Sl()
        while self.one_of("+", "-", "or"):
            self.Add()
            self.Sl()

    def Add(self):
        if not self.one_of("+", "-", "or"):
            self.error("Add", "+", "-", "or")
        self.gl()

    def Sl(self):
        """Sl → Mn { Mul Mn }."""
        self.Mn()
        while self.one_of("*", "/", "and"):
            self.Mul()
            self.Mn()

    def Mul(self):
        if not self.one_of("*", "/", "and"):
            self.error("Mul", "*", "/", "and")
        self.gl()

    def Mn(self):
        """Mn → Id | Nb | Lg | ! Mn | ( Ex )."""
        self.enter("Mn")
        try:
            if self.ID():
                self.Id()
            elif self.NUM():
                self.Nb()
            elif self.one_of("true", "false"):
                self.Lg()
            elif self.EQ("!"):
                self.gl()
                self.Mn()
            elif self.EQ("("):
                self.gl()
                self.Ex()
                self.take(")", "Mn")
            else:
                self.error("Mn", "идентификатор", "число", "true", "false", "!", "(")
        finally:
            self.depth -= 1

    def Lg(self):
        if not self.one_of("true", "false"):
            self.error("Lg", "true", "false")
        self.gl()

    def Id(self):
        if not self.ID():
            self.error("Id", "идентификатор")
        self.gl()

    def Nb(self):
        if not self.NUM():
            self.error("Nb", "число")
        self.gl()
