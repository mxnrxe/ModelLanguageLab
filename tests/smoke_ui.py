"""Интеграционная проверка Tkinter, файлов и привязок к исходному тексту."""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.app import LabApp

app = LabApp()
try:
    app.update()
    app.analyze()
    deadline = time.monotonic() + 10
    while app.busy and time.monotonic() < deadline:
        app.update()
        time.sleep(.02)
    assert not app.busy and app.result.ok
    assert len(app.result.numbers) == 2
    assert len(app.views['tokens'].get_children()) == len(app.result.tokens)
    app.views['TN'].selection_set('0')
    app.select_entry('TN')
    assert len(app.editor.text.tag_ranges('selected_token')) == 8
    app.copy_chain()
    assert app.clipboard_get() == app.result.chain
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'program.txt'
        app.path = path
        assert app.save_file()
        assert 'Сохранено:' in app.status.get() and str(path) in app.status.get()
        assert path.read_text(encoding='utf8') == app.editor.source()
        app.load_path(path)
        app.update()
        app.analyze()
        while app.busy and time.monotonic() < deadline:
            app.update()
            time.sleep(.02)
        exported = Path(directory) / 'result.json'
        with patch('ui.app.filedialog.asksaveasfilename', return_value=str(exported)):
            app.export()
        assert json.loads(exported.read_text(encoding='utf8'))['ok']
        app.saved_source = app.editor.source()
        path.write_bytes('dim x %\r\nx := 8O\r\nend'.encode('cp1251'))
        app.load_path(path)
        app.update()
        app.analyze()
        while app.busy and time.monotonic() < deadline:
            app.update()
            time.sleep(.02)
        assert not app.result.ok
        assert app.editor.text.tag_ranges('error')
        assert not app.views['TN'].get_children()
    app.geometry('1040x720')
    app.update()
    assert app.editor.text.winfo_width() > 250
    assert len(app.tabs.tabs()) == 3
    assert app.chain.winfo_height() >= 100
    delimiter_rows = [app.views['TL'].item(item, 'values') for item in app.views['TL'].get_children()]
    assert delimiter_rows[-1][1] == '/n'
    assert all(row[1] != 'NL' for row in [app.views['tokens'].item(item,'values') for item in app.views['tokens'].get_children()])
    before = app.editor.source()
    app.saved_source = 'different text'
    with patch('ui.app.messagebox.askyesnocancel', return_value=None):
        app.new_file()
    assert app.editor.source() == before
    app.saved_source = app.editor.source()
    app.new_file()
    app.update()
    assert app.editor.source() == '' and app.path is None and app.result is None
    print('Tkinter: анализ, таблицы, выбор TN, цепочка, файлы UTF-8/CP1251, JSON, ошибки — OK')
finally:
    app.destroy()
