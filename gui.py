"""Okno nastavení (tkinter) – profily podle aplikací, ve stylu Logi Options+."""
import copy
import os
import queue
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import winreg

import config as C
import engine as E

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "TecknetRemap"

ACCENT = "#2F7DE2"
CONTROL_LABEL = dict(C.CONTROLS)


def autostart_cmd():
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(w):
        exe = w
    return f'"{exe}" "{os.path.join(C.APP_DIR, "remap.pyw")}"'


def autostart_get():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
    except OSError:
        return False


def autostart_set(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, autostart_cmd())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass


class ControlRow:
    """Jeden řádek: název ovladače + výběr akce + (případně) pole pro zkratku / program."""

    def __init__(self, app, parent, control, row):
        self.app, self.control = app, control
        ttk.Label(parent, text=CONTROL_LABEL[control], style="Ctl.TLabel").grid(
            row=row * 2, column=0, sticky="w", pady=(14, 2))
        self.var = tk.StringVar()
        self.combo = ttk.Combobox(parent, textvariable=self.var, state="readonly", width=42, height=24)
        self.combo.grid(row=row * 2 + 1, column=0, sticky="we")
        self.combo.bind("<<ComboboxSelected>>", self.on_select)
        self.extra = ttk.Frame(parent)
        self.extra.grid(row=row * 2 + 1, column=1, sticky="we", padx=(10, 0))
        self.evar = tk.StringVar()
        self.entry = ttk.Entry(self.extra, textvariable=self.evar, width=26)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.commit_extra())
        self.entry.bind("<FocusOut>", lambda e: self.commit_extra())
        self.btn = ttk.Button(self.extra, width=9)
        self.btn.pack(side="left", padx=(6, 0))
        self.mode = None
        self.capturing = False

    # -- naplnění podle profilu
    def load(self, exe):
        is_global = exe == C.GLOBAL
        values = ([] if is_global else [C.INHERIT[1]]) + [l for _, l in C.PRESETS] + [C.CUSTOM_KEYS_LABEL, C.RUN_LABEL]
        self.combo["values"] = values
        prof = self.app.cfg["profiles"].get(exe, {})
        action = prof.get(self.control, "default" if is_global else "inherit")
        if action == "inherit":
            self.var.set(C.INHERIT[1])
            self.set_mode(None)
        elif action in C.PRESET_LABEL:
            self.var.set(C.PRESET_LABEL[action])
            self.set_mode(None)
        elif action.startswith("keys:"):
            self.var.set(C.CUSTOM_KEYS_LABEL)
            self.set_mode("keys", action[5:])
        elif action.startswith("run:"):
            self.var.set(C.RUN_LABEL)
            self.set_mode("run", action[4:])
        else:
            self.var.set(action)
            self.set_mode(None)

    def set_mode(self, mode, text=""):
        self.mode = mode
        self.evar.set(text)
        if mode is None:
            self.extra.grid_remove()
            return
        self.extra.grid()
        if mode == "keys":
            self.btn.configure(text="Nahrát", command=self.capture)
        else:
            self.btn.configure(text="Vybrat…", command=self.browse)

    # -- změny
    def on_select(self, _=None):
        label = self.var.get()
        if label == C.INHERIT[1]:
            self.set_mode(None)
            self.app.set_action(self.control, "inherit")
        elif label == C.CUSTOM_KEYS_LABEL:
            self.set_mode("keys", "")
            self.capture()
        elif label == C.RUN_LABEL:
            self.set_mode("run", "")
            self.browse()
        else:
            action = next(a for a, l in C.PRESETS if l == label)
            self.set_mode(None)
            self.app.set_action(self.control, action)

    def commit_extra(self):
        text = self.evar.get().strip()
        if not text or self.capturing:
            return
        if self.mode == "keys":
            try:
                E.parse_combo(text)
            except ValueError as e:
                self.app.status(f"Zkratku „{text}“ nelze použít: {e}", error=True)
                return
            self.app.set_action(self.control, "keys:" + text.lower().replace(" ", ""))
        elif self.mode == "run":
            self.app.set_action(self.control, "run:" + text)

    def browse(self):
        path = filedialog.askopenfilename(parent=self.app.root, title="Vyber program nebo soubor")
        if path:
            self.evar.set(os.path.normpath(path))
            self.commit_extra()

    def capture(self):
        self.capturing = True
        self.evar.set("Stiskni zkratku…")
        self.entry.focus_set()
        self.app.root.bind_all("<KeyPress>", self.on_key)

    def on_key(self, ev):
        vk = ev.keycode
        if vk in (0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C):
            return "break"  # samotný modifikátor – čekáme na hlavní klávesu
        name = E.VK_TO_NAME.get(vk)
        if not name:
            self.app.status(f"Klávesu (kód {vk}) neumím – napiš zkratku ručně, např. ctrl+shift+t", error=True)
            name = None
        mods = []
        if ev.state & 0x4:
            mods.append("ctrl")
        if ev.state & 0x1:
            mods.append("shift")
        if ev.state & 0x20000:
            mods.append("alt")
        self.app.root.unbind_all("<KeyPress>")
        self.capturing = False
        if name:
            self.evar.set("+".join(mods + [name]))
            self.commit_extra()
        else:
            self.evar.set("")
        return "break"


