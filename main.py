
import sys

if hasattr(sys, "set_int_max_str_digits"):
    # Числа языка могут быть длиннее стандартного предела вывода Python.
    sys.set_int_max_str_digits(0)

from ui.app import LabApp

if __name__ == "__main__":
    LabApp().mainloop()
