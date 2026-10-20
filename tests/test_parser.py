"""Контроль конструкций, диагностик и независимое сравнение с КС-грамматикой."""
import json
from pathlib import Path
import random
import unittest

from language.lexer import Lexer
from language.parser import Parser, SYMBOLS


# Исходные леворекурсивные продукции ЛР1 (лексический уровень свернут в ID/NUM).
# Оракул Эрли используется только в тестах, не в рабочем анализаторе.
GRAMMAR = {
    "Pr": [("StL", "end")],
    "StL": [("Dc", "Sep"), ("St", "Sep"), ("StL", "Dc", "Sep"), ("StL", "St", "Sep")],
    "Sep": [(":",), ("/n",)],
    "Dc": [("dim", "IdL", "Tp")],
    "IdL": [("ID",), ("IdL", ",", "ID")],
    "Tp": [("%",), ("!",), ("$",)],
    "St": [("Cmp",), ("Asg",), ("Cond",), ("ForSt",), ("WhileSt",), ("readln", "IdL"), ("writeln", "ExL")],
    "Cmp": [("[", "St", "CmpL", "]")],
    "CmpL": [(), ("CmpL", "Sep", "St")],
    "Asg": [("ID", ":=", "Ex")],
    "Cond": [("if", "(", "Ex", ")", "St", "else", "St"), ("if", "(", "Ex", ")", "St")],
    "ForSt": [("for", "Asg", "to", "Ex", "St", "next"),
              ("for", "Asg", "to", "Ex", "step", "Ex", "St", "next")],
    "WhileSt": [("while", "(", "Ex", ")", "St")],
    "ExL": [("Ex",), ("ExL", ",", "Ex")],
    "Ex": [("Op",), ("Ex", "Rel", "Op")],
    "Rel": [(x,) for x in ("<>", "=", "<", "<=", ">", ">=")],
    "Op": [("Sl",), ("Op", "Add", "Sl")],
    "Add": [(x,) for x in ("+", "-", "or")],
    "Sl": [("Mn",), ("Sl", "Mul", "Mn")],
    "Mul": [(x,) for x in ("*", "/", "and")],
    "Mn": [("ID",), ("NUM",), ("Lg",), ("!", "Mn"), ("(", "Ex", ")")],
    "Lg": [("true",), ("false",)],
}


def belongs(words):
    """Независимый алгоритм принадлежности исходной грамматике, включая ε."""
    charts = [set() for _ in range(len(words) + 1)]
    charts[0].add(("START", ("Pr",), 0, 0))
    for i, chart in enumerate(charts):
        changed = True
        while changed:
            before = len(chart)
            for lhs, rhs, dot, origin in tuple(chart):
                if dot == len(rhs):
                    for a, b, d, o in tuple(charts[origin]):
                        if d < len(b) and b[d] == lhs:
                            chart.add((a, b, d + 1, o))
                elif rhs[dot] in GRAMMAR:
                    for production in GRAMMAR[rhs[dot]]:
                        chart.add((rhs[dot], production, 0, i))
                elif i < len(words) and rhs[dot] == words[i]:
                    charts[i + 1].add((lhs, rhs, dot + 1, origin))
            changed = len(chart) != before
    return ("START", ("Pr",), 1, 0) in charts[-1]


def parse(source):
    lexical = Lexer().analyze(source, trace=False)
    return lexical, Parser().analyze(lexical)


