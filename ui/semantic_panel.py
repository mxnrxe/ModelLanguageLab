from tkinter import ttk

from language.semantic import TOP


class SemanticPanel(ttk.Frame):
    def __init__(self, parent, show_error):
        super().__init__(parent, style="Card.TFrame", padding=12)
        self.heading = ttk.Label(self, font=("Segoe UI", 16, "bold"), background="white")
        self.heading.pack(anchor="w")
        self.details = ttk.Label(self, background="white", justify="left")
        self.details.pack(fill="x", pady=(5, 8))
        self.go = ttk.Button(self, text="Перейти к ошибке", command=show_error)
        self.go.pack(anchor="w", pady=(0, 8))
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        self.identifiers = self.table(notebook, "Идентификаторы TI",
            (("№", 45), ("Имя", 120), ("Описан", 65), ("Тип", 100), ("Адрес", 65)))
        self.operations = self.table(notebook, "Операции TOP",
            (("Операция", 80), ("Слева", 90), ("Справа", 90), ("Результат", 100)))
        self.stack = self.table(notebook, "Стек выражений",
            (("Шаг", 45), ("Позиция", 65), ("Действие", 220), ("Стек", 140)))
        self.fill(self.operations, ((*key, value) for key, value in TOP.items()))
        self.bind("<Configure>", lambda e: self.details.configure(wraplength=max(180, e.width - 28)))
        self.reset()

    @staticmethod
    def table(notebook, name, columns):
        page = ttk.Frame(notebook)
        notebook.add(page, text=name)
        tree = ttk.Treeview(page, show="headings", columns=[n for n, _ in columns])
        for name, width in columns:
            tree.heading(name, text=name)
            tree.column(name, width=width, minwidth=35)
        scroll = ttk.Scrollbar(page, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(page, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        return tree

    @staticmethod
    def fill(tree, rows):
        tree.delete(*tree.get_children())
        for row in rows:
            tree.insert("", "end", values=row)

    def reset(self, stale=False):
        self.heading.configure(text="Текст изменён" if stale else "Семантический анализ",
                               foreground="#3159a3")
        self.details.configure(text="Нажмите F7 для проверки типов и объявлений.")
        self.go.configure(state="disabled")
        self.fill(self.identifiers, ())
        self.fill(self.stack, ())

    def render(self, result):
        self.fill(self.identifiers, ((i.index, i.name, int(i.declared), i.type or "—", "—")
                                    for i in result.identifiers))
        self.fill(self.stack, ((i, f"{s.line}:{s.column}", s.action, " · ".join(s.stack) or "∅")
                              for i, s in enumerate(result.trace, 1)))
        if result.ok:
            self.heading.configure(text="✓ Семантика верна", foreground="#25796b")
            note = " Журнал ограничен 3000 шагами." if result.trace_truncated else ""
            self.details.configure(text=f"Проверены объявления, выражения и операторы.{note}")
        else:
            d = result.diagnostics[0]
            title = "Семантическая ошибка" if d.phase == "semantic" else "Семантика не проверена"
            self.heading.configure(text=title, foreground="#b64254")
            self.details.configure(text=f"{d.line}:{d.column} · {d.message}")
        self.go.configure(state="disabled" if result.ok else "normal")
