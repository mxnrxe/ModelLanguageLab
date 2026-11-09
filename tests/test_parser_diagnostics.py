"""Контекстные сообщения без изменения принятого языка."""
import unittest

from language.lexer import Lexer
from language.parser import Parser


class ParserDiagnosticTests(unittest.TestCase):
    def diagnostic(self, source):
        lexical = Lexer().analyze(source, trace=False)
        self.assertTrue(lexical.ok, lexical.diagnostics)
        result = Parser().analyze(lexical)
        self.assertFalse(result.ok)
        self.assertEqual(len(result.diagnostics), 1)
        return result.diagnostics[0]

    def test_missing_step_before_assignment_points_to_body(self):
        source = ("dim a, b, i, s %\nreadln a, b\ns := 0\n"
                  "for i := a to b step  s := s + i next\n"
                  "if (s >= 0) writeln s else writeln 0\nend")
        d = self.diagnostic(source)
        self.assertIn("После «step» пропущено выражение шага", d.message)
        self.assertIn("«s :=»", d.message)
        self.assertEqual(d.expected, ("выражение шага после step",))
        self.assertEqual((d.line, d.column, d.found), (4, 23, "s"))
        self.assertEqual(source[d.start:d.end], "s")

    def test_step_still_accepts_identifiers_and_expressions(self):
        for step in ("1", "delta", "a + b", "(a + 1) * 2", "!false"):
            with self.subTest(step=step):
                source = f"for i := a to b step {step} s := s + i next:end"
                self.assertTrue(Parser().analyze(Lexer().analyze(source)).ok)
        d = self.diagnostic("for i := 1 to 10 step next:end")
        self.assertIn("После «step» ожидается выражение шага", d.message)

    def test_block_close_after_separator_and_nested_boundaries(self):
        for source in ("[x := 1\nend", "[x := 1:end",
                       "for i := 1 to 2 [x := 1\nnext:end",
                       "if (true) [x := 1\nelse writeln 0:end",
                       "[x := 1\n"):
            with self.subTest(source=source):
                d = self.diagnostic(source)
                self.assertEqual((d.rule, d.expected), ("Cmp", ("]",)))
                self.assertIn("Не закрыта скобка «[»", d.message)
                self.assertNotIn("«идентификатор», «[», «if»", d.message)

    def test_round_close_identifies_opening(self):
        for source in ("x := (1 + 2:end", "if (true writeln 1:end",
                       "while (true writeln 1:end"):
            with self.subTest(source=source):
                d = self.diagnostic(source)
                self.assertEqual(d.expected, (")",))
                self.assertIn("Не закрыта скобка «(»", d.message)
                self.assertIn("строке 1", d.message)

    def test_missing_expression_has_its_construct_context(self):
        for source, context in (
            ("x := :end", "После «:=»"),
            ("for i := 1 to next:end", "После «to»"),
            ("writeln :end", "После «writeln»"),
            ("writeln 1,:end", "После запятой"),
        ):
            with self.subTest(source=source):
                d = self.diagnostic(source)
                self.assertEqual(d.rule, "Mn")
                self.assertIn(context, d.message)

    def test_body_errors_do_not_hide_inner_or_separator_errors(self):
        for source, context in (
            ("if (true) :end", "После условия «if»"),
            ("if (true) x := 1 else :end", "После «else»"),
            ("while (true) :end", "После условия «while»"),
            ("for i := 1 to 2 next:end", "оператор тела"),
            ("[x := 1\n]:end", "Разделитель перед «]» недопустим"),
        ):
            with self.subTest(source=source):
                d = self.diagnostic(source)
                self.assertEqual(d.rule, "St")
                self.assertIn(context, d.message)
                self.assertNotIn("Не закрыта скобка", d.message)
        d = self.diagnostic("if (true) [x := (1 + ):end")
        self.assertEqual((d.rule, d.found), ("Mn", ")"))
        self.assertIn("После «:=»", d.message)
        self.assertNotIn("После условия «if»", d.message)

    def test_missing_operand_names_the_operator(self):
        for operator in ("+", "*", ">=", "and", "!"):
            with self.subTest(operator=operator):
                expression = "!" if operator == "!" else f"1 {operator}"
                d = self.diagnostic(f"x := {expression}:end")
                self.assertEqual(d.rule, "Mn")
                self.assertIn(f"После оператора «{operator}» ожидается операнд", d.message)


if __name__ == "__main__":
    unittest.main()
