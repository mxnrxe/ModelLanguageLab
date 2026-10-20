"""Настоящее окно Tk: F6, общий редактор, диагностика, файлы и экспорт."""
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.app import LabApp


def wait(app):
    deadline = time.monotonic() + 10
    while app.busy and time.monotonic() < deadline:
        app.update()
        time.sleep(.01)
    assert not app.busy, "Analysis timed out"
    app.update()


app = LabApp()
try:
    app.update()
    app.analyze_syntax()
    wait(app)
    assert app.result.ok and app.syntax_result.ok
    assert app.stage_tabs.select() == str(app.syntax_panel)
    assert len(app.stage_tabs.tabs()) == 2 and len(app.tabs.tabs()) == 3
    assert str(app.syntax_panel.go['state']) == 'disabled'
    text = app.editor.source()
    app.stage_tabs.select(0)
    assert app.editor.source() == text
    app.stage_tabs.select(app.syntax_panel)
    with tempfile.TemporaryDirectory() as folder:
        exported = Path(folder) / 'syntax.json'
        with patch('ui.app.filedialog.asksaveasfilename', return_value=str(exported)):
            app.export()
        data = json.loads(exported.read_text(encoding='utf-8'))
        assert data['phase'] == 'syntax' and data['ok']

        app.editor.set_source('dim q %\nq := (1 + )\nend')
        app.update()
        assert app.syntax_result is None
        app.analyze_syntax()
        wait(app)
        assert app.result.ok and not app.syntax_result.ok
        d = app.syntax_result.diagnostics[0]
        assert d.rule == 'Mn' and d.line == 2
        assert app.editor.text.tag_ranges('error')
        app.syntax_panel.go.invoke()
        assert app.editor.text.tag_ranges('selected_token')
        assert app.editor.text.index('selected_token.first') == f'2.{d.column - 1}'
        with patch('ui.app.filedialog.asksaveasfilename', return_value=str(exported)):
            app.export()
        assert not json.loads(exported.read_text(encoding='utf-8'))['ok']

        path = Path(folder) / 'source.txt'
        app.path = path
        assert app.save_file()
        assert path.read_text(encoding='utf-8') == app.editor.source()
        app.load_path(path)
        app.update()
        assert app.syntax_result is None

        app.editor.set_source('x := 8O:end')
        app.update()
        app.analyze_syntax()
        wait(app)
        assert app.syntax_result.diagnostics[0].phase == 'lexical'

        # Результат фонового анализа другого текста не должен попасть в окно.
        app.editor.set_source('x := 1:end')
        app.update()
        app.analyze_syntax()
        app.editor.set_source('x := +:end')
        app.update()
        wait(app)
        assert app.syntax_result is None
        assert not app._fresh()
        app.analyze_syntax()
        wait(app)
        assert not app.syntax_result.ok

        app.analyze()
        wait(app)
        assert app.result.ok and app.syntax_result is None
        assert app.stage_tabs.index(app.stage_tabs.select()) == 0
        app.saved_source = app.editor.source()
        app.new_file()
        app.update()
        assert app.result is None and app.syntax_result is None

    print('Syntax UI: shared editor, F6, diagnostics, highlight, stale results, save, JSON, lexical gate — OK')
finally:
    app.destroy()
