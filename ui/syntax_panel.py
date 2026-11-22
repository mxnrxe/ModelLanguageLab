"""Вкладка результата синтаксической проверки; вычислений здесь нет."""
import tkinter as tk
from tkinter import ttk


RULE_NAMES = {
    "Pr": "Программа", "StL": "Последовательность конструкций", "Sep": "Разделитель",
    "Dc": "Описание переменных", "IdL": "Список идентификаторов", "Tp": "Тип",
    "St": "Оператор", "Cmp": "Составной оператор", "CmpL": "Продолжение блока",
    "Asg": "Присваивание", "Cond": "Условный оператор", "ForSt": "Цикл for",
    "WhileSt": "Цикл while", "ExL": "Список выражений", "Ex": "Выражение",
    "Op": "Операнд", "Sl": "Слагаемое", "Mn": "Множитель", "Lg": "Логическая константа",
    "Id": "Идентификатор", "Nb": "Число", "Rel": "Операция отношения",
    "Add": "Операция группы сложения", "Mul": "Операция группы умножения",
}


class SyntaxPanel(ttk.Frame):
    def __init__(self, parent, show_error):
        super().__init__(parent, style="Card.TFrame", padding=20)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self.heading = ttk.Label(self, text="Проверьте структуру программы",
                                 font=("Segoe UI", 18, "bold"), background="white",
                                 foreground="#3159a3", wraplength=560)
        self.heading.grid(row=0, column=0, sticky="w", pady=(4, 12))
        self.summary = ttk.Label(self, text="F6 — синтаксический анализ", background="white",
                                font=("Segoe UI", 11), wraplength=560)
        self.summary.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        self.go = ttk.Button(self, text="Перейти к ошибке в коде", command=show_error, state="disabled")
        self.go.grid(row=2, column=0, sticky="w", pady=(0, 16))
        frame = ttk.Frame(self, style="Card.TFrame")
        frame.grid(row=3, column=0, sticky="nsew")
        self.details = tk.Text(frame, width=1, height=10, wrap="word", font=("Segoe UI", 11),
                               bg="#f5f8fe", fg="#33415b", relief="flat", padx=16, pady=16,
                               spacing3=9, state="disabled", cursor="arrow")
        self.details.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(frame, command=self.details.yview)
        scroll.pack(side="right", fill="y")
        self.details.configure(yscrollcommand=scroll.set)
        self.bind("<Configure>", lambda e: self._resize(e.width))
        self.reset()

    def _resize(self, width):
        for label in (self.heading, self.summary):
            label.configure(wraplength=max(180, width - 44))

    def write(self, text):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def reset(self):
        self.heading.configure(text="Проверьте структуру программы", foreground="#3159a3")
        self.summary.configure(text="Редактор и файлы общие для всех этапов. Нажмите F6.")
        self.go.configure(state="disabled")
        self.write("Проверка методом рекурсивного спуска\n"
                   "Анализатор получает цепочку лексем и проверяет конструкции по грамматике ЛР1. "
                   "При первой ошибке разбор останавливается.\n"
                   "Важные правила записи\n"
                   "• После каждой конструкции верхнего уровня нужен : или /n, в том числе перед end.\n"
                   "• Внутри [ ] разделитель ставится между операторами, а не перед ].\n"
                   "• Пустые строки — тоже /n. Грамматика не разрешает пропускать их произвольно.\n"
                   "• end — последняя лексема; перенос строки после него не допускается.")

    def stale(self):
        self.heading.configure(text="Текст изменён", foreground="#8b6527")
        self.summary.configure(text="Предыдущая проверка устарела. Нажмите F6 для нового результата.")
        self.go.configure(state="disabled")
        self.write("Результат проверки относится только к той версии текста, на которой она запущена.")

    def render(self, result, source):
        if result.ok:
            self.heading.configure(text="✓ Синтаксис верен", foreground="#25796b")
            self.summary.configure(text=f"Программа соответствует грамматике. Проверено лексем: {result.total}.")
            self.go.configure(state="disabled")
            self.write("Лексический анализ: успешно.\n"
                       "Синтаксический анализ: успешно.\n"
                       "Вся цепочка разобрана от Pr до завершающего end. Лишних лексем нет.")
            return
        d = result.diagnostics[0]
        if d.phase == 'semantic':
            self.heading.configure(text='Разбор остановлен', foreground='#b64254')
            self.summary.configure(text=f'Семантическая ошибка {d.line}:{d.column}. Оставшаяся часть программы не проверена.')
            self.go.configure(state='normal')
            self.write(d.message)
            return
        lexical = d.phase == "lexical"
        limit = d.phase == "limit"
        title = "Предел анализатора" if limit else "Ошибка лексики" if lexical else "Ошибка синтаксиса"
        self.heading.configure(text=title, foreground="#b64254")
        self.summary.configure(text=f"Строка {d.line}, столбец {d.column}. " +
                               ("Синтаксическая правильность не установлена." if limit else
                                "Сначала исправьте лексическую ошибку." if lexical else
                                "Разбор остановлен на первой ошибке."))
        self.go.configure(state="normal")
        lines = source.split("\n")
        line = lines[d.line - 1] if d.line <= len(lines) else ""
        rule = f"{RULE_NAMES[d.rule]} ({d.rule})" if d.rule in RULE_NAMES else d.rule
        self.write(f"{d.message}\n"
                   f"Конструкция: {rule}\n"
                   f"Исходная строка {d.line}:\n{line}\n\n"
                   "Исправьте выделенное место и запустите проверку ещё раз (F6).")