class ParserTests(unittest.TestCase):
    def test_control_files(self):
        folder = Path(__file__).resolve().parents[1] / "examples" / "syntax"
        cases = json.loads((folder / "cases.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(file=case["file"]):
                lexical, result = parse((folder / case["file"]).read_text(encoding="utf-8"))
                self.assertTrue(lexical.ok, lexical.diagnostics)
                self.assertEqual(result.ok, case["ok"], result.diagnostics)
                if not result.ok:
                    self.assertEqual(len(result.diagnostics), 1)
                    self.assertEqual(result.diagnostics[0].rule, case["rule"])

    def test_lexer_failure_blocks_parser(self):
        lexical, result = parse("dim x %\nx := 8O\nend")
        self.assertFalse(lexical.ok)
        self.assertFalse(result.ok)
        self.assertEqual(result.consumed, 0)
        self.assertEqual(result.diagnostics[0].phase, "lexical")
        self.assertEqual(result.diagnostics[0].start, lexical.diagnostics[0].start)

    def test_positions_and_eof(self):
        for source, rule, line, column, start in (
            ("dim x %\nx := (1 + )\nend", "Mn", 2, 11, 18),
            ("dim x %\nx := 1\n", "Pr", 3, 1, 15),
            ("dim x %\nend\nwriteln x", "Pr", 2, 4, 11),
        ):
            with self.subTest(source=source):
                lexical, result = parse(source)
                self.assertTrue(lexical.ok)
                d = result.diagnostics[0]
                self.assertEqual((d.rule, d.line, d.column, d.start), (rule, line, column, start))

    def test_symbol_identity_uses_pairs(self):
        # end внутри имени и END не являются зарезервированным словом end.
        for name in ("endless", "END", "ending2"):
            self.assertTrue(parse(f"dim {name} %\n{name} := 1\nend")[1].ok)
        self.assertFalse(parse("dim end %\nend")[1].ok)

    def test_comparisons_and_no_semantic_checks(self):
        for expression in ("1 < 2 < 3", "true or false and !false", "1 + 2 * 3", "(1 + 2) * 3"):
            self.assertTrue(parse(f"x := {expression}:end")[1].ok)
        # Грамматика не требует объявления и не проверяет типы / деление на ноль.
        self.assertTrue(parse("unknown := true + 1 / 0:end")[1].ok)

    def test_long_lists_do_not_recurse(self):
        source = "dim " + ",".join(f"x{i}" for i in range(2000)) + "%\n"
        source += "x0 := " + "+".join("1" for _ in range(3000)) + "\n"
        source += "x0 := 1\n" * 3000 + "end"
        self.assertTrue(parse(source)[1].ok)

    def test_depth_limit_is_reported_and_parser_reusable(self):
        parser = Parser()
        for expression in ("!" * 100 + "true", "(" * 100 + "1" + ")" * 100):
            result = parser.analyze(Lexer().analyze(f"x := {expression}:end", trace=False))
            self.assertFalse(result.ok)
            self.assertIn("предел вложенности", result.diagnostics[0].message)
        self.assertTrue(parser.analyze(Lexer().analyze("x := 1:end")).ok)

    def test_independent_grammar_oracle(self):
        folder = Path(__file__).resolve().parents[1] / "examples" / "syntax"
        sources = [p.read_text(encoding="utf-8") for p in folder.rglob("*.txt")]
        rng = random.Random(310)
        expressions = ["x", "1", "true", "false", "!x", "(x + 1)"]
        for _ in range(70):
            a, b, c = rng.choices(expressions, k=3)
            op, op2 = rng.choices(["+", "-", "or", "*", "/", "and", "<", "="], k=2)
            sources.append(f"writeln {a} {op} {b} {op2} {c}:end")
        # Удаления / вставки / замены терминалов: ожидаемый результат даёт CFG,
        # а не предположение, что любая мутация обязательно ошибочна.
        originals = list(sources)
        for source in originals:
            lexical, _ = parse(source)
            if not lexical.ok:
                continue
            words = [t.text for t in lexical.tokens]
            for _ in range(2):
                altered = list(words)
                index = rng.randrange(len(altered)) if altered else 0
                if altered and rng.choice((True, False)):
                    del altered[index]
                else:
                    altered.insert(index, rng.choice(["else", "]", ",", ":", "+", "next"]))
                sources.append(" ".join(altered))
        for source in sources:
            with self.subTest(source=source):
                lexical, result = parse(source)
                if not lexical.ok:
                    continue
                words = ["ID" if t.table == 3 else "NUM" if t.table == 4 else
                         SYMBOLS[(t.table, t.index)] for t in lexical.tokens]
                self.assertEqual(result.ok, belongs(words), result.diagnostics)


if __name__ == "__main__":
    unittest.main()
