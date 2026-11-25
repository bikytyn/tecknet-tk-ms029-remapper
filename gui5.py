"""Okno v5 – samostatný proces okna (jádro běží zvlášť, takže okno nezdržuje myš) a rychlejší UI:
seznamy a stránky se staví jednou a pak se jen přebarvují / schovávají.

Komunikace: okno -> jádro přes PostMessage (engine.WM_APP_*), jádro -> okno přes UDP (127.0.0.1).
"""
import ctypes
import json
import os
import socket
import subprocess
import sys
import tkinter as tk

import config as C
import engine as E
import gui4
import i18n as L
import winsettings as WS
from gui2 import Switch, bind_tree, rrect, set_bg_tree
from gui3 import Slider

t = L.t
SETTING_CTLS = ("wheel", "buttons")  # ovladače, které na hlavní stránce otevřou nastavení Windows
EXTRA_HS = {"wheel": (300, 262), "lbtn": (169, 439), "rbtn": (91, 361),
            "bfork": (118, 200)}  # záloha k mouse.json; bfork = bod vidličky nad obrysem myši


class RemoteTracker:
    """Zástupce DpiTrackeru, který běží v procesu jádra."""

    def __init__(self, eng):
        self.eng = eng
        self._st = {"level": None, "confidence": 0.0, "estimate": None, "learned": 0, "learning": True}

    @property
    def level(self):
        return self._st.get("level")

    def status(self):
        return dict(self._st)

    def update(self, st):
        if isinstance(st, dict):
            self._st.update(st)

    def anchor(self, level):
        self._st.update(level=level, confidence=1.0, estimate=level)
        self.eng.post(E.WM_APP_ANCHOR, level)

    def export(self):
        return None


