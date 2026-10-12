"""Проверка исполняемого if/elif против переходов итогового XML."""
import ast
import copy
import dataclasses
import unittest
from pathlib import Path
from collections import defaultdict
from language.lexer import Lexer, EOF
from language.models import TraceStep
from xml_oracle import XmlOracle, TRANSITIONS, ENTRY_ACTIONS

byq=defaultdict(list)
for e in TRANSITIONS:byq[e[1]].append(e)
def snap(r):
 return {'ok':r.ok,'tokens':[dataclasses.asdict(t) for t in r.tokens],'TI':r.identifiers,'TN':[dataclasses.asdict(t) for t in r.numbers],'diagnostics':[dataclasses.asdict(d) for d in r.diagnostics],'trace':[dataclasses.asdict(t) for t in r.trace]}
def state(l):
 return {**snap(l.result),**{k:getattr(l,k) for k in ('CS','CH','S','B','z','pos','start','line','column','start_line','start_column','_ti','_tn')}}

class ScannerIfTests(unittest.TestCase):
    def test_every_transition_and_character_class(self):
        seed={'N2':'1','N8':'7','N10':'9','P2':'1B','P8':'7O','P16':'1H','U10':'1D','N16':'1A','Exp':'1E','T':'.','E1':'.1','EX':'.1E','E2':'.1E1','E3':'.1E+','E4':'.1E+1','PP':'1E1','NK':'1E12','TT':'1E+','Mn':'1E+1'}
        alphabet=[chr(i) for i in range(256)]+[EOF,'я','☃'];covered=set();count=0
        for q in byq:
         for ch in alphabet:
          for z in (0,1):
           prefix=seed.get(q, 'name' if q=='I' else 'dim' if q=='KW' and z else 'id' if q=='KW' else '+' if q=='OP' and z else '@' if q=='OP' else '{' if q=='C' else '')
           source=prefix+('' if ch==EOF else ch)
           a=Lexer();a._reset(source,True)
           a.CS=q;a.CH=ch;a.pos=len(prefix);a.column=len(prefix)+1;a.z=z;a.B=seed.get(q,'');a.S=prefix
           b=XmlOracle();b.__dict__=copy.deepcopy(a.__dict__)
           matches=[e for e in byq[q] if b._guard(e[3])];assert len(matches)==1,(q,ch,z,matches)
           id,prev,target,_,acts=matches[0]
           if prev=='H' and target!='H':b.start,b.start_line,b.start_column=b.pos,b.line,b.column
           incoming=ENTRY_ACTIONS.get(target,[])
           b.result.trace.append(TraceStep(id,prev,target,ch,b.line,b.column,', '.join(list(acts)+incoming)))
           for act in acts:b._action(act,id)
           b.CS=target
           for act in incoming:b._action(act,id)
           a.scanner();assert state(a)==state(b),('step',q,ch,z,state(a),state(b))
           covered.add(id);count+=1
        assert covered=={e[0] for e in TRANSITIONS}
        self.assertEqual(count, 14504)
        self.assertEqual(len(covered), 117)

    def test_scanner_uses_explicit_state_branches(self):
        source = (Path(__file__).resolve().parents[1] / "language/lexer.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "scanner")
        ids = [n.args[0].value for n in ast.walk(method) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == "_record"]
        self.assertEqual(set(ids), {e[0] for e in TRANSITIONS})
        self.assertEqual(len(ids), 117)
        self.assertNotIn("TRANSITIONS", source)
        self.assertNotIn("ENTRY_ACTIONS", source)
        self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("_guard", "_action") for n in ast.walk(method)))

    def test_new_numeric_states_are_executed(self):
        for text, states in (("1E1", {"Exp", "PP"}), ("1E12", {"PP", "NK"}),
                ("1.1E1", {"EX", "E2"}), ("1.1E-1", {"EX", "E3", "E4"})):
            with self.subTest(text=text):
                result = Lexer().analyze(text)
                self.assertTrue(result.ok)
                self.assertTrue(states <= {t.target for t in result.trace})

    def test_resource_errors_and_disabled_trace(self):
        lexer = Lexer()
        result = lexer.analyze("x:=1E10001")
        self.assertFalse(result.ok)
        self.assertIn("предел", result.diagnostics[0].message)
        text = "dim a %\na:=1E2+1E2H\nend"
        a, b = lexer.analyze(text), lexer.analyze(text, trace=False)
        self.assertEqual(a.tokens, b.tokens)
        self.assertEqual(a.identifiers, b.identifiers)
        self.assertEqual(a.numbers, b.numbers)
        self.assertFalse(b.trace)

if __name__ == "__main__":
    unittest.main()
