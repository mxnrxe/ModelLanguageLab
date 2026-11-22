from dataclasses import dataclass, field
from fractions import Fraction

from .poliz import EXTRA
from .semantic import INT, REAL, BOOL


@dataclass(frozen=True)
class Address:
    index: int


@dataclass(frozen=True)
class ExecutionStep:
    pc: int
    item: str
    stack: tuple[str, ...]
    memory: str
    output: str


@dataclass
class Execution:
    output: list[str] = field(default_factory=list)
    trace: list[ExecutionStep] = field(default_factory=list)
    memory: dict = field(default_factory=dict)
    error: str = ''
    pc: int = 0
    trace_truncated: bool = False

    @property
    def ok(self):
        return not self.error


def show(value):
    if isinstance(value, Address):
        return '&' + str(value.index)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    # Округляется только строка. Точные значения Fraction в стеке и памяти
    # не меняются. Половина округляется от нуля: 0.5 последнего разряда вверх.
    value = Fraction(value)
    scale = 10 ** 12
    units, remainder = divmod(abs(value.numerator) * scale, value.denominator)
    if remainder * 2 >= value.denominator:
        units += 1
    integer, fraction = divmod(units, scale)
    tail = str(fraction).zfill(12).rstrip('0')
    sign = '-' if value < 0 and units else ''
    return sign + str(integer) + ('.' + tail if tail else '')


class RuntimeFault(Exception):
    pass


class Interpreter:
    """Стековая машина; ввод передаётся явно, eval/exec не используются."""

    def run(self, program, inputs=(), *, max_steps=100000, trace=True):
        result = Execution()
        if not program.ok:
            result.error = 'Выполнение запрещено: программа не прошла трансляцию.'
            return result
        self.program, self.result = program, result
        self.stack = []
        self.input = iter(inputs)
        self.pc = 1
        try:
            for _ in range(max_steps):
                if not 1 <= self.pc <= len(program.code):
                    raise RuntimeFault('Неверная метка перехода.')
                result.pc = self.pc
                item = program.code[self.pc - 1]
                next_pc = self.execute(item)
                if trace:
                    if len(result.trace) < 3000:
                        memory = '; '.join(f'{e.name}=' +
                            (show(result.memory[e.index]) if e.index in result.memory else '-')
                            for e in program.identifiers if e.declared)
                        result.trace.append(ExecutionStep(self.pc, item.text,
                            tuple(show(x) for x in self.stack), memory, ' '.join(result.output)))
                    else:
                        result.trace_truncated = True
                if next_pc is None:
                    return result
                self.pc = next_pc
            raise RuntimeFault(f'Превышен предел выполнения: {max_steps} команд.')
        except (RuntimeFault, ZeroDivisionError, ValueError, IndexError, StopIteration) as error:
            text = str(error) or 'Недостаточно входных данных.'
            if isinstance(error, ZeroDivisionError):
                text = 'Деление на ноль.'
            item = program.code[result.pc - 1]
            result.error = f'ПОЛИЗ {result.pc}, {item.line}:{item.column}: {text}'
        return result

    def addr(self, item):
        return Address(item.index)

    def cont(self, address):
        if address.index not in self.result.memory:
            name = self.program.identifiers[address.index - 1].name
            raise RuntimeFault(f'Переменная «{name}» не получила значение.')
        return self.result.memory[address.index]

    def let(self, address, value):
        if not isinstance(address, Address):
            raise RuntimeFault('Ожидался адрес переменной.')
        expected = self.program.identifiers[address.index - 1].type
        if expected == BOOL:
            valid = isinstance(value, bool)
        else:
            valid = not isinstance(value, bool) and isinstance(value, Fraction)
            valid = valid and (expected == REAL or value.denominator == 1)
        if not valid:
            raise RuntimeFault(f'Записываемое значение не соответствует типу {expected}.')
        self.result.memory[address.index] = value

    def inst(self, value):
        self.stack.append(value)

    def outst(self):
        if not self.stack:
            raise RuntimeFault('Пустой стек исполнения.')
        return self.stack.pop()

    def read(self, address):
        raw = str(next(self.input)).strip()
        expected = self.program.identifiers[address.index - 1].type
        if expected == BOOL:
            if raw.lower() not in ('true', 'false'):
                raise RuntimeFault('Для boolean введите true или false.')
            return raw.lower() == 'true'
        # Ввод - одно числовое значение; отрицательный знак разрешён во входных данных.
        from .lexer import Lexer
        negative = raw.startswith('-')
        raw = raw[1:] if raw[:1] in ('-', '+') else raw
        lex = Lexer().analyze('writeln ' + raw + ':end', trace=False)
        if not lex.ok or len(lex.tokens) != 4 or lex.tokens[1].table != 4:
            raise RuntimeFault('Ожидалось одно число модельного языка.')
        if expected == INT and lex.tokens[1].kind == 'REAL':
            raise RuntimeFault('Для integer требуется целая запись числа.')
        value = lex.numbers[lex.tokens[1].index - 1].value
        return -value if negative else value

    def execute(self, item):
        n, k = item.table, item.index
        next_pc = self.pc + 1
        if n == 0:
            self.inst(k)
        elif n == 5:
            self.inst(self.addr(item))
        elif n == 3:
            self.inst(self.cont(self.addr(item)))
        elif n == 4:
            self.inst(self.program.constants[k - 1])
        elif n == 6:
            self.inst(Fraction(k))
        elif n == 1 and item.text in ('true', 'false'):
            self.inst(item.text == 'true')
        elif n == 2 or n == 1 and item.text in ('and', 'or'):
            if k == EXTRA['.']:
                if self.stack:
                    raise RuntimeFault('В конце программы стек не пуст.')
                return None
            if k == EXTRA['JMP']:
                return self.outst()
            if k == EXTRA['!F']:
                target, condition = self.outst(), self.outst()
                if not isinstance(condition, bool):
                    raise RuntimeFault('Условие перехода не boolean.')
                return next_pc if condition else target
            if k == EXTRA['R']:
                address = self.outst()
                self.let(address, self.read(address))
            elif k == EXTRA['W']:
                self.result.output.append(show(self.outst()))
            elif k == EXTRA['STEP']:
                if self.outst() == 0:
                    raise RuntimeFault('Шаг for не может быть нулевым.')
            elif item.text == ':=':
                value, address = self.outst(), self.outst()
                self.let(address, value)
            elif item.text == '!':
                self.inst(not self.outst())
            else:
                right, left = self.outst(), self.outst()
                op = item.text
                if isinstance(left, Fraction) and isinstance(right, Fraction):
                    size = max(left.numerator.bit_length(), left.denominator.bit_length(),
                               right.numerator.bit_length(), right.denominator.bit_length())
                    if size > 16384:
                        raise RuntimeFault('Превышен предел размера числового значения (16384 бит).')
                if op == '+': value = left + right
                elif op == '-': value = left - right
                elif op == '*': value = left * right
                elif op == '/': value = left / right
                elif op == 'and': value = left and right
                elif op == 'or': value = left or right
                elif op == '=': value = left == right
                elif op == '<>': value = left != right
                elif op == '<': value = left < right
                elif op == '<=': value = left <= right
                elif op == '>': value = left > right
                elif op == '>=': value = left >= right
                else: raise RuntimeFault(f'Неизвестная операция {op}.')
                self.inst(value)
        else:
            raise RuntimeFault('Неизвестный элемент ПОЛИЗа.')
        return next_pc