class App:
    def __init__(self):
        self.cfg = C.load_config()
        self.q = queue.Queue()
        self.engine = E.Engine(copy.deepcopy(self.cfg), self._from_engine)

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Tecknet Remap")
        try:
            self.root.iconbitmap(default=C.ensure_icon())
        except tk.TclError:
            pass
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self._build()
        self.current = C.GLOBAL
        self.refresh_apps()
        self.select_app(C.GLOBAL)
        self.root.after(100, self._poll)

    # ---------- komunikace s enginem
    def _from_engine(self, kind, *args):
        self.q.put((kind, args))

    def _poll(self):
        try:
            while True:
                kind, args = self.q.get_nowait()
                if kind == "show":
                    self.show()
                elif kind == "quit":
                    self.quit()
                    return
                elif kind == "toggle":
                    self.enabled_var.set(not self.enabled_var.get())
                    self.on_enabled()
                elif kind == "event":
                    control, exe, action = args
                    self.last_var.set(f"{CONTROL_LABEL[control]}  ·  {exe or '?'}  →  {C.action_label(action)}")
                elif kind == "error":
                    self.status(args[0], error=True)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def push_config(self):
        C.save_config(self.cfg)
        self.engine.set_config(copy.deepcopy(self.cfg))

    # ---------- UI
    def _build(self):
        r = self.root
        r.geometry("900x560")
        r.minsize(760, 480)
        st = ttk.Style(r)
        try:
            st.theme_use("vista")
        except tk.TclError:
            pass
        st.configure("Title.TLabel", font=("Segoe UI Semibold", 16))
        st.configure("Sub.TLabel", font=("Segoe UI", 9), foreground="#666")
        st.configure("H.TLabel", font=("Segoe UI Semibold", 12))
        st.configure("Ctl.TLabel", font=("Segoe UI Semibold", 10))
        st.configure("Status.TLabel", font=("Segoe UI", 9))

        top = ttk.Frame(r, padding=(16, 12, 16, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Tecknet TK-MS029", style="Title.TLabel").pack(side="left")
        self.dev_var = tk.StringVar()
        ttk.Label(top, textvariable=self.dev_var, style="Sub.TLabel").pack(side="left", padx=12, pady=(6, 0))
        self.auto_var = tk.BooleanVar(value=autostart_get())
        ttk.Checkbutton(top, text="Spouštět po startu Windows", variable=self.auto_var,
                        command=self.on_autostart).pack(side="right")
        self.enabled_var = tk.BooleanVar(value=self.cfg.get("enabled", True))
        ttk.Checkbutton(top, text="Přemapování zapnuto", variable=self.enabled_var,
                        command=self.on_enabled).pack(side="right", padx=16)

        ttk.Separator(r).pack(fill="x")
        body = ttk.Frame(r, padding=(16, 10))
        body.pack(fill="both", expand=True)

        # levý panel – aplikace
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Aplikace", style="H.TLabel").pack(anchor="w")
        ttk.Label(left, text="Nastavení se použije podle okna v popředí.", style="Sub.TLabel").pack(anchor="w", pady=(0, 6))
        self.apps = tk.Listbox(left, width=30, activestyle="none", exportselection=False,
                               font=("Segoe UI", 10), selectbackground=ACCENT, borderwidth=1,
                               highlightthickness=0)
        self.apps.pack(fill="y", expand=True)
        self.apps.bind("<<ListboxSelect>>", self.on_app_select)
        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="+ Přidat aplikaci", command=self.add_app_dialog).pack(side="left")
        ttk.Button(btns, text="Odebrat", command=self.remove_app).pack(side="right")

        # pravý panel – ovladače
        right = ttk.Frame(body, padding=(24, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)
        self.prof_title = tk.StringVar()
        ttk.Label(right, textvariable=self.prof_title, style="H.TLabel").pack(anchor="w")
        grid = ttk.Frame(right)
        grid.pack(fill="x", anchor="n")
        grid.columnconfigure(1, weight=1)
        self.rows = [ControlRow(self, grid, c, i) for i, (c, _) in enumerate(C.CONTROLS)]

        ttk.Separator(r).pack(fill="x")
        bottom = ttk.Frame(r, padding=(16, 6))
        bottom.pack(fill="x")
        ttk.Label(bottom, text="Poslední akce:", style="Sub.TLabel").pack(side="left")
        self.last_var = tk.StringVar(value="—  (zmáčkni boční tlačítko nebo nakloň kolečko)")
        ttk.Label(bottom, textvariable=self.last_var, style="Status.TLabel").pack(side="left", padx=6)
        self.status_var = tk.StringVar()
        self.status_lbl = ttk.Label(bottom, textvariable=self.status_var, style="Sub.TLabel")
        self.status_lbl.pack(side="right")

    def status(self, text, error=False):
        self.status_var.set(text)
        self.status_lbl.configure(foreground="#C0392B" if error else "#2E7D32")
        self.root.after(6000, lambda: self.status_var.get() == text and self.status_var.set(""))

    def refresh_apps(self):
        self.app_keys = [C.GLOBAL] + sorted(k for k in self.cfg["profiles"] if k != C.GLOBAL)
        self.apps.delete(0, "end")
        for k in self.app_keys:
            self.apps.insert("end", "  Všechny aplikace" if k == C.GLOBAL else "  " + k)

    def select_app(self, exe):
        self.current = exe
        i = self.app_keys.index(exe)
        self.apps.selection_clear(0, "end")
        self.apps.selection_set(i)
        self.apps.see(i)
        self.prof_title.set("Všechny aplikace (výchozí)" if exe == C.GLOBAL else f"Profil pro {exe}")
        for row in self.rows:
            row.load(exe)

    def on_app_select(self, _=None):
        sel = self.apps.curselection()
        if sel:
            self.select_app(self.app_keys[sel[0]])

    def set_action(self, control, action):
        prof = self.cfg["profiles"].setdefault(self.current, {})
        if action == "inherit":
            prof.pop(control, None)
        else:
            prof[control] = action
        self.push_config()
        self.status("Uloženo")

    def add_app_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Přidat aplikaci")
        dlg.transient(self.root)
        dlg.geometry("520x420")
        ttk.Label(dlg, text="Spuštěné aplikace (dvojklik pro přidání):", padding=(12, 10, 12, 4)).pack(anchor="w")
        lb = tk.Listbox(dlg, font=("Segoe UI", 10), activestyle="none", selectbackground=ACCENT)
        lb.pack(fill="both", expand=True, padx=12)
        items = [(exe, title) for exe, title in E.list_window_apps()
                 if exe not in self.cfg["profiles"] and exe not in ("pythonw.exe", "explorer.exe")]
        for exe, title in items:
            lb.insert("end", f"{exe}   —   {title[:50]}")
        bar = ttk.Frame(dlg, padding=12)
        bar.pack(fill="x")

        def add(exe):
            exe = os.path.basename(exe.strip()).lower()
            if not exe:
                return
            if not exe.endswith(".exe"):
                exe += ".exe"
            self.cfg["profiles"].setdefault(exe, {})
            self.push_config()
            self.refresh_apps()
            self.select_app(exe)
            dlg.destroy()

        def add_sel(_=None):
            s = lb.curselection()
            if s:
                add(items[s[0]][0])

        def browse():
            p = filedialog.askopenfilename(parent=dlg, title="Vyber program", filetypes=[("Programy", "*.exe")])
            if p:
                add(p)

        lb.bind("<Double-Button-1>", add_sel)
        ttk.Button(bar, text="Přidat vybranou", command=add_sel).pack(side="left")
        ttk.Button(bar, text="Procházet .exe…", command=browse).pack(side="left", padx=8)
        ttk.Button(bar, text="Zrušit", command=dlg.destroy).pack(side="right")

    def remove_app(self):
        if self.current == C.GLOBAL:
            return
        if messagebox.askyesno("Odebrat profil", f"Odebrat nastavení pro {self.current}?", parent=self.root):
            self.cfg["profiles"].pop(self.current, None)
            self.push_config()
            self.refresh_apps()
            self.select_app(C.GLOBAL)

    def on_enabled(self):
        self.cfg["enabled"] = bool(self.enabled_var.get())
        self.push_config()

    def on_autostart(self):
        try:
            autostart_set(self.auto_var.get())
        except OSError as e:
            self.status(f"Autostart se nepodařilo nastavit: {e}", error=True)
            self.auto_var.set(autostart_get())

    # ---------- okno
    def show(self):
        ok = E.device_present(self.cfg.get("device_match", ""))
        self.dev_var.set("● myš připojena" if ok else "○ přijímač myši nenalezen")
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self):
        self.root.withdraw()

    def quit(self):
        self.engine.stop()
        self.root.destroy()

    def run(self, show=False):
        self.engine.start()
        if show:
            self.root.after(50, self.show)
        self.root.mainloop()
