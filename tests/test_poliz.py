import json
from pathlib import Path
import unittest
from fractions import Fraction
from unittest.mock import patch

from language.lexer import Lexer
from language.parser import Parser
from language.poliz import Compiler, EXTRA
from language.semantic import SemanticAnalyzer
from language.interpreter import Interpreter, show, Address


def compile_source(source):
    return Compiler().analyze(Lexer().analyze(source, trace=False))


class PolizTests(unittest.TestCase):
    def test_decimal_output_rounding(self):
        cases = [
            (Fraction(1,3), '0.333333333333'),
            (Fraction(2,3), '0.666666666667'),
            (Fraction(-2,3), '-0.666666666667'),
            (Fraction(5,2), '2.5'), (Fraction(-5,2), '-2.5'),
            (Fraction(2), '2'), (Fraction(0), '0'),
            (Fraction(1,10**12), '0.000000000001'),
            (Fraction(1,2*10**12), '0.000000000001'),
            (Fraction(-1,2*10**12), '-0.000000000001'),
            (Fraction(-1,10**13), '0'),
            (Fraction(19999999999999,20000000000000), '1'),
            (Fraction(-19999999999999,20000000000000), '-1'),
            (Fraction(1234567890123456789,10), '123456789012345678.9'),
            (True, 'true'), (False, 'false'), (Address(2), '&2'),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(show(value), expected)

    def test_rounding_does_not_change_calculations(self):
        p, r = self.run_source('dim x !:x := 1 / 3:writeln x, x * 3, x * 3 = 1:end')
        self.assertEqual(r.output, ['0.333333333333', '1', 'true'])
        self.assertEqual(r.memory[1], Fraction(1,3))
        self.assertTrue(any('0.333333333333' in step.memory for step in r.trace))
        self.assertTrue(any('0.333333333333' in step.stack for step in r.trace))

    def test_control_catalog(self):
        folder = Path(__file__).resolve().parents[1] / 'examples/poliz'
        cases = json.loads((folder/'cases.json').read_text(encoding='utf-8'))
        for case in cases:
            with self.subTest(case=case['title']):
                p = compile_source((folder/case['file']).read_text(encoding='utf-8'))
                self.assertEqual(p.ok, case['ok'])
                if p.ok:
                    r = Interpreter().run(p, case['inputs'])
                    self.assertTrue(r.ok, r.error)
                    self.assertEqual(r.output, case['output'])
                else:
                    self.assertEqual(p.diagnostics[0].phase, case['phase'])
                    self.assertEqual(p.code, [])

    def run_source(self, source, inputs=()):
        p = compile_source(source)
        self.assertTrue(p.ok, p.diagnostics)
        r = Interpreter().run(p, inputs)
        self.assertTrue(r.ok, r.error)
        return p, r

    def test_one_pass_and_error_order(self):
        # Parser.analyze только один раз на полный совмещённый проход.
        original = Parser.analyze
        calls = []
        def wrapped(instance, lexical):
            calls.append(instance)
            return original(instance, lexical)
        with patch.object(Parser, 'analyze', wrapped):
            p = compile_source('dim a %:a := 1:writeln a:end')
        self.assertTrue(p.ok)
        self.assertEqual(len(calls), 1)
        self.assertIsInstance(calls[0], Compiler)
        p = compile_source('x := 1:writeln (:end')
        self.assertFalse(p.ok)
        self.assertEqual(p.diagnostics[0].phase, 'semantic')
        self.assertEqual(p.code, [])
        self.assertFalse(Interpreter().run(p).ok)

    def test_postfix_and_pairs(self):
        p, r = self.run_source('dim a %:a := 2 + 3 * 4:writeln a:end')
        self.assertEqual([x.text for x in p.code], ['&a','2','3','4','*','+',':=','a','W','.'])
        self.assertEqual(r.output, ['14'])
        self.assertEqual(p.code[0].table, 5)
        self.assertEqual(p.code[7].table, 3)
        self.assertEqual(p.identifiers[0].address, 1)
        self.assertEqual(r.trace[-1].stack, ())

    def test_numeric_and_logical_operations(self):
        expressions = {
            '2 + 3 * 4': '14', '(2 + 3) * 4': '20', '10 - 3 - 2': '5',
            '1 / 3 + 1 / 6': '0.5', '1B + 1O + 1H + 1D': '4',
            '1 = 1.0': 'true', '1 <> 2': 'true', '2 < 1': 'false',
            '2 <= 2': 'true', '2 > 1': 'true', '2 >= 3': 'false',
            'true and !false': 'true', 'false or true': 'true', '!!false': 'false',
            '!(1 < 2)': 'false', '8 / 2 / 2': '2',
        }
        for ex, expected in expressions.items():
            with self.subTest(expression=ex):
                _, r = self.run_source(f'writeln {ex}:end')
                self.assertEqual(r.output, [expected])

    def test_conditions_and_while(self):
        for flag in ('true','false'):
            _, r = self.run_source(f'if ({flag}) writeln 1 else writeln 2:end')
            self.assertEqual(r.output, ['1' if flag == 'true' else '2'])
            _, r = self.run_source(f'if ({flag}) writeln 1:writeln 2:end')
            self.assertEqual(r.output, ['1','2'] if flag == 'true' else ['2'])
        _, r = self.run_source('dim a %:a := 0:while (a < 3) [writeln a:a := a + 1]:end')
        self.assertEqual(r.output, ['0','1','2'])
        _, r = self.run_source('while (false) writeln 1:writeln 2:end')
        self.assertEqual(r.output, ['2'])
        _, r = self.run_source('if (true) if (false) writeln 1 else writeln 2:end')
        self.assertEqual(r.output, ['2'])

    def test_for_variations_and_nested(self):
        for start, end, step, expected in (
            ('1','3','',['1','2','3']), ('3','1','step (0 - 1)',['3','2','1']),
            ('1','5','step 2',['1','3','5']), ('3','1','',[]), ('1','3','step (0 - 1)',[]),
            ('2','2','',['2']),
        ):
            _, r = self.run_source(f'dim i %:for i := {start} to {end} {step} writeln i next:end')
            self.assertEqual(r.output, expected)
        _, r = self.run_source('dim i,j,s %:s := 0:for i := 1 to 3 for j := 1 to 2 s := s + i * j next next:writeln s:end')
        self.assertEqual(r.output, ['18'])
        # Граница и шаг фиксируются при входе, изменение n внутри тела не меняет число итераций.
        _, r = self.run_source('dim i,n %:n := 3:for i := 1 to n [writeln i:n := 1] next:end')
        self.assertEqual(r.output, ['1','2','3'])

    def test_input_and_memory(self):
        _, r = self.run_source('dim a %:dim r !:dim b $:readln a,r,b:writeln a,r,b:end', ['-10B','.5','TRUE'])
        self.assertEqual(r.output, ['-2','0.5','true'])
        for source, inputs, message in (
            ('dim a %:writeln a:end', [], 'не получила значение'),
            ('dim a %:readln a:end', [], 'Недостаточно входных'),
            ('dim a %:readln a:end', ['1.0'], 'целая запись'),
            ('dim a $:readln a:end', ['1'], 'true или false'),
            ('dim a !:readln a:end', ['1 2'], 'одно число'),
            ('writeln 1 / 0:end', [], 'Деление на ноль'),
            ('dim a %:for a := 1 to 2 step 0 writeln a next:end', [], 'нулевым'),
        ):
            with self.subTest(source=source):
                p = compile_source(source)
                self.assertTrue(p.ok, p.diagnostics)
                r = Interpreter().run(p,inputs)
                self.assertFalse(r.ok)
                self.assertIn(message, r.error)

    def test_limits_and_lexer_unchanged(self):
        p = compile_source('while (true) writeln 1:end')
        r = Interpreter().run(p,max_steps=30)
        self.assertIn('предел выполнения',r.error)
        p, r = self.run_source('dim a %:a := 0:while (a < 1000) a := a + 1:end')
        self.assertTrue(r.trace_truncated)
        self.assertEqual(len(r.trace), 3000)
        for source in ('dim a %:a := 1:', 'writeln 8O:end', 'writeln 1 + :end'):
            p = compile_source(source)
            self.assertFalse(p.ok)
            self.assertEqual(p.code, [])

    def test_regression_syntax_when_semantically_declared(self):
        folder = Path(__file__).resolve().parents[1] / 'examples/syntax'
        for source_path in folder.rglob('*.txt'):
            source = source_path.read_text(encoding='utf-8')
            lex = Lexer().analyze(source,trace=False)
            result = Compiler().analyze(lex)
            if result.ok:
                self.assertTrue(Parser().analyze(lex).ok)
            for item in result.code:
                if item.table == 0:
                    self.assertTrue(1 <= item.index <= len(result.code))
