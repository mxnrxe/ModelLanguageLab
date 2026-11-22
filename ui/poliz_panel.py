import tkinter as tk
from tkinter import ttk
from .semantic_panel import SemanticPanel


class PolizPanel(ttk.Frame):
    def __init__(self, parent, run, show_error):
        super().__init__(parent, padding=10)
        self.status = ttk.Label(self, text='F8 - единый разбор и построение ПОЛИЗ', wraplength=650)
        self.status.pack(fill='x', pady=(0, 8))
        bar = ttk.Frame(self)
        bar.pack(fill='x')
        self.run_button = ttk.Button(bar, text='▶ Выполнить  F9', style='Accent.TButton',
                                     command=run, state='disabled')
        self.run_button.pack(side='left')
        ttk.Button(bar, text='К ошибке', command=show_error).pack(side='left', padx=4)
        ttk.Label(bar, text='Ctrl+Enter - выполнить из поля ввода').pack(side='right')
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, pady=8)
        self.console = ttk.Frame(self.notebook)
        self.notebook.add(self.console, text='Ввод и вывод')
        self.panes = ttk.Panedwindow(self.console, orient='vertical')
        self.panes.pack(fill='both', expand=True)
        input_card = ttk.Frame(self.panes, padding=12, style='Card.TFrame')
        output_card = ttk.Frame(self.panes, padding=12, style='Card.TFrame')
        self.panes.add(input_card, weight=1)
        self.panes.add(output_card, weight=3)
        self.inputs = self.text_card(input_card, 'Входные данные', height=4, editable=True)
        self.inputs.bind('<Control-Return>', lambda _: (run(), 'break')[1])
        ttk.Label(input_card, text='Вводите значения по порядку readln: каждое с новой строки или через пробел.',
                  background='white', wraplength=600).pack(anchor='w', pady=(8, 0))
        self.output = self.text_card(output_card, 'Результат выполнения', height=12, editable=False)
        self.output.tag_configure('error', foreground='#af3046')
        footer = ttk.Frame(output_card, style='Card.TFrame')
        footer.pack(fill='x', pady=(8, 0))
        ttk.Button(footer, text='Скопировать вывод', command=self.copy_output).pack(side='left')
        ttk.Button(footer, text='Очистить вывод', command=lambda: self.write('')).pack(side='left', padx=6)
        self.code = SemanticPanel.table(self.notebook, 'ПОЛИЗ',
            (('№', 50), ('Пара', 85), ('Элемент', 140), ('Позиция', 80)))
        self.trace = SemanticPanel.table(self.notebook, 'Ход выполнения',
            (('Шаг', 45), ('Команда', 70), ('Элемент', 70), ('Стек после', 160),
             ('Память после', 220), ('Вывод', 100)))
        self.bind('<Configure>', lambda e: self.status.configure(wraplength=max(200, e.width - 25)))

    @staticmethod
    def text_card(parent, heading, height, editable):
        header = ttk.Frame(parent, style='Card.TFrame')
        header.pack(fill='x', pady=(0, 8))
        ttk.Label(header, text=heading, font=('Segoe UI', 12, 'bold'),
                  background='white', foreground='#263e67').pack(side='left')
        holder = ttk.Frame(parent)
        holder.pack(fill='both', expand=True)
        text = tk.Text(holder, width=1, height=height, wrap='word', undo=editable,
                       font=('Consolas', 14), bg='#f3f6fc', fg='#23334d',
                       insertbackground='#23334d', relief='flat', padx=14, pady=12,
                       spacing1=2, spacing3=4, selectbackground='#cbdcff',
                       state='normal' if editable else 'disabled')
        text.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(holder, command=text.yview)
        scrollbar.pack(side='right', fill='y')
        text.configure(yscrollcommand=scrollbar.set)
        if editable:
            ttk.Button(header, text='Очистить ввод',
                       command=lambda: text.delete('1.0', 'end')).pack(side='right')
        return text

    def copy_output(self):
        text = self.output.get('1.0', 'end-1c')
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)

    def input_values(self):
        return self.inputs.get('1.0', 'end-1c').split()

    def write(self, text):
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', text)
        self.output.configure(state='disabled')

    def reset(self):
        self.run_button.configure(state='disabled')
        self.status.configure(text='Результат не построен. Нажмите F8.')
        SemanticPanel.fill(self.code, ())
        SemanticPanel.fill(self.trace, ())
        self.write('')

    def render(self, result):
        self.reset()
        if not result.ok:
            d = result.diagnostics[0]
            self.status.configure(text=f'{d.phase}: {d.line}:{d.column} - {d.message}')
            return
        self.status.configure(text=f'Трансляция завершена: {len(result.code)} элементов. Входные данные задаются на вкладке «Ввод и вывод».')
        SemanticPanel.fill(self.code, ((i, t.pair, t.text, f'{t.line}:{t.column}')
                                      for i, t in enumerate(result.code, 1)))
        self.run_button.configure(state='normal')

    def render_execution(self, result):
        SemanticPanel.fill(self.trace, ((i, s.pc, s.item, ' · '.join(s.stack) or '∅', s.memory, s.output)
                                       for i, s in enumerate(result.trace, 1)))
        self.write('\n'.join(result.output) + ('\nОшибка: ' + result.error if result.error else ''))
        if result.error:
            self.output.tag_add('error', f'{len(result.output) + 1}.0', 'end')
        self.notebook.select(self.console)
        self.status.configure(text=('Выполнение завершено.' if result.ok else result.error) +
                              (' Журнал ограничен 3000 шагами.' if result.trace_truncated else ''))
