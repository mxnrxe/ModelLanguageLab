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
    while (app.busy or app.executing) and time.monotonic() < deadline:
        app.update()
        time.sleep(.01)
    assert not app.busy and not app.executing
    app.update()


app = LabApp()
try:
    app.update()
    app.editor.set_source('dim a %:readln a:if (a > 5) writeln a + 3 else writeln a:end')
    app.update()
    app.analyze_poliz()
    wait(app)
    assert app.compilation.ok and app.semantic_result.ok and app.syntax_result.ok
    assert app.stage_tabs.select() == str(app.poliz_panel)
    assert len(app.poliz_panel.code.get_children()) == len(app.compilation.code)
    app.poliz_panel.inputs.insert('1.0','7')
    app.run_poliz()
    wait(app)
    assert app.execution.ok and app.execution.output == ['10']
    assert app.poliz_panel.trace.get_children()
    assert app.poliz_panel.output.get('1.0','end').strip() == '10'
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/'poliz.json'
        with patch('ui.app.filedialog.asksaveasfilename', return_value=str(path)):
            app.export()
        data = json.loads(path.read_text(encoding='utf-8'))
        assert data['execution']['output'] == ['10']
        assert data['compilation']['code']
    app.editor.set_source('dim a %:a := true:end')
    app.update()
    assert app.compilation is None and app.execution is None
    assert str(app.poliz_panel.run_button['state']) == 'disabled'
    app.analyze_poliz()
    wait(app)
    assert not app.compilation.ok and not app.compilation.code
    app.show_error()
    assert app.editor.text.tag_ranges('selected_token')
    app.editor.set_source('writeln 1/0:end')
    app.update()
    app.analyze_poliz()
    wait(app)
    app.run_poliz()
    wait(app)
    assert not app.execution.ok and 'Деление на ноль' in app.execution.error
    print('POLIZ UI: single-pass compilation, execution, input, output, diagnostics, export, stale results - OK')
finally:
    app.destroy()
