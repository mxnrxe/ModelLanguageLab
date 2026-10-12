"""Светлый интерфейс Tkinter. Все вычисления вынесены в language."""
import json
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from language.lexer import Lexer
from language.tables import TW, TL
from language.numbers import display_value
from .editor import CodeEditor

ROOT = Path(__file__).resolve().parents[1]
DEMO = """{Пример: разные записи одного значения}
dim x, y %
dim rate !
x := 101B: y := 5
rate := .5E-2
writeln x, y, rate, 5H, 005D
end"""
KINDS = {"BIN": "Двоичное", "OCT": "Восьмеричное", "DEC": "Десятичное",
         "DEC_D": "Десятичное D", "HEX": "Шестнадцатеричное", "REAL": "Действительное"}


class LabApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Model Studio — редактор языка")
        self.geometry("1600x1000")
        self.minsize(1100, 760)
        self.configure(bg="#f3f6fc")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.path = None
        self.saved_source = DEMO
        self.result = None
        self.version = 0
        self.busy = False
        self.messages = queue.Queue()
        self._style()
        self._build()
        self.editor.set_source(DEMO)
        self.after(120, self._maximize)
        self.bind("<Control-n>", lambda _: self.new_file())
        self.bind("<Control-o>", lambda _: self.open_file())
        self.bind("<Control-s>", lambda _: self.save_file())
        self.bind("<Control-Shift-S>", lambda _: self.save_file(True))
        self.bind("<F5>", lambda _: self.analyze())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self._poll)

    def _maximize(self):
        try:
            self.state("zoomed")
        except tk.TclError:
            self.geometry(f"{int(self.winfo_screenwidth() * .9)}x{int(self.winfo_screenheight() * .85)}")
        self.after(100, self._size_panes)

    def _size_panes(self):
        self.panes.sashpos(0, int(self.panes.winfo_width() * .38))
        self.body.sashpos(0, max(300, self.body.winfo_height() - 230))

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame", background="#edf2f8")
        s.configure("Card.TFrame", background="#ffffff")
        s.configure("Header.TFrame", background="#202d49")
        s.configure("TLabel", background="#edf2f8", foreground="#28344d", font=("Segoe UI", 10))
        s.configure("Brand.TLabel", background="#202d49", foreground="#f4f7ff", font=("Segoe UI", 19, "bold"))
        s.configure("Header.TLabel", background="#202d49", foreground="#b6c7e6", font=("Segoe UI", 10))
        s.configure("CardTitle.TLabel", background="#e7eefb", foreground="#3159a3", font=("Segoe UI", 10, "bold"), padding=(12, 9))
        s.configure("TealTitle.TLabel", background="#e2f3ef", foreground="#25796b", font=("Segoe UI", 10, "bold"), padding=(12, 9))
        s.configure("Muted.TLabel", foreground="#738099")
        s.configure("TButton", font=("Segoe UI", 10), padding=(14, 9), background="#ffffff", borderwidth=0)
        s.map("TButton", background=[("active", "#dce7fa")])
        s.configure("Accent.TButton", background="#3867da", foreground="white", font=("Segoe UI", 10, "bold"))
        s.map("Accent.TButton", background=[("active", "#2c53b3"), ("disabled", "#a0add8")])
        s.configure("TNotebook", background="#edf2f8", borderwidth=0)
        s.configure("TNotebook.Tab", padding=(15, 9), background="#dde6f5", font=("Segoe UI", 10))
        s.map("TNotebook.Tab", background=[("selected", "#ffffff")], foreground=[("selected", "#3867da")])
        s.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground="#33415b",
            rowheight=29, font=("Segoe UI", 10), borderwidth=0)
        s.configure("Treeview.Heading", background="#eef3fb", foreground="#587094",
            font=("Segoe UI", 9, "bold"), padding=(8, 8), relief="flat")
        s.map("Treeview", background=[("selected", "#d6e5ff")], foreground=[("selected", "#253e85")])

    def _card(self, parent, title, key, columns, teal=False):
        card = ttk.Frame(parent, style="Card.TFrame")
        ttk.Label(card, text=title, style="TealTitle.TLabel" if teal else "CardTitle.TLabel").pack(fill="x")
        table_frame = ttk.Frame(card, style="Card.TFrame")
        table_frame.pack(fill="both", expand=True)
        self.views[key] = self.make_table(table_frame, columns)
        return card

    def _build(self):
        header = ttk.Frame(self, style="Header.TFrame", padding=(22, 12))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="</>  Model Studio", style="Brand.TLabel").pack(side="left")
        ttk.Label(header, text="РЕДАКТОР  /  АНАЛИЗ ЯЗЫКА", style="Header.TLabel").pack(side="right")
        tools = ttk.Frame(self, padding=(18, 12))
        tools.grid(row=1, column=0, sticky="ew")
        for label, command in (("＋ Новый", self.new_file), ("Открыть", self.open_file),
                               ("Сохранить", self.save_file), ("Сохранить как…", lambda: self.save_file(True)),
                               ("Примеры", self.show_examples), ("Экспорт", self.export)):
            ttk.Button(tools, text=label, command=command).pack(side="left", padx=(0, 7))
        self.run_button = ttk.Button(tools, text="▶  Лексический анализ   F5", style="Accent.TButton", command=self.analyze)
        self.run_button.pack(side="right")
        self.body = ttk.Panedwindow(self, orient="vertical")
        self.body.grid(row=2, column=0, sticky="nsew", padx=18)
        workspace = ttk.Frame(self.body)
        chain_panel = ttk.Frame(self.body)
        self.body.add(workspace, weight=4)
        self.body.add(chain_panel, weight=1)
        self.panes = ttk.Panedwindow(workspace, orient="horizontal")
        self.panes.pack(fill="both", expand=True)
        left = ttk.Frame(self.panes, style="Card.TFrame")
        right = ttk.Frame(self.panes)
        self.panes.add(left, weight=4)
        self.panes.add(right, weight=6)
        self.filename = tk.StringVar(value="Новый файл")
        ttk.Label(left, text="ИСХОДНЫЙ КОД", style="CardTitle.TLabel").pack(fill="x")
        ttk.Label(left, textvariable=self.filename, padding=(12, 7), style="Muted.TLabel").pack(fill="x")
        self.editor = CodeEditor(left, self.changed)
        self.editor.pack(fill="both", expand=True)
        self.views = {}
        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill="both", expand=True, padx=(8, 0))
        overview = ttk.Frame(self.tabs)
        statics = ttk.Frame(self.tabs)
        trace = ttk.Frame(self.tabs)
        self.tabs.add(overview, text="Таблицы лексем")
        self.tabs.add(statics, text="Слова и ограничители")
        self.tabs.add(trace, text="Журнал переходов")
        overview.rowconfigure(0, weight=1)
        overview.rowconfigure(1, weight=1)
        overview.columnconfigure(0, weight=5)
        overview.columnconfigure(1, weight=6)
        self._card(overview, "ТАБЛИЦА ЛЕКСЕМ", "tokens", [("#",40),("Написание",100),("Пара",80),("Позиция",85)]).grid(row=0,column=0,rowspan=2,sticky="nsew",padx=(0,8))
        self._card(overview, "3 · ИДЕНТИФИКАТОРЫ — TI", "TI", [("Индекс",60),("Идентификатор",160)], True).grid(row=0,column=1,sticky="nsew",pady=(0,8))
        self._card(overview, "4 · ЧИСЛА — TN", "TN", [("Индекс",50),("Значение",85),("Записи",150),("Виды",115)], True).grid(row=1,column=1,sticky="nsew")
        statics.rowconfigure(0,weight=1)
        for col in (0,1): statics.columnconfigure(col,weight=1)
        self._card(statics, "1 · ЗАРЕЗЕРВИРОВАННЫЕ СЛОВА — TW", "TW", [("Индекс",50),("Слово",90),("Назначение",170)]).grid(row=0,column=0,sticky="nsew",padx=(0,8))
        self._card(statics, "2 · ОГРАНИЧИТЕЛИ — TL", "TL", [("Индекс",50),("Запись",65),("Назначение",180)]).grid(row=0,column=1,sticky="nsew")
        self._card(trace, "ПЕРЕХОДЫ АВТОМАТА", "trace", [("Дуга",60),("Из",65),("В",65),("CH",75),("Действия",220)]).pack(fill="both",expand=True)
        self.views["tokens"].bind("<<TreeviewSelect>>", self.select_token)
        for key in ("TI", "TN"):
            self.views[key].bind("<<TreeviewSelect>>", lambda e, k=key: self.select_entry(k))
        self.views["trace"].bind("<<TreeviewSelect>>", self.select_trace)
        for key, table in (("TW", TW), ("TL", TL)):
            for i, (word, meaning) in enumerate(table, 1):
                self.views[key].insert("", "end", values=(i, "/n" if word == "NL" else word, meaning))
        bottom = ttk.Frame(chain_panel, padding=(0, 9, 0, 5))
        bottom.pack(fill="x")
        ttk.Label(bottom, text="ВЫХОДНАЯ ЦЕПОЧКА ЛЕКСЕМ", style="Muted.TLabel").pack(side="left")
        ttk.Button(bottom, text="Копировать цепочку", command=self.copy_chain).pack(side="right")
        chain_frame = ttk.Frame(chain_panel)
        chain_frame.pack(fill="both",expand=True)
        self.chain = tk.Text(chain_frame, height=8, width=1, wrap="word", font=("Consolas", 12), bg="#e5edfc",
            fg="#294b91", relief="flat", padx=14, pady=12, spacing1=4, spacing3=4, state="disabled")
        self.chain.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(chain_frame, command=self.chain.yview)
        sb.pack(side="right", fill="y")
        self.chain.configure(yscrollcommand=sb.set)
        self.status = tk.StringVar(value="Готов к работе · Ctrl+N — новый файл · F5 — лексический анализ")
        self.status_label = ttk.Label(self, textvariable=self.status, padding=(18, 9))
        self.status_label.grid(row=3, column=0, sticky="ew")
        self.status_label.bind("<Button-1>", lambda _: self.show_error())

    def new_file(self):
        if not self._confirm_replace():
            return
        self.path = None
        self.saved_source = ""
        self.editor.set_source("")
        self.editor.text.edit_modified(False)
        self.clear_result()
        self._update_filename()
        self.status.set("Новый файл создан. Ctrl+S — выбрать имя и сохранить.")
        self.editor.text.focus_set()

    def make_table(self, parent, columns):
        keys = [str(i) for i in range(len(columns))]
        tree = ttk.Treeview(parent, columns=keys, show="headings", selectmode="browse")
        for key, (title, width) in zip(keys, columns):
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=45, stretch=key != "0")
        y = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        x = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        tree.tag_configure("even", background="#f7f9fd")
        return tree

    def changed(self):
        self.version += 1
        if hasattr(self, "status"):
            self.status.set("Текст изменён. Нажмите F5 для обновления результатов.")
        self._update_filename()

    def _update_filename(self):
        if hasattr(self, "editor"):
            dirty = self.editor.source() != self.saved_source
            self.filename.set((self.path.name if self.path else "Новый файл") + ("  • изменён" if dirty else ""))

    def _confirm_replace(self):
        if self.editor.source() == self.saved_source: return True
        answer = messagebox.askyesnocancel("Несохранённые изменения", "Сохранить текущую программу?", parent=self)
        if answer is None: return False
        return self.save_file() if answer else True

    def open_file(self):
        name = filedialog.askopenfilename(parent=self, title="Открыть программу", filetypes=[("Исходный текст", "*.txt *.tlp *.src"), ("Все файлы", "*.*")])
        if name: self.load_path(Path(name))

    def load_path(self, path):
        try:
            raw = path.read_bytes()
            if raw.startswith((b"\xff\xfe", b"\xfe\xff")): source = raw.decode("utf-16")
            else:
                try: source = raw.decode("utf-8-sig")
                except UnicodeDecodeError: source = raw.decode("cp1251")
        except (OSError, UnicodeError) as error:
            messagebox.showerror("Не удалось открыть файл", str(error), parent=self)
            return
        if not self._confirm_replace(): return
        self.path = path
        self.saved_source = source.replace("\r\n", "\n").replace("\r", "\n")
        self.editor.set_source(self.saved_source)
        self.clear_result()
        self._update_filename()

    def save_file(self, save_as=False):
        path = self.path
        if save_as or path is None:
            name = filedialog.asksaveasfilename(parent=self, title="Сохранить программу", defaultextension=".txt", filetypes=[("Исходный текст UTF-8", "*.txt")])
            if not name: return False
            path = Path(name)
        try: path.write_text(self.editor.source(), encoding="utf-8")
        except OSError as error:
            messagebox.showerror("Не удалось сохранить", str(error), parent=self)
            return False
        self.path = path
        self.saved_source = self.editor.source()
        self._update_filename()
        self.status.set(f"✓ Сохранено: {path}")
        return True

    def show_examples(self):
        menu = tk.Menu(self, tearoff=False)
        for path in sorted((ROOT / "examples").glob("*.txt")):
            menu.add_command(label=path.stem, command=lambda p=path: self.load_path(p))
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def clear_result(self):
        self.result = None
        for key in ("tokens", "TI", "TN", "trace"):
            tree = self.views[key]
            tree.delete(*tree.get_children())
        self._set_chain("")

    def analyze(self):
        if self.busy: return
        source, version = self.editor.source(), self.version
        self.busy = True
        self.run_button.configure(state="disabled")
        self.status.set("Анализирую программу…")
        def worker():
            try: self.messages.put((version, Lexer().analyze(source), None))
            except Exception as error: self.messages.put((version, None, error))
        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        try:
            version, result, error = self.messages.get_nowait()
            self.busy = False
            self.run_button.configure(state="normal")
            if version != self.version:
                self.status.set("Текст изменился во время анализа. Нажмите F5 ещё раз.")
            elif error:
                self.status.set("Внутренняя ошибка анализатора")
                messagebox.showerror("Ошибка", str(error), parent=self)
            else: self.render_result(result)
        except queue.Empty: pass
        self.after(100, self._poll)

    def render_result(self, result):
        self.clear_result()
        self.result = result
        self.analyzed_version = self.version
        self.editor.text.tag_remove("error", "1.0", "end")
        rows = {
            "tokens": [(i, "/n" if t.text == "\n" else t.text, t.pair, f"{t.line}:{t.column}") for i, t in enumerate(result.tokens, 1)],
            "TI": list(enumerate(result.identifiers, 1)),
            "TN": [(i, display_value(n.value), ", ".join(n.spellings), ", ".join(KINDS[k] for k in n.kinds)) for i, n in enumerate(result.numbers, 1)],
            "trace": [(s.edge, s.source, s.target, "EOF" if s.character == "EOF" else "/n" if s.character == "\n" else repr(s.character), s.actions) for s in result.trace],
        }
        for key, values in rows.items():
            for i, row in enumerate(values):
                self.views[key].insert("", "end", iid=str(i), values=row, tags=("even",) if i % 2 == 0 else ())
        self._set_chain(result.chain)
        if result.ok:
            self.status.set(f"✓ Лексический анализ завершён · {len(result.tokens)} лексем · {len(result.identifiers)} идентификаторов · {len(result.numbers)} значений чисел" + (" · журнал ограничен 100000 переходами" if result.trace_truncated else ""))
        else:
            d = result.diagnostics[0]
            self.editor.mark("error", d.start, d.end)
            self.editor.text.see(f"1.0+{d.start}c")
            self.status.set(f"Ошибка {d.line}:{d.column} · {d.message} · {d.state}, {d.edge} · нажмите для перехода")

    def _fresh(self):
        return self.result is not None and self.analyzed_version == self.version

    def select_token(self, _=None):
        selected = self.views["tokens"].selection()
        if self._fresh() and selected:
            token = self.result.tokens[int(selected[0])]
            self.editor.select_span(token.start, token.end)

    def select_entry(self, key):
        selected = self.views[key].selection()
        if not self._fresh() or not selected: return
        index = int(selected[0]) + 1
        self.editor.text.tag_remove("selected_token", "1.0", "end")
        matching = [t for t in self.result.tokens if t.table == (3 if key == "TI" else 4) and t.index == index]
        for t in matching: self.editor.mark("selected_token", t.start, t.end)
        if matching: self.editor.text.see(f"1.0+{matching[0].start}c")

    def select_trace(self, _=None):
        selected = self.views["trace"].selection()
        if self._fresh() and selected:
            step = self.result.trace[int(selected[0])]
            self.editor.text.see(f"{step.line}.{step.column - 1}")

    def show_error(self):
        if self._fresh() and self.result.diagnostics:
            d = self.result.diagnostics[0]
            self.editor.select_span(d.start, d.end)

    def _set_chain(self, text):
        self.chain.configure(state="normal")
        self.chain.delete("1.0", "end")
        self.chain.insert("1.0", text)
        self.chain.configure(state="disabled")

    def copy_chain(self):
        if not self._fresh():
            self.status.set("Сначала обновите анализ: F5")
            return
        self.clipboard_clear()
        self.clipboard_append(self.result.chain)

    def export(self):
        if not self._fresh():
            messagebox.showinfo("Экспорт", "Сначала выполните анализ текущего текста (F5).", parent=self)
            return
        name = filedialog.asksaveasfilename(parent=self, title="Экспорт результата", defaultextension=".json", filetypes=[("Результат JSON", "*.json"), ("Цепочка лексем", "*.txt")])
        if not name: return
        r = self.result
        data = {"ok": r.ok, "source": r.source, "chain": r.chain, "TW": TW,
            "TL": [("/n" if word == "NL" else word, meaning) for word, meaning in TL],
            "TI": r.identifiers, "TN": [{"index": i, "value": str(n.value), "spellings": n.spellings, "kinds": n.kinds} for i, n in enumerate(r.numbers, 1)],
            "tokens": [vars(t) for t in r.tokens], "diagnostics": [vars(d) for d in r.diagnostics],
            "trace": [vars(t) for t in r.trace], "trace_truncated": r.trace_truncated}
        try:
            Path(name).write_text(r.chain if name.lower().endswith(".txt") else json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as error: messagebox.showerror("Экспорт", str(error), parent=self)

    def close(self):
        if self._confirm_replace(): self.destroy()