class RemoteEngine:
    """Stejné rozhraní jako engine.Engine, ale jen posílá zprávy běžícímu jádru."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.setblocking(False)
        self.port = self.sock.getsockname()[1]
        self.tracker = RemoteTracker(self)

    def hwnd(self):
        return E.u32.FindWindowW(E.WINDOW_CLASS, None)

    def post(self, msg, wp=0):
        h = self.hwnd()
        if not h:  # jádro neběží -> spustit ho
            exe = sys.executable
            w = os.path.join(os.path.dirname(exe), "pythonw.exe")
            subprocess.Popen([w if os.path.exists(w) else exe, os.path.join(C.APP_DIR, "remap.pyw")])
            return False
        return bool(E.u32.PostMessageW(h, msg, wp, 0))

    # rozhraní, které používá GUI
    def start(self):
        self.post(E.WM_APP_HELLO, self.port)

    def stop(self):
        h = self.hwnd()
        if h:
            E.u32.PostMessageW(h, E.WM_APP_HELLO, 0, 0)

    def set_config(self, cfg):
        self.post(E.WM_APP_RELOAD)

    def measure_begin(self):
        self.post(E.WM_APP_MEASURE, 1)

    def measure_end(self):
        self.post(E.WM_APP_MEASURE, 0)  # výsledek přijde zprávou „measure“

    def request_status(self):
        self.post(E.WM_APP_STATUS)

    def poll(self):
        out = []
        while True:
            try:
                data = self.sock.recv(65536)
            except BlockingIOError:
                break
            except OSError:
                break
            try:
                m = json.loads(data.decode("utf-8"))
                out.append((m["k"], tuple(m.get("a", []))))
            except (ValueError, KeyError):
                pass
        return out


class App(gui4.App):
    def __init__(self):
        self._arows = None
        self._app_rows_key = None
        self._win_built = False
        self._hello_n = 0
        self._wsv = WS.read_all()  # aktuální nastavení myši ve Windows (pro souhrny na kartách)
        super().__init__()
        self.engine = RemoteEngine()   # nahradí lokální jádro z gui2/gui4
        self.root.after(5000, self._dev_tick)

    def _dev_tick(self):
        """Stav připojení myši (USB / Bluetooth) v hlavičce – myš se může připojit i odpojit kdykoli."""
        if self.root.state() != "withdrawn":
            self._update_dev_label()
        self.root.after(5000, self._dev_tick)

    def app_name(self, exe):
        # okno nastavení samo běží jako pythonw.exe – uživateli ukázat název programu, ne interpretu
        if exe in ("pythonw.exe", "python.exe"):
            return "Tecknet Remap"
        # starší uložené názvy mohou obsahovat smetí za nulovým znakem (viz gui2.file_description)
        return super().app_name(exe).split("\x00", 1)[0].strip()

    # ================================================================ komunikace
    def _poll(self):
        for kind, args in self.engine.poll():
            if kind == "reload":
                self.cfg = C.load_config()
                self.cfg.setdefault("app_info", {})
                self.sw_enabled.set(self.cfg.get("enabled", True))
            elif kind in ("show", "quit", "event", "error"):
                self.q.put((kind, args))
                if kind == "event" and args:  # boční tlačítka a palcové kolečko: stejná záře jako u testeru
                    k = {"x1": "x1", "x2": "x2", "hright": "hup", "hleft": "hdown"}.get(args[0])
                    if k:
                        self.root.after(0, self._test_flash, k)
        # každých ~5 s připomenout jádru náš port (kdyby se jádro restartovalo)
        self._hello_n += 1
        if self._hello_n % 60 == 0:
            self.engine.start()
        super()._poll()

    # ---------- DPI bylo odstraněno (sledování nefungovalo spolehlivě) – vypnout zděděné části z gui4
    def _save_tracker(self):
        pass

    def _dpi_tick(self):
        pass  # gui4 to plánuje každou sekundu; v5 není co obnovovat

    def _dpi_cancel(self):
        pass

    def _update_dev_label(self):
        mice = E.connected_mice(self.cfg.get("device_match", ""))
        if mice:
            kinds = sorted({t("conn_bt") if E.is_bluetooth(m) else t("conn_usb") for m in mice})
            text = f"{t('dev_ok')} ({', '.join(kinds)})"
        else:
            text = t("dev_missing")
        self.dev_lbl.configure(text=text, fg=self.T["ok"] if mice else self.T["warn"])

    # ================================================================ rychlejší levý panel
    def refresh_apps(self):
        keys = tuple([C.GLOBAL] + sorted((k for k in self.cfg["profiles"] if k != C.GLOBAL), key=self.app_name))
        if keys != self._app_rows_key:
            super().refresh_apps()  # postaví řádky (jen když se změnil seznam aplikací)
            self._app_rows_key = keys
            self._app_rows = dict(zip(keys, self.app_scroll.frame.winfo_children()))
            for exe, row in self._app_rows.items():
                bind_tree(row, "<Enter>", lambda e, x=exe: self._app_hover(x, True))
                bind_tree(row, "<Leave>", lambda e, x=exe: self._app_hover(x, False))
        T = self.T
        for exe, row in self._app_rows.items():
            sel = exe == self.current
            bg = T["accent_soft"] if sel else T["panel"]
            set_bg_tree(row, bg)
            kids = row.winfo_children()
            kids[0].configure(bg=T["accent"] if sel else bg)  # proužek
            labels = kids[2].winfo_children()
            labels[0].configure(fg=T["accent"] if sel else T["text"],
                                font=("Segoe UI Semibold" if sel else "Segoe UI", 10))

    def _app_hover(self, exe, inside):
        if exe == self.current:
            return
        row = self._app_rows[exe]
        set_bg_tree(row, self.T["hover"] if inside else self.T["panel"])
        row.winfo_children()[0].configure(bg=self.T["hover"] if inside else self.T["panel"])

    # ================================================================ seznam akcí jako jedno plátno
    # (dřív ~160 widgetů = 160 oken Windows; při změně velikosti okna se každé přesouvalo a překreslovalo)
    def _action_sections(self):
        secs = [("sec_profile", ["inherit"])]
        for names, acts in L.CATEGORIES:
            secs.append((names, list(acts)))
        secs.append(("sec_custom", ["custom_keys", "custom_run"]))
        return secs

    def _make_action_canvas(self):
        old = self.act_scroll.cv
        parent = old.master
        old.destroy()
        cv = tk.Canvas(parent, bg=self.T["panel"], highlightthickness=0, yscrollincrement=self.px(20))
        cv.pack(fill="both", expand=True)
        self.act_cv = cv

        class _Holder:  # gui4.build_editor balí editor „before=self.act_scroll.cv“
            pass

        self.act_scroll = _Holder()
        self.act_scroll.cv = cv
        self._ahover = None
        self._ahits = []
        self._aw = 0
        cv.bind("<Configure>", lambda e: (self._aw != e.width) and self._render_actions())
        cv.bind("<Motion>", self._actions_motion)
        cv.bind("<Leave>", lambda e: self._set_ahover(None))
        cv.bind("<Button-1>", self._actions_click)
        cv.bind("<Enter>", lambda e: cv.bind_all("<MouseWheel>", self._actions_wheel))
        cv.bind("<Leave>", lambda e: (cv.unbind_all("<MouseWheel>"), self._set_ahover(None)), add="+")

    def _actions_wheel(self, e):
        if self._aheight > self.act_cv.winfo_height():
            self.act_cv.yview_scroll(int(-e.delta / 40), "units")

    def _row_at(self, e):
        y = self.act_cv.canvasy(e.y)
        for y0, y1, a in self._ahits:
            if y0 <= y <= y1:
                return a
        return None

    def _actions_motion(self, e):
        a = self._row_at(e)
        self.act_cv.configure(cursor="hand2" if a else "")
        self._set_ahover(a)

    def _set_ahover(self, a):
        if a != self._ahover:
            self._ahover = a
            self._render_actions()

    def _actions_click(self, e):
        a = self._row_at(e)
        if a:
            self.choose(a)

    def _render_actions(self):
        cv, T, px = self.act_cv, self.T, self.px
        W = cv.winfo_width()
        if W < 50:
            return
        self._aw = W
        cv.delete("all")
        self._ahits = []
        d = px(16)
        y = 0
        f_norm, f_bold, f_sub = ("Segoe UI", 10), ("Segoe UI Semibold", 10), ("Segoe UI", 8)
        for name, rows in self._avis_list:
            y += px(14)
            cv.create_text(px(22), y, text=name.upper(), anchor="nw", font=("Segoe UI Semibold", 8), fill=T["sub"])
            y += px(20)
            for a, text, sub in rows:
                h = px(34)
                sel = a == self._asel
                bg = T["accent_soft"] if sel else T["hover"] if a == self._ahover else T["panel"]
                if bg != T["panel"]:
                    cv.create_rectangle(px(12), y, W - px(12), y + h, fill=bg, outline="")
                cv.create_image(px(24) + d / 2, y + h / 2, image=self._radio_img(sel, bg))
                cv.create_text(px(24) + d + px(10), y + h / 2, text=text, anchor="w",
                               font=f_bold if sel else f_norm, fill=T["accent"] if sel else T["text"])
                if sub:
                    cv.create_text(W - px(24), y + h / 2, text=sub, anchor="e", font=f_sub, fill=T["sub"])
                self._ahits.append((y, y + h, a))
                y += h + 2
        if not self._avis_list:
            cv.create_text(px(22), px(16), text=t("nothing_found"), anchor="nw", font=("Segoe UI", 9), fill=T["sub"])
            y = px(40)
        self._aheight = y + px(16)
        cv.configure(scrollregion=(0, 0, W, self._aheight))

    def build_actions(self):
        if not hasattr(self, "act_cv"):
            self._make_action_canvas()
        if self.control in SETTING_CTLS:  # kolečko / tlačítka / DPI -> nastavení Windows místo akcí
            self._show_settings_panel(self.control)
            return
        self._hide_settings_panel()
        cur = self.raw_action(self.control)
        is_keys = cur.startswith("keys:") and cur not in L.A
        is_run = cur.startswith("run:")
        q = "" if self._search_placeholder else self.search_var.get().strip().lower()
        vis = []
        for title, acts in self._action_sections():
            name = t(title) if isinstance(title, str) else L.category(title)
            rows = []
            for a in acts:
                if a == "inherit":
                    if self.current == C.GLOBAL:
                        continue
                    text, sub = t("inherit"), L.action_short(self.raw_action(self.control, C.GLOBAL))
                elif a == "custom_keys":
                    text, sub = t("custom_keys"), (cur[5:] if is_keys else "")
                elif a == "custom_run":
                    text, sub = t("custom_run"), (os.path.basename(cur[4:]) if is_run else "")
                else:
                    text, sub = L.action(a)
                if q and not any(q in s.lower() for s in (text, sub, name)):
                    continue
                rows.append((a, text, sub))
            if rows:
                vis.append((name, rows))
        self._asel = "custom_keys" if is_keys else "custom_run" if is_run else cur
        changed = vis != getattr(self, "_avis_list", None)
        self._avis_list = vis
        self._render_actions()
        if changed:
            self.act_cv.yview_moveto(0)
        self.build_editor("keys" if is_keys else "run" if is_run else None, cur)

    def build_editor(self, mode, cur):
        # editor stavět jen když se změnil režim nebo hodnota (jinak by problikával)
        key = (mode, cur if mode else None)
        if getattr(self, "_editor_key", None) == key:
            return
        self._editor_key = key
        super().build_editor(mode, cur)

    def choose(self, action):
        if action == "custom_keys":
            self._editor_key = None
        super().choose(action)

    # ================================================================ stránky
    def _build(self):
        super()._build()
        # mezera a jemná linka mezi šablonami a diagramem myši
        tk.Frame(self.cv.master, bg=self.T["border"], height=1).pack(
            fill="x", padx=self.px(28), pady=(self.px(20), self.px(10)), before=self.cv)
        # tester tlačítek: klik / pravý klik / stisk kolečka / otočení kolečkem nad obrázkem rozsvítí myš
        self._test, self._test_n = None, 0
        # (nad kartou nebo kroužkem ovladače se tester neozývá – klik tam jen vybírá ovladač)
        self.cv.bind("<Button-1>", lambda e: self._canvas_click(e) if self._over_hit(e) else self._test_flash("left"))
        self.cv.bind("<Button-2>", lambda e: self._over_hit(e) or self._test_flash("middle"))
        self.cv.bind("<Button-3>", lambda e: self._over_hit(e) or self._test_flash("right"))
        self.cv.bind("<MouseWheel>", lambda e: self._over_hit(e) or self._test_flash("up" if e.delta > 0 else "down"))
        # obě stránky leží na sobě v jednom kontejneru; přepnutí = jen zvednout tu správnou
        # (pack_forget/pack by pokaždé přepočítal rozložení celé stránky)
        self.page_buttons.pack_forget()
        self._pages = tk.Frame(self.root, bg=self.T["bg"])
        self._pages.pack(fill="both", expand=True)
        self._pages.lower()
        for p in (self.page_win, self.page_buttons):
            p.place(in_=self._pages, x=0, y=0, relwidth=1, relheight=1)
        self.page_buttons.lift()
        self.root.after(1200, self._prebuild_win)
        self._replace_job = None
        self._rsize = None
        self.root.bind("<Configure>", self._on_root_configure, add="+")

    def _over_hit(self, e):
        return any(x1 <= e.x <= x2 and y1 <= e.y <= y2 for x1, y1, x2, y2, _ in self._hits)

    def _test_flash(self, kind):
        """Tester tlačítek: rozsvítí stisknuté místo na obrázku myši (na 0,65 s)."""
        self._test = kind
        self._test_n += 1
        n = self._test_n
        self.draw()
        self.root.after(650, lambda: self._test_n == n and (setattr(self, "_test", None), self.draw()))

    def _hidden_page(self):
        return self.page_win if self.page == "buttons" else self.page_buttons

    def _on_root_configure(self, e):
        """Při změně velikosti okna odpojit schovanou stránku (jinak se zbytečně přepočítává)
        a připojit ji zpět, až se okno uklidní – přepínání záložek pak zůstane rychlé."""
        if e.widget is not self.root:
            return
        size = (e.width, e.height)
        if size == self._rsize:
            return
        first = self._rsize is None
        self._rsize = size
        if first:
            return
        hidden = self._hidden_page()
        if hidden.winfo_manager():
            hidden.place_forget()
        if self._replace_job:
            self.root.after_cancel(self._replace_job)
        self._replace_job = self.root.after(700, self._replace_hidden)

    def _replace_hidden(self):
        self._replace_job = None
        hidden = self._hidden_page()
        if not hidden.winfo_manager():
            hidden.lower()  # nejdřív dospod, ať se při připojení ani na okamžik neukáže navrchu
            hidden.place(in_=self._pages, x=0, y=0, relwidth=1, relheight=1)

    def _ensure_placed(self, page):
        if not page.winfo_manager():
            page.place(in_=self._pages, x=0, y=0, relwidth=1, relheight=1)

    def _prebuild_win(self):
        if not self._win_built:
            self.build_win_page()
            if self.page != "win":
                self.page_buttons.lift()

    def _freeze(self, widget):
        """Dočasně zakáže překreslování oblasti (WM_SETREDRAW) – změny se pak ukážou naráz."""
        try:
            E.u32.SendMessageW(widget.winfo_id(), 0x000B, 0, 0)
        except Exception:
            pass

    def _thaw(self, widget):
        try:
            self.root.update_idletasks()
            hwnd = widget.winfo_id()
            E.u32.SendMessageW(hwnd, 0x000B, 1, 0)
            # RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW | RDW_FRAME
            ctypes.windll.user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0100 | 0x0400)
        except Exception:
            pass

    def set_page(self, page):
        if page == self.page:
            return
        self._freeze(self._pages)
        try:
            self._set_page(page)
        finally:
            self._thaw(self._pages)

    def select_control(self, control):
        self._freeze(self.page_buttons)
        try:
            super().select_control(control)
        finally:
            self._thaw(self.page_buttons)

    def select_app(self, exe):
        if not hasattr(self, "_pages"):  # první volání ještě během stavby okna
            return super().select_app(exe)
        self._freeze(self.page_buttons)
        try:
            super().select_app(exe)
        finally:
            self._thaw(self.page_buttons)

    def _set_page(self, page):
        self.page = page
        if page == "win":
            self._ensure_placed(self.page_win)
            if not self._win_built:
                self.build_win_page()
            self.page_win.lift()
        else:
            self._ensure_placed(self.page_buttons)
            self.page_buttons.lift()
            self._schedule_draw()
        self._paint_tabs()

    def build_win_page(self):
        """Záložka „Další nastavení“ – jen to, co nepatří k žádnému ovladači na myši."""
        import webbrowser
        T, px = self.T, self.px
        self.win_scroll.clear()
        outer = tk.Frame(self.win_scroll.frame, bg=T["bg"])
        outer.pack(fill="x", padx=px(48), pady=(px(6), px(30)))
        v = WS.read_all()
        intro = tk.Frame(outer, bg=T["bg"])
        intro.pack(fill="x", pady=(px(18), 0))
        self.label(intro, t("win_title"), 17, True, bg=T["bg"]).pack(anchor="w")
        self.label(intro, t("win_intro2"), 9, fg=T["sub"], bg=T["bg"], wraplength=px(760),
                   justify="left").pack(anchor="w")
        c = self._section(outer, t("sec_pointer"))
        self._row(c, t("speed"), t("speed_sub"),
                  lambda p: Slider(p, self, 1, 20, v["speed"], lambda x: self._apply(WS.set_speed, x)).pack_with_value())
        self._row(c, t("accel"), t("accel_sub"),
                  lambda p: self._switch(p, v["accel"], lambda on: self._apply(WS.set_accel, on)))

        c = self._section(outer, t("sec_cursor"))
        self._row(c, t("csize"), t("csize_sub"),
                  lambda p: Slider(p, self, 1, 15, v["cursor_size"],
                                   lambda x: self._apply(WS.set_cursor_size, x)).pack_with_value())
        self._row(c, t("schemes"), t("schemes_sub"),
                  lambda p: self.button(p, t("install_scheme"), self.install_scheme, kind="primary").pack(side="right"))
        grid = tk.Frame(c, bg=T["panel"])
        grid.pack(fill="x", padx=px(14))
        self._scheme_tiles(grid, v["scheme"])
        links = tk.Frame(c, bg=T["panel"])
        links.pack(fill="x", padx=px(20), pady=(px(8), px(16)))
        self.label(links, t("scheme_hint"), 8, fg=T["sub"], wraplength=px(760), justify="left").pack(anchor="w")
        lrow = tk.Frame(links, bg=T["panel"])
        lrow.pack(anchor="w", pady=(px(6), 0))
        self.label(lrow, t("find_schemes") + ":", 9, True).pack(side="left", padx=(0, px(10)))
        for name, url in WS.CURSOR_LINKS:
            a = self.label(lrow, name, 9, fg=T["accent"], cursor="hand2")
            a.pack(side="left", padx=(0, px(16)))
            a.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

        c = self._section(outer, t("sec_more"))
        self._row(c, t("sonar"), t("sonar_sub"),
                  lambda p: self._switch(p, v["sonar"], lambda on: self._apply(WS.set_bool, "sonar", on)))
        self._row(c, t("vanish"), None,
                  lambda p: self._switch(p, v["vanish"], lambda on: self._apply(WS.set_bool, "vanish", on)))
        self._row(c, t("snap"), t("snap_sub"),
                  lambda p: self._switch(p, v["snap"], lambda on: self._apply(WS.set_bool, "snap", on)))
        self._row(c, t("trails"), t("trails_sub"),
                  lambda p: self._switch(p, v["trails"] > 0, lambda on: self._apply(WS.set_trails, 7 if on else 0)))

        bar = tk.Frame(outer, bg=T["bg"])
        bar.pack(fill="x", pady=(px(26), 0))
        self.button(bar, t("open_settings"), WS.open_windows_settings).pack(side="left")
        self.button(bar, t("open_classic"), WS.open_classic_panel).pack(side="left", padx=px(8))
        self.button(bar, t("reset"), self.reset_windows, kind="ghost").pack(side="right")
        self._win_built = True

    def reset_windows(self):
        super().reset_windows()
        self._wsv = WS.read_all()
        self._schedule_draw()
        if self.control in SETTING_CTLS:
            self._show_settings_panel(self.control)

    def _scheme_tiles(self, grid, current):
        """Dlaždice schémat – každá je jedno plátno (dřív 9 widgetů na dlaždici)."""
        import base64
        import winsettings as WS
        from gui3 import hicon_png
        self._scheme_grid = grid
        T, px = self.T, self.px
        schemes = WS.list_schemes()
        names = {s["name"] for s in schemes}
        cols = 3
        for i in range(cols):
            grid.columnconfigure(i, weight=1, uniform="s")
        isz, chip = px(32), "#F3F4F7"
        th = px(96)
        for i, sch in enumerate([None] + schemes):
            name = t("scheme_default") if sch is None else sch["name"]
            sel = (sch is None and current not in names) or (sch is not None and sch["name"] == current)
            bg = T["accent_soft"] if sel else T["panel2"]
            cv = tk.Canvas(grid, height=th, bg=bg, highlightthickness=2 if sel else 1, cursor="hand2",
                           highlightbackground=T["accent"] if sel else T["border"])
            cv.grid(row=i // cols, column=i % cols, sticky="nsew", padx=px(5), pady=px(5))
            files = WS.DEFAULT_FILES if sch is None else sch["files"]
            imgs = []
            for cur in WS.PREVIEW:
                key = ("cur", name, cur, isz, files.get(cur, ""))
                if key not in self.images:
                    h = WS.load_cursor(files.get(cur) or WS.DEFAULT_FILES.get(cur), isz)
                    img = None
                    if h:
                        try:
                            img = tk.PhotoImage(data=base64.b64encode(hicon_png(h, isz)).decode())
                        except Exception:
                            img = None
                    self.images[key] = img
                if self.images[key]:
                    imgs.append(self.images[key])
            deletable = sch is not None and sch["source"] == 1

            def paint(e=None, cv=cv, imgs=imgs, name=name, sel=sel, deletable=deletable):
                cv.delete("all")
                w = cv.winfo_width()
                cv.create_rectangle(px(10), px(10), w - px(10), px(10) + isz + px(10), fill=chip, outline="")
                for j, img in enumerate(imgs):
                    cv.create_image(px(16) + j * (isz + px(8)), px(15), image=img, anchor="nw")
                cv.create_text(px(12), th - px(20), text=name, anchor="w",
                               font=("Segoe UI Semibold" if sel else "Segoe UI", 9),
                               fill=T["accent"] if sel else T["text"])
                if deletable:
                    cv.create_text(w - px(14), th - px(20), text="✕", anchor="e", font=("Segoe UI", 9),
                                   fill=T["sub"], tags=("del",))

            cv.bind("<Configure>", paint)

            def click(e, cv=cv, sch=sch, deletable=deletable):
                if deletable and e.x > cv.winfo_width() - px(34) and e.y > th - px(36):
                    self._delete_scheme(sch)
                else:
                    self._pick_scheme(sch)

            cv.bind("<Button-1>", click)

    def _pick_scheme(self, sch):
        import winsettings as WS
        if self._apply(WS.apply_scheme, sch, msg=t("scheme_applied")):
            grid = self._scheme_grid
            for w in grid.winfo_children():
                w.destroy()
            self._scheme_tiles(grid, WS.current_scheme())

    # ================================================================ scéna: všechny ovladače myši
    def _summaries(self):
        v = self._wsv
        wheel = t("sum_page") if v["lines"] < 0 else t("sum_lines", n=v["lines"])
        if v["hover_scroll"]:
            wheel += "  ·  " + t("sum_hover")
        buttons = (t("sum_swapped") + "  ·  " if v["swap"] else "") + t("sum_dbl", n=v["dblclick"])
        return {"wheel": wheel, "buttons": buttons}

    def draw(self):
        """Překreslit jen když se scéna opravdu změnila (velikost, výběr, bliknutí, akce, nastavení)."""
        self._draw_job = None
        if self.page != "buttons" or self.mouse_src is None:
            return
        summ = self._summaries()
        key = (self.cv.winfo_width(), self.cv.winfo_height(), self.current, self.control, self.flash,
               json.dumps([self.raw_action(c) for c in ("x1", "x2", "hleft", "hright")]),
               json.dumps([self.raw_action(c, C.GLOBAL) for c in ("x1", "x2", "hleft", "hright")]),
               json.dumps(summ), getattr(self, "_test", None), getattr(self, "_test_n", 0))
        if key == getattr(self, "_drawn_key", None):
            return
        self._drawn_key = key
        self._draw_scene(summ)

    def _draw_scene(self, summ):
        import math
        from PIL import Image, ImageDraw, ImageTk
        from gui4 import rgb
        cv, T, px = self.cv, self.T, self.px
        cv.delete("all")
        self._hits = []
        Wd, Hd = cv.winfo_width(), cv.winfo_height()
        if Wd < 200 or Hd < 150:
            return
        SS = 2
        sw, sh = self.mouse_src.size
        # rozvržení: nahoře nad myší „Levé a pravé tlačítko“ a „Kolečko“; palcové kolečko vpravo nahoře,
        # Zpět vpravo, Vpřed vlevo dole (jako dřív)
        row_h, head_h, ch, chs = px(34), px(32), px(62), px(60)
        m, vgap = px(8), px(30)
        cw = px(222)
        avail_h = Hd - 2 * m - chs - vgap
        iw = min((Wd - px(24) - cw - px(70)) / 0.67, avail_h * 0.95 * sw / sh, Wd * 0.95, px(820))
        k = iw / sw
        ih = sh * k
        free = Wd - (iw * 0.67 + px(70) + cw)
        ox = max(px(8), free / 2)
        oy = m + chs + vgap + max(0, (avail_h - ih) / 2)
        HS = dict(EXTRA_HS)
        HS.update(self.mouse_hs)
        hs = {n: (ox + x * k, oy + y * k) for n, (x, y) in HS.items()}
        ctl, flash = self.control, self.flash

        def clamp(x, y, w, h):
            return [max(px(6), min(x, Wd - w - px(6))), max(px(6), min(y, Hd - h - px(6))), w, h]

        wh_h = head_h + 2 * row_h + px(8)
        wb = clamp(hs["x1"][0] + px(64), hs["h"][1] - wh_h - px(14), cw, wh_h)            # palcové kolečko
        x1b = clamp(hs["x1"][0] + px(64), max(hs["x1"][1] + px(4), wb[1] + wb[3] + px(12)), cw, ch)  # Zpět
        x2b = clamp(hs["x2"][0] - px(64) - cw, hs["x2"][1] + px(70), cw, ch)               # Vpřed (níž, ať nezakrývá myš)
        # horní řada nad myší: tlačítka vlevo, kolečko vpravo (značky v tomto pořadí zleva -> čáry se nekříží)
        gap = px(14)
        right_edge = Wd - px(6)
        if wb[1] < m + chs + gap:  # karta palcového kolečka zasahuje do horní řady -> nesmí se překrýt
            right_edge = wb[0] - gap
        tw = min(px(250), (right_edge - px(6) - gap) / 2)
        tx = max(px(6), min(hs["rbtn"][0] - tw * 0.55, right_edge - (2 * tw + gap)))
        btb = [tx, m, tw, chs]                       # levé a pravé tlačítko (značka na pravém tlačítku)
        whb = [tx + tw + gap, m, tw, chs]            # kolečko
        wheel_ctls = ("hright", "hleft")

        # (název karty, box, ovladače které vybírá, značky na myši)
        items = [
            ("h", wb, wheel_ctls, ["h"]),
            ("x1", x1b, ("x1",), ["x1"]),
            ("x2", x2b, ("x2",), ["x2"]),
            ("buttons", btb, ("buttons",), ["rbtn", "lbtn"]),
            ("wheel", whb, ("wheel",), ["wheel"]),
        ]

        def state(ctls):
            return any(c == flash for c in ctls), any(c == ctl for c in ctls)

        pad = px(12)
        allx = [ox, ox + iw] + [b[0] for _, b, _, _ in items] + [b[0] + b[2] for _, b, _, _ in items]
        ally = [oy, oy + ih] + [b[1] for _, b, _, _ in items] + [b[1] + b[3] for _, b, _, _ in items]
        rx0, ry0 = int(max(0, min(allx) - pad)), int(max(0, min(ally) - pad))
        rx1, ry1 = int(min(Wd, max(allx) + pad)), int(min(Hd, max(ally) + pad))
        base_key = (rx1 - rx0, ry1 - ry0, int(iw), int(ih), int(ox) - rx0, int(oy) - ry0, T["bg"])
        if getattr(self, "_base_key", None) != base_key:
            base = Image.new("RGBA", ((rx1 - rx0) * SS, (ry1 - ry0) * SS), rgb(T["bg"]))
            base.alpha_composite(self._mouse_scaled(int(iw * SS), int(ih * SS)),
                                 (int((ox - rx0) * SS), int((oy - ry0) * SS)))
            self._base, self._base_key = base, base_key
        scene = self._base.copy()
        d = ImageDraw.Draw(scene, "RGBA")

        def S(*v):
            return [(a - (rx0 if i % 2 == 0 else ry0)) * SS for i, a in enumerate(v)]

        r = px(9)
        def seg(a, b, col, lw):
            d.line(S(*a, *b), fill=rgb(T["halo"], 150), width=int((lw + px(2.5)) * SS))
            d.line(S(*a, *b), fill=rgb(col), width=int(lw * SS))

        def from_ring(p, q):  # začátek čáry na okraji kroužku
            dx, dy = q[0] - p[0], q[1] - p[1]
            dist = math.hypot(dx, dy) or 1
            return p[0] + dx / dist * (r + px(2)), p[1] + dy / dist * (r + px(2))

        for name, box, ctls, marks in items:  # vodicí čáry
            fl, sel = state(ctls)
            x, y, w, h = box
            col = T["ok"] if fl else T["accent"] if sel else T["lead"]
            lw = px(2) if (fl or sel) else max(1, px(1.5))
            if len(marks) > 1:
                # vidlička: z každého kroužku krátká čára do společného bodu, odtud jedna čára ke kartě
                ps = [hs[m] for m in marks]
                jx, jy = hs["bfork"]  # bod vidličky – nad obrysem myši
                q = (min(max(jx, x), x + w), min(max(jy, y), y + h))
                segs = [(from_ring(p, (jx, jy)), (jx, jy)) for p in ps] + [((jx, jy), q)]
                # nejdřív všechny lemy, pak všechny čáry – jinak lem další čáry přeruší tu předchozí
                for a, b in segs:
                    d.line(S(*a, *b), fill=rgb(T["halo"], 150), width=int((lw + px(2.5)) * SS))
                for a, b in segs:
                    d.line(S(*a, *b), fill=rgb(col), width=int(lw * SS))
                jr = lw / 2  # zaoblený spoj (stejná barva jako čáry, žádná tečka navíc)
                d.ellipse(S(jx - jr, jy - jr, jx + jr, jy + jr), fill=rgb(col))
                continue
            p = hs[marks[0]]
            q = (min(max(p[0], x), x + w), min(max(p[1], y), y + h))
            seg(from_ring(p, q), q, col, lw)

        def card(box, fill, outline, width):
            x, y, w, h = box
            d.rounded_rectangle(S(x, y, x + w, y + h), radius=px(10) * SS, fill=rgb(fill),
                                outline=rgb(outline), width=int(width * SS))

        fl, sel = state(wheel_ctls)
        card(wb, T["card"], T["ok"] if fl else T["accent"] if sel else T["border"], px(2) if (fl or sel) else 1)
        for i, c in enumerate(wheel_ctls):
            if c == ctl or c == flash:
                x, y, w, h = wb
                ry = y + head_h + i * row_h
                d.rounded_rectangle(S(x + px(6), ry + px(2), x + w - px(6), ry + row_h - px(2)), radius=px(7) * SS,
                                    fill=rgb(T["ok"] if c == flash else T["accent"]))
        for name, box, ctls, _ in items[1:]:
            fl, sel = state(ctls)
            fill = T["ok"] if fl else T["accent"] if sel else T["card"]
            card(box, fill, fill if (fl or sel) else T["border"], 1)
        for name, box, ctls, marks in items:  # kroužky
            fl, sel = state(ctls)
            for m in marks:
                x, y = hs[m]
                col = T["ok"] if fl else T["accent"] if sel else T["marker"]
                d.ellipse(S(x - r - px(2.5), y - r - px(2.5), x + r + px(2.5), y + r + px(2.5)),
                          outline=rgb(T["halo"], 140), width=int(px(2.5) * SS))
                d.ellipse(S(x - r, y - r, x + r, y + r), outline=rgb(col), width=int(max(2, px(2)) * SS),
                          fill=rgb(col) if (fl or sel) else None)
                if fl or sel:
                    d.ellipse(S(x - r * 0.4, y - r * 0.4, x + r * 0.4, y + r * 0.4), fill=(255, 255, 255, 255))
        # tester: zelená záře na stisknutém místě myši + bublina s popisem
        test = getattr(self, "_test", None)
        bubble = None
        if test:
            spot = {"left": "lbtn", "right": "rbtn", "middle": "wheel", "up": "wheel", "down": "wheel",
                    "x1": "x1", "x2": "x2", "hup": "h", "hdown": "h"}[test]
            x, y = hs[spot]
            g = rgb(T["ok"])
            for rad, alpha in ((r * 2.4, 50), (r * 1.8, 90), (r * 1.35, 140)):
                d.ellipse(S(x - rad, y - rad, x + rad, y + rad), fill=(g[0], g[1], g[2], alpha))
            d.ellipse(S(x - r, y - r, x + r, y + r), fill=g, outline=(255, 255, 255, 255), width=int(px(2) * SS))
            # bublina jen u koleček a jen se značkou (kreslenou, ať je přesně uprostřed):
            # nahoru = lehce nad středem kroužku, dolů = lehce pod ním, stisk = v úrovni
            kind = {"up": "up", "hup": "up", "down": "down", "hdown": "down", "middle": "press"}.get(test)
            if kind:
                bw = bh = px(28)
                # palcové kolečko má vpravo kartu -> značka vlevo od kroužku
                bx = x - r * 2.7 - bw if spot == "h" else x + r * 2.7
                bx = min(max(bx, rx0 + px(4)), rx1 - bw - px(4))
                by = y - bh / 2 + {"up": -px(9), "down": px(9), "press": 0}[kind]
                by = min(max(by, ry0 + px(4)), ry1 - bh - px(4))
                d.rounded_rectangle(S(bx, by, bx + bw, by + bh), radius=px(8) * SS, fill=g)
                cx, cy, s = bx + bw / 2, by + bh / 2, px(6)
                white = (255, 255, 255, 255)
                if kind == "up":
                    d.polygon(S(cx, cy - s * 0.85, cx + s, cy + s * 0.65, cx - s, cy + s * 0.65), fill=white)
                elif kind == "down":
                    d.polygon(S(cx, cy + s * 0.85, cx + s, cy - s * 0.65, cx - s, cy - s * 0.65), fill=white)
                else:  # stisk: prstýnek s tečkou
                    d.ellipse(S(cx - s, cy - s, cx + s, cy + s), outline=white, width=int(px(2) * SS))
                    d.ellipse(S(cx - s * 0.4, cy - s * 0.4, cx + s * 0.4, cy + s * 0.4), fill=white)
        self._scene = ImageTk.PhotoImage(scene.reduce(SS), master=self.root)
        cv.create_image(rx0, ry0, image=self._scene, anchor="nw")
        if bubble:
            cv.create_text(bubble[0], bubble[1], text=bubble[2], font=self.f_card, fill="#FFFFFF", tags=("bubble",))
        cv.create_text(Wd - px(10), Hd - px(8), text=t("test_hint"), anchor="se", font=self.f_cardsub,
                       fill=T["sub"])

        # ---------- texty a klikací oblasti
        def fit(text, font, maxw):
            while font.measure(text) > maxw and len(text) > 3:
                text = text[:-2] + "…"
            return text

        def effective(c):
            raw = self.raw_action(c)
            return (self.raw_action(c, C.GLOBAL), True) if raw == "inherit" else (raw, False)

        # jednotně na všech kartách: nahoře tučně název prvku, pod ním funkce / nastavení
        if not hasattr(self, "f_row"):
            import tkinter.font as tkfont
            self.f_row = tkfont.Font(family="Segoe UI", size=10)
        x, y, w, h = wb
        cv.create_text(x + px(14), y + head_h / 2 + px(4), text=fit(t("thumb_wheel"), self.f_card, w - px(28)),
                       anchor="w", font=self.f_card, fill=T["text"])
        for i, (c, arrow) in enumerate(zip(wheel_ctls, ("▲", "▼"))):
            ry = y + head_h + i * row_h
            on = c == ctl or c == flash
            fg = "#FFFFFF" if on else T["text"]
            eff, inh = effective(c)
            cv.create_text(x + px(18), ry + row_h / 2, text=arrow, anchor="w", font=self.f_cardsub, fill=fg)
            cv.create_text(x + px(40), ry + row_h / 2, anchor="w", font=self.f_row, fill=fg,
                           text=fit(L.action_short(eff) + (f"  ·  {t('inherited')}" if inh else ""),
                                    self.f_row, w - px(54)))
            self._hits.append((x, ry, x + w, ry + row_h, c))
        self._hits.append((x, y, x + w, y + h, ctl if ctl in wheel_ctls else "hright"))

        cards = [(c, box, f"{arrow}  {L.control(c)}",
                  L.action_short(effective(c)[0]) + (f"  ·  {t('inherited')}" if effective(c)[1] else ""))
                 for c, box, arrow in (("x1", x1b, "◀"), ("x2", x2b, "▶"))]
        cards += [(c, box, L.control(c), summ[c]) for c, box in (("wheel", whb), ("buttons", btb))]
        for c, box, title, sub in cards:
            x, y, w, h = box
            on = c == ctl or c == flash
            fg, sub_fg = ("#FFFFFF", "#E6EEFB") if on else (T["text"], T["sub"])
            cv.create_text(x + px(14), y + px(20), anchor="w", font=self.f_card, fill=fg,
                           text=fit(title, self.f_card, w - px(28)))
            cv.create_text(x + px(14), y + px(42), anchor="w", font=self.f_row, fill=sub_fg,
                           text=fit(sub, self.f_row, w - px(28)))
            self._hits.append((x, y, x + w, y + h, c))

        rr = r + px(6)
        for name, box, ctls, marks in items:
            target = (ctl if ctl in wheel_ctls else "hright") if name == "h" else ctls[0]
            for m in marks:
                x, y = hs[m]
                self._hits.append((x - rr, y - rr, x + rr, y + rr, target))

    # ================================================================ pravý panel: nastavení Windows
    def _right_parts(self):
        rt = self.ctl_title.master
        return rt.winfo_children()[0], self.search.master  # nadpis „AKCE PRO“, pole hledání

    def _show_settings_panel(self, kind):
        T, px = self.T, self.px
        head, sbox = self._right_parts()
        head.configure(text=t("settings_for"))
        if sbox.winfo_manager():
            sbox.pack_forget()
        self.act_cv.pack_forget()
        self.editor.pack_forget()
        self._editor_key = None
        if not hasattr(self, "set_panel"):
            self.set_panel = tk.Frame(self.act_cv.master, bg=T["panel"])
        for w in self.set_panel.winfo_children():
            w.destroy()
        self.set_panel.pack(fill="both", expand=True)
        self._wsv = WS.read_all()
        v = self._wsv
        box = tk.Frame(self.set_panel, bg=T["panel"])
        box.pack(fill="x", padx=px(22), pady=(px(6), 0))

        def changed():
            self._wsv = WS.read_all()
            self._schedule_draw()

        def apply(fn, *a):
            if self._apply(fn, *a):
                changed()

        def row(title, sub=None, inline=None):
            f = tk.Frame(box, bg=T["panel"])
            f.pack(fill="x", pady=(px(14), 0))
            top = tk.Frame(f, bg=T["panel"])
            top.pack(fill="x")
            self.label(top, title, 10, True, anchor="w").pack(side="left")
            if inline:
                inline(top)
            if sub:
                self.label(f, sub, 8, fg=T["sub"], wraplength=px(280), justify="left").pack(anchor="w")
            body = tk.Frame(f, bg=T["panel"])
            body.pack(fill="x", pady=(px(6), 0))
            return body

        def switch(value, fn, also_right=False):
            def mk(parent):
                sw = Switch(parent, self, value, fn)
                sw.pack(side="right")
                if also_right:
                    sw.bind("<Button-3>", sw.toggle)
            return mk

        if kind == "wheel":
            lines = {"v": v["lines"] if v["lines"] > 0 else 3}
            page = {}

            def set_lines(x):
                lines["v"] = x
                if not page["on"]:
                    apply(WS.set_lines, x)

            def set_page(on):
                page["on"] = on
                apply(WS.set_lines, -1 if on else lines["v"])

            page["on"] = v["lines"] < 0
            Slider(row(t("lines"), t("lines_sub")), self, 1, 20, lines["v"], set_lines, width=200).pack_with_value()
            row(t("page"), t("page_sub"), switch(page["on"], set_page))
            row(t("hover"), t("hover_sub"), switch(v["hover_scroll"], lambda on: apply(WS.set_hover_scroll, on)))
            Slider(row(t("chars"), t("chars_sub")), self, 1, 20, v["chars"],
                   lambda x: apply(WS.set_chars, x), width=200).pack_with_value()
            self.label(box, t("mid_note"), 8, fg=T["sub"], wraplength=px(280), justify="left").pack(
                anchor="w", pady=(px(16), 0))
        elif kind == "buttons":
            row(t("swap"), t("swap_sub"), switch(v["swap"], lambda on: apply(WS.set_swap, on), also_right=True))
            body = row(t("dbl"), t("dbl_sub"))
            Slider(body, self, 200, 900, v["dblclick"], lambda x: apply(WS.set_dblclick, x),
                   fmt=lambda x: f"{x} ms", step=10, width=180).pack_with_value()
            test = tk.Canvas(box, width=px(140), height=px(44), bg=T["panel"], highlightthickness=0, cursor="hand2")
            test.pack(anchor="w", pady=(px(10), 0))
            st = {"on": False}

            def paint():
                test.delete("all")
                rrect(test, 2, 2, px(140) - 2, px(44) - 2, px(10), fill=T["ok"] if st["on"] else T["panel2"],
                      outline=T["border"])
                test.create_text(px(70), px(22), text=t("dbl_ok") if st["on"] else t("dbl_test"),
                                 fill="#FFFFFF" if st["on"] else T["sub"], font=("Segoe UI", 9))

            test.bind("<Double-Button-1>", lambda e: (st.update(on=not st["on"]), paint()))
            paint()
        link = self.label(box, t("open_win"), 9, fg=T["accent"], cursor="hand2")
        link.pack(anchor="w", pady=(px(22), 0))
        link.bind("<Button-1>", lambda e: WS.open_windows_settings())

    def _hide_settings_panel(self):
        if hasattr(self, "set_panel") and self.set_panel.winfo_manager():
            self.set_panel.pack_forget()
            head, sbox = self._right_parts()
            head.configure(text=t("actions_for"))
            sbox.pack(fill="x", pady=(self.px(12), self.px(2)))
            self.act_cv.pack(fill="both", expand=True)

    def _schedule_draw(self, _=None):
        if self._draw_job:
            self.root.after_cancel(self._draw_job)
        self._draw_job = self.root.after(45, self.draw)

    def show(self):
        self._update_dev_label()
        self.sw_auto.set(gui4.G.autostart_get())
        self.root.deiconify()
        self._titlebar(self.root)
        self.root.lift()
        self.root.focus_force()

    def set_language(self, code):
        if code == L.LANG:
            return
        self.cfg["language"] = code
        self.push_config()  # uloží a řekne jádru (menu v oznamovací oblasti)
        self.status(t("lang_restart"))
        args = [sys.executable, os.path.join(C.APP_DIR, "remap.pyw"), "--gui", "--restart"]
        if self.page == "win":
            args.append("--page-win")
        subprocess.Popen(args, creationflags=0x00000008)
        self.root.after(100, self.quit)
