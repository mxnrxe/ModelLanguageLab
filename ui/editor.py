"""Редактор; подсветка — только оформление, не лексический анализ."""
import re
import tkinter as tk
from tkinter import ttk
from language.tables import TW


class CodeEditor(ttk.Frame):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        self.on_change = on_change
        self._pending = None
        self.gutter = tk.Canvas(self, width=48, bg="#e5ebf5", highlightthickness=0)
        self.gutter.grid(row=0, column=0, sticky="ns")
        self.text = tk.Text(self, undo=True, maxundo=200, wrap="none", width=1, height=1, font=("Consolas", 12),
            bg="#f8faff", fg="#24304a", insertbackground="#4669dd", selectbackground="#dce6ff",
            relief="flat", padx=14, pady=12, tabs=(32,), spacing1=3, spacing3=3)
        self.text.grid(row=0, column=1, sticky="nsew")
        vertical = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        vertical.grid(row=0, column=2, sticky="ns")
        horizontal = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        horizontal.grid(row=1, column=1, sticky="ew")
        self.text.configure(xscrollcommand=horizontal.set, yscrollcommand=lambda a, b: (vertical.set(a, b), self.redraw()))
        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        for tag, color in (("keyword", "#6d4dc2"), ("number", "#18827d"),
                           ("comment", "#8a96a6"), ("delimiter", "#62749a")):
            self.text.tag_configure(tag, foreground=color)
        self.text.tag_configure("error", background="#ffe1e4", underline=True)
        self.text.tag_configure("selected_token", background="#dce6ff")
        self.text.bind("<<Modified>>", self.modified)
        self.text.bind("<Configure>", lambda _: self.redraw())
        self.text.bind("<KeyRelease>", lambda _: self.redraw())
        self.text.bind("<Tab>", lambda _: (self.text.insert("insert", "    "), "break")[-1])
        self.text.bind("<Control-a>", self.select_all)
        menu = tk.Menu(self, tearoff=False)
        for title, event in (("Отменить", "<<Undo>>"), ("Повторить", "<<Redo>>"),
                             ("Вырезать", "<<Cut>>"), ("Копировать", "<<Copy>>"), ("Вставить", "<<Paste>>")):
            menu.add_command(label=title, command=lambda e=event: self.text.event_generate(e))
        self.text.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    def select_all(self, _=None):
        self.text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def modified(self, _=None):
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        self.text.tag_remove("error", "1.0", "end")
        self.text.tag_remove("selected_token", "1.0", "end")
        self.on_change()
        if self._pending:
            self.after_cancel(self._pending)
        self._pending = self.after(140, self.highlight)

    def set_source(self, text):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text.replace("\r\n", "\n").replace("\r", "\n"))
        self.text.edit_reset()
        self.highlight()
        self.redraw()

    def source(self):
        return self.text.get("1.0", "end-1c")

    def highlight(self):
        self._pending = None
        source = self.source()
        for tag in ("keyword", "number", "comment", "delimiter"):
            self.text.tag_remove(tag, "1.0", "end")
        keywords = {s for s, _ in TW}
        # Один проход по фрагментам: комментарий всегда имеет приоритет.
        pattern = r"\{[^}]*\}?|[A-Za-z][A-Za-z0-9]*|[0-9][0-9A-Fa-f]*[Hh]|(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+|[BbOoDd])?|[:<>]=|<>|[+*/=\-:,()%!$\[\]]"
        for match in re.finditer(pattern, source):
            word = match.group()
            if word.startswith("{"): tag = "comment"
            elif word in keywords: tag = "keyword"
            elif word[0].isdigit() or word.startswith("."): tag = "number"
            elif not word[0].isalpha(): tag = "delimiter"
            else: continue
            self.mark(tag, match.start(), match.end())
        self.text.tag_raise("error")
        self.redraw()

    def mark(self, tag, start, end):
        self.text.tag_add(tag, f"1.0+{start}c", f"1.0+{max(start + 1, end)}c")

    def select_span(self, start, end):
        self.text.tag_remove("selected_token", "1.0", "end")
        self.mark("selected_token", start, end)
        self.text.see(f"1.0+{start}c")

    def redraw(self):
        self.gutter.delete("all")
        index = self.text.index("@0,0")
        while True:
            info = self.text.dlineinfo(index)
            if info is None: break
            self.gutter.create_text(36, info[1] + 2, anchor="ne", text=index.split(".")[0],
                font=("Consolas", 10), fill="#a0a9bb")
            index = self.text.index(f"{index}+1line")
