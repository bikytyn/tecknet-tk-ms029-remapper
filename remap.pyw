"""Tecknet Remap – remaps the side buttons and thumb wheel of the Tecknet TK-MS029 mouse.

Dva procesy:
  pythonw remap.pyw            jádro na pozadí (hook myši, Raw Input, ikona v oznamovací oblasti) – bez okna
  pythonw remap.pyw --show     jádro + otevře nastavení
  pythonw remap.pyw --gui      okno nastavení (samostatný proces; spouští ho jádro)
  --v4 / --v3 / --v2 / --classic   starší okna (jádro ve stejném procesu jako okno)
"""
import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import engine  # noqa: E402

k32 = ctypes.windll.kernel32


def single_instance(name, wait):
    """Vrátí handle mutexu, nebo None, když už instance běží (po případném čekání při restartu)."""
    deadline = time.time() + wait
    while True:
        m = k32.CreateMutexW(None, False, name)
        if k32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
            return m
        k32.CloseHandle(m)
        if time.time() >= deadline:
            return None
        time.sleep(0.2)


def common_setup():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    try:  # vlastní identita na hlavním panelu (jinak Windows ukáže ikonu Pythonu)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Tecknet.Remap")
    except Exception:
        pass


def bring_gui_to_front():
    u = ctypes.windll.user32
    h = u.FindWindowW("TkTopLevel", "Tecknet Remap")
    if h:
        u.ShowWindow(h, 9)  # SW_RESTORE
        u.SetForegroundWindow(h)


if __name__ == "__main__":
    legacy = next((a for a in ("--v4", "--v3", "--v2", "--classic") if a in sys.argv), None)
    if "--gui" in sys.argv:
        # ---- okno nastavení
        mutex = single_instance(engine.GUI_MUTEX, 8 if "--restart" in sys.argv else 0)
        if mutex is None:
            bring_gui_to_front()
            sys.exit(0)
        common_setup()
        from gui5 import App
        App().run(show=True)
    elif legacy:
        # ---- starší varianta: jádro i okno v jednom procesu
        if single_instance("Local\\TecknetRemap", 0) is None:
            engine.signal_running_instance()
            sys.exit(0)
        common_setup()
        mod = {"--v4": "gui4", "--v3": "gui3", "--v2": "gui2", "--classic": "gui"}[legacy]
        App = __import__(mod).App
        App().run(show=True)
    else:
        # ---- jádro na pozadí
        if single_instance("Local\\TecknetRemap", 8 if "--restart" in sys.argv else 0) is None:
            engine.signal_running_instance()  # už běží -> otevře nastavení
            sys.exit(0)
        common_setup()
        first_run = not os.path.exists(__import__("config").CFG_PATH)
        engine.run_standalone(open_gui="--show" in sys.argv or first_run)
