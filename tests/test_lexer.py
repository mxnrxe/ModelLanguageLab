import random
import json
import xml.etree.ElementTree as ET
import unittest
from fractions import Fraction
from pathlib import Path
from language.lexer import Lexer
from language.numbers import convert_number, display_value
from language.tables import TW, TL
from language.transitions import TRANSITIONS, ENTRY_ACTIONS


class LexerTests(unittest.TestCase):
    def test_diagram_correspondence(self):
        names = {"PB":"P2","PO":"P8","PH":"P16","PD":"U10","X":"N16",
            "E":"Exp","EU":"NK","DOT":"T","FR":"E1","RE":"EX","ES":"TT","RP":"Mn","LT":"CM","GT":"CB"}
        root = ET.parse(Path(__file__).resolve().parents[1] / "docs" / "Схема.drawio")
        transitions = []
        entries = {}
        for cell in root.iter('mxCell'):
            if cell.get('edge') == '1':
                source, target = cell.get('logicalSource'), cell.get('logicalTarget')
                transitions.append((cell.get('id'), names.get(source,source), names.get(target,target),
                    json.loads(cell.get('guard')), tuple(json.loads(cell.get('actions')))))
            if cell.get('role') == 'state':
                state = cell.get('logicalState')
                entries[names.get(state,state)] = json.loads(cell.get('entryActions','[]'))
        self.assertEqual(len(transitions), 117)
        self.assertEqual(tuple(transitions), TRANSITIONS)
        self.assertEqual(entries, ENTRY_ACTIONS)

    def test_exact_chain(self):
        r = Lexer().analyze("dim x %\nx := 1E2H\nwriteln x\nend")
        self.assertTrue(r.ok)
        self.assertEqual([(t.table, t.index) for t in r.tokens],
            [(1,1),(3,1),(2,18),(2,21),(3,1),(2,13),(4,1),(2,21),(1,11),(3,1),(2,21),(1,2)])
        self.assertEqual(r.numbers[0].value, 482)

    def test_value_key_and_original_spelling(self):
        r = Lexer().analyze("1 01 1D 1B 1O 1H 1.0 1E0 0.1E1 .10E+1")
        self.assertTrue(r.ok)
        self.assertEqual(len(r.numbers), 1)
        self.assertEqual(r.numbers[0].value, 1)
        self.assertEqual(len(r.numbers[0].spellings), 10)
        self.assertTrue(all(t.index == 1 for t in r.tokens))
        self.assertEqual([t.text for t in r.tokens], "1 01 1D 1B 1O 1H 1.0 1E0 0.1E1 .10E+1".split())

    def test_ambiguous_prefixes(self):
        words = {"11":11,"11B":3,"17":17,"17O":15,"1E2":100,"1E2H":482,
            "1EH":30,"1BH":27,"10DH":269,"1B2H":434,"1E2BH":7723,".5E-2":Fraction(1,200)}
        for word, value in words.items():
            with self.subTest(word=word):
                r = Lexer().analyze(word)
                self.assertTrue(r.ok)
                self.assertEqual(r.numbers[0].value, value)

    def test_malformed_numbers(self):
        for word in ("2B","8O","1E2B","1E+2H","1.","1E+","1.2H","1e--2","12G","12_","."):
            with self.subTest(word=word):
                r = Lexer().analyze("x := " + word)
                self.assertFalse(r.ok)
                self.assertFalse(r.numbers)
                self.assertEqual(r.diagnostics[0].start, 5)

    def test_comments_case_crlf_coordinates(self):
        r = Lexer().analyze("dim\tx %\r\nx:=1{8O @\r\ninside}+2\r\nDim dim1 end")
        self.assertTrue(r.ok)
        self.assertEqual(r.identifiers, ["x", "Dim", "dim1"])
        self.assertEqual(sum(t.text == "\n" for t in r.tokens), 2)
        plus = next(t for t in r.tokens if t.text == "+")
        self.assertEqual((plus.line, plus.column), (3,8))
        for token in r.tokens:
            self.assertEqual(r.source[token.start:token.end], token.text)

    def test_all_static_entries(self):
        r = Lexer().analyze(" ".join(s for s, _ in TW) + "\n" + " ".join(s for s, _ in TL if s != "NL"))
        self.assertTrue(r.ok)
        self.assertEqual({t.index for t in r.tokens if t.table == 1}, set(range(1,16)))
        self.assertEqual({t.index for t in r.tokens if t.table == 2}, set(range(1,22)))

    def test_unclosed_comment_and_unknown_character(self):
        r = Lexer().analyze("x {не закрыт")
        self.assertFalse(r.ok)
        self.assertEqual(r.diagnostics[0].state, "C")
        self.assertEqual(r.diagnostics[0].start, 2)
        r = Lexer().analyze("x\n@")
        self.assertFalse(r.ok)
        self.assertEqual((r.diagnostics[0].line, r.diagnostics[0].column), (2,1))

    def test_no_gc_on_number_completion(self):
        r = Lexer().analyze("1+2")
        self.assertEqual([t.text for t in r.tokens], ["1", "+", "2"])
        finishing = [s for s in r.trace if "number:" in s.actions]
        self.assertTrue(all("gc" not in s.actions for s in finishing))

    def test_generated_bases_against_integer_values(self):
        rng = random.Random(132111)
        for base, suffix, kind in ((2,"B","BIN"),(8,"O","OCT"),(10,"D","DEC_D"),(16,"H","HEX")):
            for _ in range(100):
                digits = "".join(rng.choice("0123456789abcdef"[:base]) for _ in range(rng.randrange(1,30)))
                if base == 16 and digits[0].isalpha(): digits = "0" + digits
                r = Lexer().analyze(digits + suffix)
                self.assertTrue(r.ok)
                self.assertEqual(r.numbers[0].value, int(digits, base))

    def test_exact_fraction_and_rendering(self):
        self.assertEqual(convert_number("000.0500e-1", "REAL"), Fraction(1,200))
        self.assertEqual(convert_number("1E-40", "REAL"), Fraction(1,10**40))
        self.assertEqual(display_value(Fraction(1,200)), "0.005")

    def test_examples(self):
        for path in (Path(__file__).resolve().parents[1] / "examples").glob("*.txt"):
            with self.subTest(file=path.name):
                r = Lexer().analyze(path.read_text(encoding="utf-8-sig"))
                self.assertTrue(r.ok, r.diagnostics)
                for token in r.tokens:
                    self.assertEqual(r.source[token.start:token.end], token.text)

    def test_lexer_is_not_parser(self):
        self.assertTrue(Lexer().analyze("writeln (1+2\nend").ok)


if __name__ == "__main__":
    unittest.main()
