import unittest
from pathlib import Path

from language.lexer import Lexer
from language.parser import Parser
from language.semantic import SemanticAnalyzer, TOP, INT, REAL, BOOL


def check(source):
    return SemanticAnalyzer().analyze(Lexer().analyze(source, trace=False))


class SemanticTests(unittest.TestCase):
    def test_example_and_stack(self):
        path = Path(__file__).resolve().parents[1] / "examples" / "semantic.txt"
        r = check(path.read_text(encoding="utf-8").rstrip("\n"))
        self.assertTrue(r.ok, r.diagnostics)
        self.assertEqual([i.type for i in r.identifiers], [INT, INT, INT, REAL, BOOL])
        self.assertEqual([s.stack for s in r.trace if s.line == 5],
                         [(INT,), (INT, "+"), (INT, "+", INT), (INT, "+", INT, "*"),
                          (INT, "+", INT, "*", INT), (INT, "+", INT), (INT,), ()])

    def test_declarations_and_operators(self):
        for source, rule, line, column in (
            ("dim x,x %\nend", "Dc", 1, 7),
            ("dim x %\ndim x !\nend", "Dc", 2, 5),
            ("readln x\ndim x %\nend", "Id", 1, 8),
            ("x := 1:end", "Id", 1, 1),
            ("dim x %\nx := y:end", "Id", 2, 6),
            ("dim x %\nx := 1.0:end", "Asg", 2, 1),
            ("writeln 1 and true:end", "Ex", 1, 11),
            ("writeln !1:end", "Mn", 1, 9),
            ("if (1) writeln 1:end", "Cond", 1, 5),
            ("while (1.0) writeln 1:end", "WhileSt", 1, 8),
            ("dim x !:for x := 1 to 2 writeln x next:end", "ForSt", 1, 13),
            ("dim x %:for x := 1.0 to 2 writeln x next:end", "ForSt", 1, 13),
            ("dim x %:for x := 1 to 2.0 writeln x next:end", "ForSt", 1, 23),
            ("dim x %:for x := 1 to 2 step true writeln x next:end", "ForSt", 1, 30),
        ):
            with self.subTest(source=source):
                r = check(source)
                self.assertFalse(r.ok)
                d, = r.diagnostics
                self.assertEqual((d.phase, d.rule, d.line, d.column),
                                 ("semantic", rule, line, column))

    def test_all_binary_type_combinations(self):
        atoms = {INT: "1", REAL: "1.0", BOOL: "true"}
        for op in ("+", "-", "*", "/", "<>", "=", "<", "<=", ">", ">=", "and", "or"):
            for left, a in atoms.items():
                for right, b in atoms.items():
                    with self.subTest(op=op, left=left, right=right):
                        r = check(f"writeln {a} {op} {b}:end")
                        numeric = BOOL not in (left, right)
                        if op in ("and", "or"):
                            expected = BOOL if left == right == BOOL else None
                        elif op in ("<>", "=", "<", "<=", ">", ">="):
                            expected = BOOL if numeric or op == "=" and left == right else None
                        else:
                            expected = (REAL if REAL in (left, right) or op == "/" else INT) if numeric else None
                        self.assertEqual(r.ok, expected is not None)
                        if expected:
                            self.assertEqual(r.trace[-2].stack, (expected,))
        self.assertEqual(len(TOP), 43)

    def test_literal_types_and_control_flow(self):
        for source in (
            "dim x !:x := 1:end",
            "dim x !:x := 1 / 2:end",
            "dim x %:x := 1B + 1O + 01H + 1D:end",
            "dim x %:for x := 1 to 2 step 1 [if (!false) writeln x:readln x] next:end",
            "dim x %:while (x <= 1.0) x := x + 1:end",
            "writeln ! (1 < 2), (1 = 1) and true:end",
        ):
            with self.subTest(source=source):
                r = check(source)
                self.assertTrue(r.ok, r.diagnostics)
        lex = Lexer().analyze("writeln 1, 1.0:end")
        self.assertEqual(len(lex.numbers), 1)
        r = SemanticAnalyzer().analyze(lex)
        self.assertEqual([s.stack for s in r.trace], [(INT,), (), (REAL,), ()])

    def test_phase_gate_and_reuse(self):
        a = SemanticAnalyzer()
        for source, phase in (("x := 8O:end", "lexical"),
                              ("x := 1 + :end", "syntax"),
                              ("x := 1:end", "semantic")):
            r = a.analyze(Lexer().analyze(source))
            self.assertEqual(r.diagnostics[0].phase, phase)
            self.assertTrue(a.analyze(Lexer().analyze("dim x %:x := 1:end")).ok)
        self.assertTrue(Parser().analyze(Lexer().analyze("x := true + 1:end")).ok)

    def test_long_trace_limit(self):
        source = "writeln " + "+".join(["1"] * 1500) + ":end"
        r = check(source)
        self.assertTrue(r.ok)
        self.assertTrue(r.trace_truncated)
        self.assertEqual(len(r.trace), 3000)
