"""Okno v4 – EN/CS, vyhlazená scéna myši (Pillow), měření DPI, instalace sad kurzorů, vlastní ikona.

Navazuje na gui2.App (profily, akce, engine). Texty jsou v i18n.py.
"""
import base64
import json
import math
import os
import subprocess
import sys
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox

from PIL import Image, ImageDraw, ImageTk

import config as C
import engine as E
import gui2 as G
import i18n as L
import winsettings as WS
from gui2 import ScrollList, Switch, bind_tree, rrect, set_bg_tree
from gui3 import Slider, hicon_png
from dpi_tracker import DpiTracker

t = L.t
ASSETS = os.path.join(C.APP_DIR, "assets")
G.LIGHT.update(lead="#59616F", halo="#FFFFFF")
G.DARK.update(lead="#C9D1DC", halo="#0B0C0F")


DPI_LEVELS = [800, 1200, 1600, 2400, 3200, 4800]  # stupně TK-MS029 podle výrobce (výchozí 1600)
DPI_DISTANCES = [(10.0, "dpi_d_ruler"), (8.56, "dpi_d_card"), (21.0, "dpi_d_a4")]


def snap_dpi(v):
    """-> (nejbližší stupeň, jistota 0..1; 1 = přesně na stupni, 0 = na hranici mezi stupni)"""
    lv = min(DPI_LEVELS, key=lambda x: abs(math.log(v / x)))
    i = DPI_LEVELS.index(lv)
    half = min(abs(math.log(DPI_LEVELS[j] / lv)) for j in (i - 1, i + 1) if 0 <= j < len(DPI_LEVELS)) / 2
    return lv, max(0.0, 1 - abs(math.log(v / lv)) / half)


def dpi_pos(v):
    """poloha na budíku: index stupně, mezi stupni logaritmicky"""
    if v <= DPI_LEVELS[0]:
        return max(-0.3, math.log(v / DPI_LEVELS[0]) / math.log(1.5))
    for i in range(len(DPI_LEVELS) - 1):
        a, b = DPI_LEVELS[i], DPI_LEVELS[i + 1]
        if v <= b:
            return i + math.log(v / a) / math.log(b / a)
    return min(len(DPI_LEVELS) - 0.7, len(DPI_LEVELS) - 1 + math.log(v / DPI_LEVELS[-1]) / math.log(1.5))


def rgb(h, a=255):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), a


class App(G.App):
    def __init__(self):
        L.set_lang(C.load_config().get("language", "en"))
        self.page = "buttons"
        self.mouse_src = None
        self._mouse_key = None
        self._search_placeholder = True
        self._hits = []
        self._draw_job = None
        self.dpi_cm = 10.0
        self.dpi_state = "idle"
        self.dpi_result = None
        self._dpi_drawn = None
        super().__init__()
        old = self.cfg.get("dpi") or {}
        if old and not (600 <= old.get("measured", 0) <= 6400):
            self.cfg.pop("dpi", None)  # chybné staré měření (mimo rozsah myši)
            C.save_config(self.cfg)
        self.engine.tracker = DpiTracker(self.cfg.get("dpi_track"))
        self._tick_n = 0
        self.root.after(1000, self._dpi_tick)
        try:
            icons = [ImageTk.PhotoImage(Image.open(os.path.join(ASSETS, "app.png")).resize((s, s), Image.LANCZOS),
                                        master=self.root) for s in (256, 48, 32, 16)]
            self.root.iconphoto(True, *icons)
            self._app_icons = icons
        except OSError:
            pass

    # ================================================================ texty převzatých částí
    def app_name(self, exe):
        if exe == C.GLOBAL:
            return t("all_apps")
        return super().app_name(exe)

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
                    self.sw_enabled.set(not self.sw_enabled.value)
                    self.on_enabled(self.sw_enabled.value)
                elif kind == "event":
                    control, exe, action = args
                    self.last_lbl.configure(text=f"{L.control(control)}  ·  {self.app_name(exe) if exe else '?'}"
                                                 f"  →  {L.action_short(action)}")
                    self.flash = control
                    self.draw()
                    self.root.after(450, self._unflash, control)
                elif kind == "dpi":
                    self.status(t("dpi_changed", dpi=args[0]))
                    self._save_tracker()
                    self._update_dev_label()
                    self.dpi_result = None
                    if self.page == "win":
                        self._dpi_show()
                elif kind == "error":
                    self.status(args[0], error=True)
        except Exception:
            pass
        self.root.after(80, self._poll)

    # ---------- pasivní DPI
    def _save_tracker(self):
        tr = self.engine.tracker
        if tr:
            self.cfg["dpi_track"] = tr.export()
            C.save_config(self.cfg)

    def _dpi_anchor(self, level):
        self.engine.tracker.anchor(level)
        self.dpi_result = None
        self._save_tracker()
        self._update_dev_label()
        self._dpi_show()

    def _dpi_tick(self):
        self._tick_n += 1
        if self._tick_n % 120 == 0:  # každé 2 minuty uložit, co se naučil
            self._save_tracker()
        if self.page == "win" and self.root.state() == "normal":
            try:
                self._dpi_refresh()
            except tk.TclError:
                pass
        self.root.after(1000, self._dpi_tick)

    def _dpi_refresh(self):
        """Průběžně aktualizuje stav sledování (text, čipy stupňů a budík, když se něco změnilo)."""
        if not hasattr(self, "dpi_track_lbl") or not self.dpi_track_lbl.winfo_exists():
            return
        st = self.engine.tracker.status()
        T = self.T
        if not st["level"]:
            txt = t("dpi_track_none")
        elif st["learning"]:
            txt = t("dpi_track_learning", n=st["learned"])
        else:
            txt = t("dpi_track_ok", c=int(round(st["confidence"] * 100)), n=st["learned"])
        self.dpi_track_lbl.configure(text=txt)
        for lv, ch in self._level_chips:
            on = lv == st["level"]
            ch.configure(bg=T["accent"] if on else T["panel2"], fg=T["on_accent"] if on else T["text"])
        key = (st["level"], st["estimate"] and round(st["estimate"], -1))
        if key != self._dpi_drawn and self.dpi_state == "idle":
            self._dpi_show()

    def status(self, text, error=False):
        self.status_lbl.configure(text=text, fg=self.T["warn"] if error else self.T["ok"])
        self.root.after(5000, lambda: self.status_lbl.cget("text") == text and self.status_lbl.configure(text=""))

    # ================================================================ stavba
    def _build(self):
        T, px, r = self.T, self.px, self.root
        r.geometry(f"{px(1180)}x{px(730)}")
        r.minsize(px(1060), px(640))
        self._load_mouse()

        hdr = tk.Frame(r, bg=T["panel"])
        hdr.pack(fill="x")
        inner = tk.Frame(hdr, bg=T["panel"])
        inner.pack(fill="x", padx=px(20))
        try:
            s = px(36)
            self.logo = ImageTk.PhotoImage(Image.open(os.path.join(ASSETS, "app.png")).resize((s, s), Image.LANCZOS),
                                           master=r)
            tk.Label(inner, image=self.logo, bg=T["panel"]).pack(side="left", pady=px(12))
        except OSError:
            pass
        tb = tk.Frame(inner, bg=T["panel"])
        tb.pack(side="left", padx=px(12))
        self.label(tb, "Tecknet TK-MS029", 15, True).pack(anchor="w")
        self.dev_lbl = self.label(tb, "", 9, fg=T["sub"])
        self.dev_lbl.pack(anchor="w")

        tabs = tk.Frame(inner, bg=T["panel"])
        tabs.pack(side="left", padx=(px(36), 0), fill="y")
        self.tabs = {}
        for key, text in (("buttons", t("tab_buttons")), ("win", t("tab_windows"))):
            f = tk.Frame(tabs, bg=T["panel"], cursor="hand2")
            f.pack(side="left", fill="y", padx=px(4))
            lab = tk.Label(f, text=text, font=("Segoe UI Semibold", 11), bg=T["panel"], fg=T["sub"])
            lab.pack(side="top", padx=px(12), pady=(px(22), px(14)))
            und = tk.Frame(f, bg=T["panel"], height=px(3))
            und.pack(side="bottom", fill="x", padx=px(8))
            bind_tree(f, "<Button-1>", lambda e, k=key: self.set_page(k))
            self.tabs[key] = (lab, und)

        # jazyk EN | CS
        lang = tk.Frame(inner, bg=T["panel"])
        lang.pack(side="right", padx=(px(22), 0))
        for code, name in L.LANGS:
            on = code == L.LANG
            b = tk.Label(lang, text=name, font=("Segoe UI Semibold", 9), cursor="hand2", padx=px(8), pady=px(3),
                         bg=T["accent"] if on else T["panel2"], fg=T["on_accent"] if on else T["sub"])
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, c=code: self.set_language(c))

        def switch(text, value, cmd):
            box = tk.Frame(inner, bg=T["panel"])
            box.pack(side="right", padx=(px(22), 0))
            sw = Switch(box, self, value, cmd)
            sw.pack(side="left")
            self.label(box, text, 10).pack(side="left", padx=(px(8), 0))
            return sw

        self.sw_auto = switch(t("sw_autostart"), G.autostart_get(), self.on_autostart)
        self.sw_enabled = switch(t("sw_enabled"), self.cfg.get("enabled", True), self.on_enabled)
        tk.Frame(r, bg=T["border"], height=1).pack(fill="x")

        foot = tk.Frame(r, bg=T["panel"])
        foot.pack(side="bottom", fill="x")
        tk.Frame(r, bg=T["border"], height=1).pack(side="bottom", fill="x")
        fi = tk.Frame(foot, bg=T["panel"])
        fi.pack(fill="x", padx=px(20), pady=px(8))
        self.label(fi, t("last_action"), 9, True, fg=T["sub"]).pack(side="left")
        self.last_lbl = self.label(fi, t("last_hint"), 9, fg=T["sub"])
        self.last_lbl.pack(side="left", padx=px(10))
        self.status_lbl = self.label(fi, "", 9, fg=T["ok"])
        self.status_lbl.pack(side="right")

        # ---- stránka Tlačítka
        self.page_buttons = body = tk.Frame(r, bg=T["bg"])
        body.pack(fill="both", expand=True)
        side = tk.Frame(body, bg=T["panel"], width=px(236))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Frame(body, bg=T["border"], width=1).pack(side="left", fill="y")
        self.label(side, t("apps"), 8, True, fg=T["sub"]).pack(anchor="w", padx=px(20), pady=(px(18), px(8)))
        self.button(side, t("add_app"), self.add_app_dialog).pack(side="bottom", fill="x", padx=px(16), pady=px(16))
        self.app_scroll = ScrollList(side, T["panel"], px(20))
        self.app_scroll.cv.pack(fill="both", expand=True)

        right = tk.Frame(body, bg=T["panel"], width=px(330))
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        tk.Frame(body, bg=T["border"], width=1).pack(side="right", fill="y")
        rt = tk.Frame(right, bg=T["panel"])
        rt.pack(fill="x", padx=px(22), pady=(px(18), px(6)))
        self.label(rt, t("actions_for"), 8, True, fg=T["sub"]).pack(anchor="w")
        self.ctl_title = self.label(rt, "", 13, True)
        self.ctl_title.pack(anchor="w")
        sbox = tk.Frame(rt, bg=T["panel2"], highlightthickness=1, highlightbackground=T["border"])
        sbox.pack(fill="x", pady=(px(12), px(2)))
        self.label(sbox, "⌕", 13, fg=T["sub"], bg=T["panel2"]).pack(side="left", padx=(px(10), 0))
        self.search_var = tk.StringVar(value=t("search"))
        self.search = tk.Entry(sbox, textvariable=self.search_var, font=("Segoe UI", 10), bg=T["panel2"],
                               fg=T["sub"], insertbackground=T["text"], relief="flat")
        self.search.pack(side="left", fill="x", expand=True, padx=px(8), ipady=px(6))
        self.search.bind("<FocusIn>", self._search_focus)
        self.search.bind("<FocusOut>", self._search_blur)
        self.search_var.trace_add("write", lambda *_: self._search_placeholder or self.build_actions())
        self.editor = tk.Frame(right, bg=T["panel2"])
        self.act_scroll = ScrollList(right, T["panel"], px(20))
        self.act_scroll.cv.pack(fill="both", expand=True)

        center = tk.Frame(body, bg=T["bg"])
        center.pack(side="left", fill="both", expand=True)
        top = tk.Frame(center, bg=T["bg"])
        top.pack(fill="x", padx=px(28), pady=(px(20), 0))
        trow = tk.Frame(top, bg=T["bg"])
        trow.pack(fill="x")
        self.title_lbl = self.label(trow, "", 17, True)
        self.title_lbl.pack(side="left")
        self.remove_btn = self.button(trow, t("remove_profile"), self.remove_app, kind="ghost")
        self.sub_lbl = self.label(top, "", 9, fg=T["sub"])
        self.sub_lbl.pack(anchor="w")
        chips = tk.Frame(top, bg=T["bg"])
        chips.pack(anchor="w", pady=(px(12), 0))
        self.label(chips, t("presets"), 9, True, fg=T["sub"]).pack(side="left", padx=(0, px(10)))
        for key, _ in L.TEMPLATES:
            self.button(chips, t(key), lambda k=key: self.apply_template(k)).pack(side="left", padx=(0, px(8)))
        self.cv = tk.Canvas(center, bg=T["bg"], highlightthickness=0)
        self.cv.pack(fill="both", expand=True, padx=px(8), pady=px(8))
        self.cv.bind("<Configure>", self._schedule_draw)
        self.cv.bind("<Button-1>", self._canvas_click)
        self.cv.bind("<Motion>", self._canvas_motion)

        # ---- stránka Myš ve Windows
        self.page_win = tk.Frame(r, bg=T["bg"])
        self.win_scroll = ScrollList(self.page_win, T["bg"], px(24))
        self.win_scroll.cv.pack(fill="both", expand=True)
        self._paint_tabs()

    # ================================================================ záložky, jazyk
    def _paint_tabs(self):
        for key, (lab, und) in self.tabs.items():
            on = key == self.page
            lab.configure(fg=self.T["tab_on"] if on else self.T["sub"])
            und.configure(bg=self.T["accent"] if on else self.T["panel"])

    def set_page(self, page):
        if page == self.page:
            return
        self._dpi_cancel()
        self.page = page
        if page == "win":
            self.page_buttons.pack_forget()
            self.page_win.pack(fill="both", expand=True)
            self.build_win_page()
        else:
            self.page_win.pack_forget()
            self.page_buttons.pack(fill="both", expand=True)
            self._schedule_draw()
        self._paint_tabs()

    def set_language(self, code):
        if code == L.LANG:
            return
        self.cfg["language"] = code
        C.save_config(self.cfg)
        self.status(t("lang_restart"))
        args = [sys.executable, os.path.join(C.APP_DIR, "remap.pyw"), "--show", "--restart"]
        if self.page == "win":
            args.append("--page-win")
        subprocess.Popen(args, creationflags=0x00000008)  # DETACHED_PROCESS
        self.root.after(100, self.quit)

    # ================================================================ levý panel a hlavička profilu
    def refresh_apps(self):
        T, px = self.T, self.px
        self.app_scroll.clear()
        keys = [C.GLOBAL] + sorted((k for k in self.cfg["profiles"] if k != C.GLOBAL), key=self.app_name)
        for exe in keys:
            sel = exe == self.current
            bg = T["accent_soft"] if sel else T["panel"]
            row = tk.Frame(self.app_scroll.frame, bg=bg, cursor="hand2")
            row.pack(fill="x", padx=px(10), pady=1)
            tk.Frame(row, bg=T["accent"] if sel else bg, width=px(3)).pack(side="left", fill="y")
            self.icon_widget(row, exe, bg).pack(side="left", padx=px(10), pady=px(8))
            tx = tk.Frame(row, bg=bg)
            tx.pack(side="left", fill="x", expand=True)
            self.label(tx, self.app_name(exe), 10, sel, fg=T["accent"] if sel else T["text"], anchor="w").pack(anchor="w")
            self.label(tx, t("default_profile") if exe == C.GLOBAL else exe, 8, fg=T["sub"], anchor="w").pack(anchor="w")
            bind_tree(row, "<Button-1>", lambda e, x=exe: self.select_app(x))
            if not sel:
                bind_tree(row, "<Enter>", lambda e, w=row: set_bg_tree(w, T["hover"]))
                bind_tree(row, "<Leave>", lambda e, w=row: set_bg_tree(w, T["panel"]))

    def select_app(self, exe):
        self.current = exe
        self.refresh_apps()
        self.title_lbl.configure(text=self.app_name(exe))
        if exe == C.GLOBAL:
            self.sub_lbl.configure(text=t("global_sub"))
            self.remove_btn.pack_forget()
        else:
            self.sub_lbl.configure(text=t("app_sub", exe=exe))
            self.remove_btn.pack(side="right")
        self.select_control(self.control)

    def select_control(self, control):
        self.control = control
        self.ctl_title.configure(text=L.control(control))
        self.build_actions()
        self._schedule_draw()

    # ================================================================ akce
    def _search_focus(self, _):
        if self._search_placeholder:
            self.search_var.set("")
            self._search_placeholder = False
            self.search.configure(fg=self.T["text"])

    def _search_blur(self, _):
        if not self.search_var.get():
            self._search_placeholder = True
            self.search_var.set(t("search"))
            self.search.configure(fg=self.T["sub"])

    def build_actions(self):
        T, px = self.T, self.px
        sl = self.act_scroll
        sl.clear()
        cur = self.raw_action(self.control)
        q = "" if self._search_placeholder else self.search_var.get().strip().lower()
        sections = []
        if self.current != C.GLOBAL:
            sections.append((t("sec_profile"), [("inherit", t("inherit"),
                                                 L.action_short(self.raw_action(self.control, C.GLOBAL)))]))
        for names, acts in L.CATEGORIES:
            sections.append((L.category(names), [(a, *L.action(a)) for a in acts]))
        is_keys = cur.startswith("keys:") and cur not in L.A
        is_run = cur.startswith("run:")
        sections.append((t("sec_custom"), [("custom_keys", t("custom_keys"), cur[5:] if is_keys else ""),
                                            ("custom_run", t("custom_run"), os.path.basename(cur[4:]) if is_run else "")]))

        def selected(a):
            return a == cur or (a == "custom_keys" and is_keys) or (a == "custom_run" and is_run)

        shown = 0
        for title, items in sections:
            items = [i for i in items if not q or any(q in s.lower() for s in (i[1], i[2], title))]
            if not items:
                continue
            self.label(sl.frame, title.upper(), 8, True, fg=T["sub"]).pack(anchor="w", padx=px(22), pady=(px(14), px(4)))
            for action, text, sub in items:
                self._action_row(sl.frame, action, text, sub, selected(action))
                shown += 1
        if not shown:
            self.label(sl.frame, t("nothing_found"), 9, fg=T["sub"]).pack(anchor="w", padx=px(22), pady=px(16))
        tk.Frame(sl.frame, bg=T["panel"], height=px(16)).pack()
        self.build_editor("keys" if is_keys else "run" if is_run else None, cur)

    def _action_row(self, parent, action, text, sub, sel):
        T, px = self.T, self.px
        bg = T["accent_soft"] if sel else T["panel"]
        f = tk.Frame(parent, bg=bg, cursor="hand2")
        f.pack(fill="x", padx=px(12), pady=1)
        d = px(16)
        rc = tk.Canvas(f, width=d, height=d, bg=bg, highlightthickness=0)
        rc.pack(side="left", padx=(px(12), px(10)), pady=px(9))
        img = self._radio_img(sel, bg)
        rc.create_image(d / 2, d / 2, image=img)
        self.label(f, text, 10, sel, fg=T["accent"] if sel else T["text"], anchor="w").pack(side="left")
        if sub:
            self.label(f, sub, 8, fg=T["sub"]).pack(side="right", padx=px(12))
        bind_tree(f, "<Button-1>", lambda e, a=action: self.choose(a))
        if not sel:
            def enter(e, w=f, c=rc):
                set_bg_tree(w, T["hover"])
                c.delete("all")
                c.create_image(d / 2, d / 2, image=self._radio_img(False, T["hover"]))

            def leave(e, w=f, c=rc):
                set_bg_tree(w, T["panel"])
                c.delete("all")
                c.create_image(d / 2, d / 2, image=self._radio_img(False, T["panel"]))

            bind_tree(f, "<Enter>", enter)
            bind_tree(f, "<Leave>", leave)

    def _radio_img(self, sel, bg):
        """Vyhlazený přepínač (kolečko) – vykreslený 4× větší a zmenšený."""
        key = ("radio", sel, bg)
        if key not in self.images:
            d = self.px(16)
            n = d * 4
            im = Image.new("RGBA", (n, n), rgb(bg))
            dr = ImageDraw.Draw(im)
            if sel:
                dr.ellipse((2, 2, n - 3, n - 3), outline=rgb(self.T["accent"]), width=int(n * 0.13))
                dr.ellipse((n * 0.3, n * 0.3, n * 0.7, n * 0.7), fill=rgb(self.T["accent"]))
            else:
                dr.ellipse((2, 2, n - 3, n - 3), outline=rgb(self.T["line"]), width=int(n * 0.08))
            self.images[key] = ImageTk.PhotoImage(im.resize((d, d), Image.LANCZOS), master=self.root)
        return self.images[key]

    def build_editor(self, mode, cur):
        T, px = self.T, self.px
        for ch in self.editor.winfo_children():
            ch.destroy()
        if mode is None:
            self.editor.pack_forget()
            return
        self.editor.pack(side="bottom", fill="x", before=self.act_scroll.cv)
        box = tk.Frame(self.editor, bg=T["panel2"])
        box.pack(fill="x", padx=px(20), pady=px(14))
        if mode == "keys":
            self.label(box, t("editor_keys"), 9, True, fg=T["sub"]).pack(anchor="w")
            line = tk.Frame(box, bg=T["panel2"])
            line.pack(fill="x", pady=(px(6), px(4)))
            self.key_var = tk.StringVar(value=cur[5:] if cur.startswith("keys:") else "")
            ent = tk.Entry(line, textvariable=self.key_var, font=("Segoe UI", 11), bg=T["panel"], fg=T["text"],
                           insertbackground=T["text"], relief="flat", highlightthickness=1,
                           highlightbackground=T["border"], highlightcolor=T["accent"])
            ent.pack(side="left", fill="x", expand=True, ipady=px(5))
            ent.bind("<Return>", lambda e: self.save_custom_keys())
            self.key_entry = ent
            self.button(line, t("record"), self.capture).pack(side="left", padx=(px(8), 0))
            self.button(line, t("save"), self.save_custom_keys, kind="primary").pack(side="left", padx=(px(6), 0))
            self.label(box, t("keys_hint"), 8, fg=T["sub"], wraplength=px(290), justify="left").pack(anchor="w")
        else:
            self.label(box, t("editor_run"), 9, True, fg=T["sub"]).pack(anchor="w")
            self.label(box, cur[4:], 9, wraplength=px(290), justify="left").pack(anchor="w", pady=px(4))
            self.button(box, t("change"), lambda: self.choose("custom_run")).pack(anchor="w")

    def choose(self, action):
        if action == "custom_keys":
            self.build_editor("keys", "keys:")
            self.capture()
            return
        if action == "custom_run":
            p = filedialog.askopenfilename(parent=self.root, title=t("pick_file"))
            if not p:
                return
            action = "run:" + os.path.normpath(p)
        self.set_action(self.control, action)

    def set_action(self, control, action):
        prof = self.cfg["profiles"].setdefault(self.current, {})
        if action == "inherit":
            prof.pop(control, None)
        else:
            prof[control] = action
        self.push_config()
        self.build_actions()
        self._schedule_draw()
        self.status(t("saved"))

    def save_custom_keys(self):
        text = self.key_var.get().strip().lower().replace(" ", "")
        try:
            E.parse_combo(text)
        except ValueError as e:
            self.status(t("bad_shortcut", err=e), error=True)
            return
        self.set_action(self.control, "keys:" + text)

    def capture(self):
        self.capturing = True
        self.key_var.set(t("press_shortcut"))
        self.key_entry.focus_set()
        self.root.bind_all("<KeyPress>", self._on_key)

    def _on_key(self, ev):
        vk = ev.keycode
        if vk in (0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C):
            return "break"
        self.root.unbind_all("<KeyPress>")
        self.capturing = False
        name = E.VK_TO_NAME.get(vk)
        if not name:
            self.key_var.set("")
            self.status(t("key_unknown"), error=True)
            return "break"
        mods = [m for m, bit in (("ctrl", 0x4), ("shift", 0x1), ("alt", 0x20000)) if ev.state & bit]
        self.key_var.set("+".join(mods + [name]))
        self.save_custom_keys()
        return "break"

    def apply_template(self, key):
        tpl = dict(L.TEMPLATES)[key]
        self.cfg["profiles"][self.current] = dict(tpl)
        self.push_config()
        self.build_actions()
        self._schedule_draw()
        self.status(t("tpl_applied", name=t(key)))

    # ================================================================ přidání / odebrání aplikace
    def add_app_dialog(self):
        T, px = self.T, self.px
        dlg = tk.Toplevel(self.root, bg=T["panel"])
        dlg.title(t("add_title"))
        dlg.transient(self.root)
        dlg.geometry(f"{px(500)}x{px(560)}")
        dlg.after(10, lambda: self._titlebar(dlg))
        head = tk.Frame(dlg, bg=T["panel"])
        head.pack(fill="x", padx=px(22), pady=(px(18), px(6)))
        self.label(head, t("add_title"), 14, True).pack(anchor="w")
        self.label(head, t("add_sub"), 9, fg=T["sub"]).pack(anchor="w")
        q = tk.StringVar()
        ent = tk.Entry(head, textvariable=q, font=("Segoe UI", 10), bg=T["panel2"], fg=T["text"],
                       insertbackground=T["text"], relief="flat", highlightthickness=1,
                       highlightbackground=T["border"], highlightcolor=T["accent"])
        ent.pack(fill="x", pady=(px(10), 0), ipady=px(5))
        ent.focus_set()
        bar = tk.Frame(dlg, bg=T["panel"])
        bar.pack(side="bottom", fill="x", padx=px(22), pady=px(16))
        sl = ScrollList(dlg, T["panel"], px(20))
        sl.cv.pack(fill="both", expand=True, padx=px(10))
        skip = {"pythonw.exe", "python.exe", "explorer.exe", "applicationframehost.exe", "textinputhost.exe",
                "shellexperiencehost.exe", "searchhost.exe", "startmenuexperiencehost.exe", "lockapp.exe"}
        apps = [a for a in G.window_apps() if a[0] not in self.cfg["profiles"] and a[0] not in skip]
        for exe, _, path in apps:
            if exe not in self.cfg["app_info"]:
                self.cfg["app_info"][exe] = {"path": path, "name": G.file_description(path) or ""}

        def fill(*_):
            sl.clear()
            needle = q.get().lower()
            for exe, title, path in apps:
                name = self.app_name(exe)
                if needle and needle not in (exe + name + title).lower():
                    continue
                f = tk.Frame(sl.frame, bg=T["panel"], cursor="hand2")
                f.pack(fill="x", padx=px(8), pady=1)
                self.icon_widget(f, exe, T["panel"], 26, path).pack(side="left", padx=px(10), pady=px(7))
                tx = tk.Frame(f, bg=T["panel"])
                tx.pack(side="left", fill="x", expand=True)
                self.label(tx, name, 10, True, anchor="w").pack(anchor="w")
                self.label(tx, f"{exe}  ·  {title[:46]}", 8, fg=T["sub"], anchor="w").pack(anchor="w")
                if exe in G.PLAYERS:
                    self.label(f, t("player_badge"), 8, fg=T["accent"]).pack(side="right", padx=px(12))
                bind_tree(f, "<Button-1>", lambda e, x=exe, p=path: (self.add_app(x, p), dlg.destroy()))
                bind_tree(f, "<Enter>", lambda e, w=f: set_bg_tree(w, T["hover"]))
                bind_tree(f, "<Leave>", lambda e, w=f: set_bg_tree(w, T["panel"]))
            if not sl.frame.winfo_children():
                self.label(sl.frame, t("nothing_found"), 9, fg=T["sub"]).pack(pady=px(20))

        q.trace_add("write", fill)
        fill()

        def browse():
            p = filedialog.askopenfilename(parent=dlg, title=t("pick_program"), filetypes=[(t("programs"), "*.exe")])
            if p:
                self.add_app(os.path.basename(p).lower(), os.path.normpath(p))
                dlg.destroy()

        self.button(bar, t("browse"), browse).pack(side="left")
        self.button(bar, t("close"), dlg.destroy, kind="ghost").pack(side="right")

    def add_app(self, exe, path=None):
        exe = exe.lower()
        if path:
            self.cfg["app_info"][exe] = {"path": path, "name": G.file_description(path) or ""}
        new = exe not in self.cfg["profiles"]
        self.cfg["profiles"].setdefault(exe, {})
        if new and exe in G.PLAYERS:
            self.cfg["profiles"][exe] = dict(dict(L.TEMPLATES)["tpl_player"])
        self.push_config()
        self.select_app(exe)
        if new and exe in G.PLAYERS:
            self.status(t("player_tpl"))

    def remove_app(self):
        if self.current == C.GLOBAL:
            return
        exe = self.current
        self.cfg["profiles"].pop(exe, None)
        self.push_config()
        self.select_app(C.GLOBAL)
        self.status(t("profile_removed", exe=exe))

    def on_enabled(self, value):
        self.cfg["enabled"] = bool(value)
        self.push_config()
        self.status(t("enabled_on") if value else t("enabled_off"))

    def on_autostart(self, value):
        try:
            G.autostart_set(value)
            self.status(t("auto_on") if value else t("auto_off"))
        except OSError as e:
            self.sw_auto.set(G.autostart_get())
            self.status(t("auto_err", err=e), error=True)

    # ================================================================ scéna s myší (Pillow, vyhlazeně)
    def _load_mouse(self):
        try:
            with open(os.path.join(ASSETS, "mouse.json"), encoding="utf-8") as f:
                meta = json.load(f)
            name = "mouse_dark.png" if self.dark else "mouse.png"
            self.mouse_src = Image.open(os.path.join(ASSETS, name)).convert("RGBA")
            self.mouse_hs = meta["hotspots"]
        except (OSError, ValueError, KeyError):
            self.mouse_src = None

    def _mouse_scaled(self, w, h):
        if self._mouse_key != (w, h):
            # zvětšování nad rozlišení zdroje stačí rychlé (víc detailu stejně nepřinese)
            up = w > self.mouse_src.size[0]
            self._mouse_img = self.mouse_src.resize((w, h), Image.BILINEAR if up else Image.LANCZOS)
            self._mouse_key = (w, h)
        return self._mouse_img

    def _schedule_draw(self, _=None):
        if self._draw_job:
            self.root.after_cancel(self._draw_job)
        self._draw_job = self.root.after(20, self.draw)

    def _canvas_click(self, e):
        for x1, y1, x2, y2, ctl in self._hits:
            if x1 <= e.x <= x2 and y1 <= e.y <= y2:
                self.select_control(ctl)
                return

    def _canvas_motion(self, e):
        hit = any(x1 <= e.x <= x2 and y1 <= e.y <= y2 for x1, y1, x2, y2, _ in self._hits)
        self.cv.configure(cursor="hand2" if hit else "")

    def draw(self):
        self._draw_job = None
        if self.page != "buttons" or self.mouse_src is None:
            return
        cv, T, px = self.cv, self.T, self.px
        cv.delete("all")
        self._hits = []
        Wd, Hd = cv.winfo_width(), cv.winfo_height()
        if Wd < 200 or Hd < 150:
            return
        SS = 2
        sw, sh = self.mouse_src.size
        cw = px(222)
        # strop velikosti: na velké obrazovce se myš nezvětšuje donekonečna (rychlost i vzhled)
        iw = min((Wd - px(24) - cw - px(70)) / 0.67, Hd * 0.9 * sw / sh, Wd * 0.95, px(820))
        k = iw / sw
        ih = sh * k
        free = Wd - (iw * 0.67 + px(70) + cw)
        ox, oy = max(px(8), free / 2), (Hd - ih) / 2 + px(20)
        hs = {n: (ox + x * k, oy + y * k) for n, (x, y) in self.mouse_hs.items()}
        ctl, flash = self.control, self.flash

        def clamp(x, y, w, h):
            return max(px(6), min(x, Wd - w - px(6))), max(px(6), min(y, Hd - h - px(6))), w, h

        row_h, head_h = px(36), px(34)
        wb = clamp(hs["x1"][0] + px(64), hs["h"][1] - (head_h + 2 * row_h + px(10)) - px(14), cw,
                   head_h + 2 * row_h + px(10))
        x1b = clamp(hs["x1"][0] + px(64), max(hs["x1"][1] + px(4), wb[1] + wb[3] + px(12)), cw, px(66))
        x2b = clamp(hs["x2"][0] - px(64) - cw, hs["x2"][1] + px(22), cw, px(66))
        wheel_ctls = ("hright", "hleft")  # nahoře „nahoru“, dole „dolů“

        def state(ctls):
            return any(c == flash for c in ctls), any(c == ctl for c in ctls)

        # ---------- obraz (2× a zmenšit = vyhlazené hrany) – jen oblast kolem myši a karet
        pad = px(12)
        rx0 = int(max(0, min(ox, x2b[0], wb[0], x1b[0]) - pad))
        ry0 = int(max(0, min(oy, wb[1], x1b[1], x2b[1]) - pad))
        rx1 = int(min(Wd, max(ox + iw, wb[0] + wb[2], x1b[0] + x1b[2], x2b[0] + x2b[2]) + pad))
        ry1 = int(min(Hd, max(oy + ih, wb[1] + wb[3], x1b[1] + x1b[3], x2b[1] + x2b[3]) + pad))
        base_key = (rx1 - rx0, ry1 - ry0, int(iw), int(ih), int(ox) - rx0, int(oy) - ry0, T["bg"])
        if getattr(self, "_base_key", None) != base_key:  # podklad s fotkou myši se drží v mezipaměti
            base = Image.new("RGBA", ((rx1 - rx0) * SS, (ry1 - ry0) * SS), rgb(T["bg"]))
            base.alpha_composite(self._mouse_scaled(int(iw * SS), int(ih * SS)),
                                 (int((ox - rx0) * SS), int((oy - ry0) * SS)))
            self._base, self._base_key = base, base_key
        scene = self._base.copy()
        d = ImageDraw.Draw(scene, "RGBA")  # „RGBA“ = poloprůhledné tahy se míchají s fotkou

        def S(*v):
            return [(a - (rx0 if i % 2 == 0 else ry0)) * SS for i, a in enumerate(v)]

        r = px(9)
        for name, box, ctls in (("h", wb, wheel_ctls), ("x1", x1b, ("x1",)), ("x2", x2b, ("x2",))):
            fl, sel = state(ctls)
            p = hs[name]
            x, y, w, h = box
            q = (min(max(p[0], x), x + w), min(max(p[1], y), y + h))
            dx, dy = q[0] - p[0], q[1] - p[1]
            dist = math.hypot(dx, dy) or 1
            start = (p[0] + dx / dist * (r + px(2)), p[1] + dy / dist * (r + px(2)))
            col = T["ok"] if fl else T["accent"] if sel else T["lead"]
            lw = px(2) if (fl or sel) else max(1, px(1.5))
            d.line(S(*start, *q), fill=rgb(T["halo"], 150), width=int((lw + px(2.5)) * SS))
            d.line(S(*start, *q), fill=rgb(col), width=int(lw * SS))

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
        for c, box in (("x1", x1b), ("x2", x2b)):
            fl, sel = c == flash, c == ctl
            fill = T["ok"] if fl else T["accent"] if sel else T["card"]
            card(box, fill, fill if (fl or sel) else T["border"], 1)

        for name, ctls in (("h", wheel_ctls), ("x1", ("x1",)), ("x2", ("x2",))):
            fl, sel = state(ctls)
            x, y = hs[name]
            col = T["ok"] if fl else T["accent"] if sel else T["marker"]
            d.ellipse(S(x - r - px(2.5), y - r - px(2.5), x + r + px(2.5), y + r + px(2.5)),
                      outline=rgb(T["halo"], 140), width=int(px(2.5) * SS))
            d.ellipse(S(x - r, y - r, x + r, y + r), outline=rgb(col), width=int(max(2, px(2)) * SS),
                      fill=rgb(col) if (fl or sel) else None)
            if fl or sel:
                d.ellipse(S(x - r * 0.4, y - r * 0.4, x + r * 0.4, y + r * 0.4), fill=(255, 255, 255, 255))

        self._scene = ImageTk.PhotoImage(scene.reduce(SS), master=self.root)
        cv.create_image(rx0, ry0, image=self._scene, anchor="nw")

        # ---------- texty (Tk je vyhlazuje sám) a klikací oblasti
        def fit(text, font, maxw):
            while font.measure(text) > maxw and len(text) > 3:
                text = text[:-2] + "…"
            return text

        def effective(c):
            raw = self.raw_action(c)
            return (self.raw_action(c, C.GLOBAL), True) if raw == "inherit" else (raw, False)

        x, y, w, h = wb
        cv.create_text(x + px(14), y + head_h / 2 + px(3), text=t("thumb_wheel"), anchor="w",
                       font=self.f_cardsub, fill=T["sub"])
        for i, (c, arrow) in enumerate(zip(wheel_ctls, ("▲", "▼"))):
            ry = y + head_h + i * row_h
            on = c == ctl or c == flash
            fg = "#FFFFFF" if on else T["text"]
            eff, inh = effective(c)
            cv.create_text(x + px(18), ry + row_h / 2, text=arrow, anchor="w", font=self.f_cardsub, fill=fg)
            cv.create_text(x + px(40), ry + row_h / 2, anchor="w", font=self.f_card, fill=fg,
                           text=fit(L.action_short(eff) + (f"  ·  {t('inherited')}" if inh else ""),
                                    self.f_card, w - px(54)))
            self._hits.append((x, ry, x + w, ry + row_h, c))
        self._hits.append((x, y, x + w, y + h, ctl if ctl in wheel_ctls else "hright"))

        for c, box, arrow in (("x1", x1b, "◀"), ("x2", x2b, "▶")):
            x, y, w, h = box
            on = c == ctl or c == flash
            eff, inh = effective(c)
            fg = "#FFFFFF" if on else T["text"]
            sub_fg = "#E6EEFB" if on else T["sub"]
            cv.create_text(x + px(14), y + px(23), anchor="w", font=self.f_card, fill=fg,
                           text=fit(L.action_short(eff), self.f_card, w - px(28)))
            cv.create_text(x + px(14), y + px(46), anchor="w", font=self.f_cardsub, fill=sub_fg,
                           text=f"{arrow}  {L.control(c)}" + (f"  ·  {t('inherited')}" if inh else ""))
            self._hits.append((x, y, x + w, y + h, c))

        for name, target in (("h", ctl if ctl in wheel_ctls else "hright"), ("x1", "x1"), ("x2", "x2")):
            x, y = hs[name]
            rr = r + px(6)
            self._hits.append((x - rr, y - rr, x + rr, y + rr, target))

    # ================================================================ stránka Myš ve Windows
    def _apply(self, fn, *args, msg=None):
        try:
            fn(*args)
            self.status(msg or t("saved_win"))
            return True
        except OSError as e:
            self.status(t("failed", err=e), error=True)
            return False

    def _section(self, parent, title, sub=None):
        T, px = self.T, self.px
        self.label(parent, title, 13, True, bg=T["bg"]).pack(anchor="w", pady=(px(26), px(2)))
        if sub:
            self.label(parent, sub, 9, fg=T["sub"], bg=T["bg"], wraplength=px(760), justify="left").pack(anchor="w")
        card = tk.Frame(parent, bg=T["panel"], highlightthickness=1, highlightbackground=T["border"])
        card.pack(fill="x", pady=(px(10), 0))
        card._rows = 0
        return card

    def _row(self, card, title, sub, build):
        T, px = self.T, self.px
        if card._rows:
            tk.Frame(card, bg=T["border"], height=1).pack(fill="x", padx=px(18))
        card._rows += 1
        row = tk.Frame(card, bg=T["panel"])
        row.pack(fill="x", padx=px(20), pady=px(13))
        right = tk.Frame(row, bg=T["panel"])
        right.pack(side="right")
        build(right)
        tx = tk.Frame(row, bg=T["panel"])
        tx.pack(side="left", fill="x", expand=True)
        self.label(tx, title, 10, True, anchor="w").pack(anchor="w")
        if sub:
            self.label(tx, sub, 8, fg=T["sub"], anchor="w", justify="left", wraplength=px(430)).pack(anchor="w")
        return row

    def _switch(self, parent, value, fn, also_right=False):
        sw = Switch(parent, self, value, fn)
        sw.pack(side="right")
        if also_right:
            sw.bind("<Button-3>", sw.toggle)
        return sw

    def build_win_page(self):
        T, px = self.T, self.px
        self.win_scroll.clear()
        outer = tk.Frame(self.win_scroll.frame, bg=T["bg"])
        outer.pack(fill="x", padx=px(48), pady=(px(6), px(30)))
        v = WS.read_all()

        intro = tk.Frame(outer, bg=T["bg"])
        intro.pack(fill="x", pady=(px(18), 0))
        self.label(intro, t("win_title"), 17, True, bg=T["bg"]).pack(anchor="w")
        self.label(intro, t("win_intro"), 9, fg=T["sub"], bg=T["bg"], wraplength=px(760), justify="left").pack(anchor="w")

        self._build_dpi(outer)

        c = self._section(outer, t("sec_pointer"))
        self._row(c, t("speed"), t("speed_sub"),
                  lambda p: Slider(p, self, 1, 20, v["speed"], lambda x: self._apply(WS.set_speed, x)).pack_with_value())
        self._row(c, t("accel"), t("accel_sub"),
                  lambda p: self._switch(p, v["accel"], lambda on: self._apply(WS.set_accel, on)))

        c = self._section(outer, t("sec_scroll"))
        lines = {"v": v["lines"] if v["lines"] > 0 else 3}
        holder = {}

        def set_lines(x):
            lines["v"] = x
            if not holder["sw"].value:
                self._apply(WS.set_lines, x)

        self._row(c, t("lines"), t("lines_sub"),
                  lambda p: Slider(p, self, 1, 20, lines["v"], set_lines).pack_with_value())
        self._row(c, t("page"), t("page_sub"),
                  lambda p: holder.setdefault("sw", self._switch(
                      p, v["lines"] < 0, lambda on: self._apply(WS.set_lines, -1 if on else lines["v"]))))
        self._row(c, t("hover"), t("hover_sub"),
                  lambda p: self._switch(p, v["hover_scroll"], lambda on: self._apply(WS.set_hover_scroll, on)))
        self._row(c, t("chars"), t("chars_sub"),
                  lambda p: Slider(p, self, 1, 20, v["chars"], lambda x: self._apply(WS.set_chars, x)).pack_with_value())

        c = self._section(outer, t("sec_btn"))
        self._row(c, t("swap"), t("swap_sub"),
                  lambda p: self._switch(p, v["swap"], lambda on: self._apply(WS.set_swap, on), also_right=True))

        def dbl(p):
            test = tk.Canvas(p, width=px(110), height=px(40), bg=T["panel"], highlightthickness=0, cursor="hand2")
            st = {"on": False}

            def paint():
                test.delete("all")
                rrect(test, 2, 2, px(110) - 2, px(40) - 2, px(10), fill=T["ok"] if st["on"] else T["panel2"],
                      outline=T["border"])
                test.create_text(px(55), px(20), text=t("dbl_ok") if st["on"] else t("dbl_test"),
                                 fill="#FFFFFF" if st["on"] else T["sub"], font=("Segoe UI", 9))

            def flip(_):
                st["on"] = not st["on"]
                paint()

            test.bind("<Double-Button-1>", flip)
            paint()
            test.pack(side="right", padx=(px(16), 0))
            Slider(p, self, 200, 900, v["dblclick"], lambda x: self._apply(WS.set_dblclick, x),
                   fmt=lambda x: f"{x} ms", step=10, width=200).pack_with_value()

        self._row(c, t("dbl"), t("dbl_sub"), dbl)

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

    # ---------- DPI
    def _build_dpi(self, outer):
        T, px = self.T, self.px
        c = self._section(outer, t("sec_dpi"), t("dpi_sub2"))
        box = tk.Frame(c, bg=T["panel"])
        box.pack(fill="x", padx=px(20), pady=px(16))
        res = tk.Frame(box, bg=T["panel"])
        res.pack(side="right", padx=(px(20), 0))
        self.gauge = tk.Canvas(res, width=px(400), height=px(210), bg=T["panel"], highlightthickness=0)
        self.gauge.pack()
        self.dpi_big = self.label(res, "— DPI", 20, True)
        self.dpi_big.pack()
        self.dpi_detail = self.label(res, "", 8, fg=T["sub"])
        self.dpi_detail.pack()
        left = tk.Frame(box, bg=T["panel"])
        left.pack(side="left", fill="x", expand=True)
        # automatické sledování: kotva = aktuální stupeň
        self.label(left, t("dpi_now"), 9, True, fg=T["sub"]).pack(anchor="w")
        lrow = tk.Frame(left, bg=T["panel"])
        lrow.pack(anchor="w", pady=(px(6), px(8)))
        self._level_chips = []
        for lv in DPI_LEVELS:
            ch = tk.Label(lrow, text=str(lv), font=("Segoe UI Semibold", 11), cursor="hand2",
                          padx=px(12), pady=px(6), bg=T["panel2"], fg=T["text"])
            ch.pack(side="left", padx=(0, px(6)))
            ch.bind("<Button-1>", lambda e, v=lv: self._dpi_anchor(v))
            self._level_chips.append((lv, ch))
        self.dpi_track_lbl = self.label(left, "", 9, fg=T["sub"], wraplength=px(520), justify="left")
        self.dpi_track_lbl.pack(anchor="w")
        tk.Frame(left, bg=T["border"], height=1).pack(fill="x", pady=(px(16), px(12)))
        self.label(left, t("dpi_exact"), 9, True, fg=T["sub"]).pack(anchor="w", pady=(0, px(6)))
        drow = tk.Frame(left, bg=T["panel"])
        drow.pack(anchor="w")
        self.label(drow, t("dpi_distance"), 9, True, fg=T["sub"]).pack(side="left", padx=(0, px(10)))
        self._dpi_chips = []
        for cm, key in DPI_DISTANCES:
            ch = tk.Label(drow, text=t(key), font=("Segoe UI Semibold", 9), cursor="hand2", padx=px(10), pady=px(4))
            ch.pack(side="left", padx=(0, px(6)))
            ch.bind("<Button-1>", lambda e, v=cm: self._dpi_set_dist(v))
            self._dpi_chips.append((cm, ch))
        self.dpi_msg = self.label(left, "", 10, wraplength=px(480), justify="left")
        self.dpi_msg.pack(anchor="w", pady=(px(12), px(10)))
        btns = tk.Frame(left, bg=T["panel"])
        btns.pack(anchor="w")
        self.dpi_btn = self.button(btns, t("dpi_measure"), self._dpi_start, kind="primary")
        self.dpi_btn.pack(side="left")
        self.dpi_cancel_btn = self.button(btns, t("cancel"), self._dpi_cancel, kind="ghost")
        self._dpi_set_dist(self.dpi_cm)
        self._dpi_show()
        self._dpi_refresh()

    def _dpi_set_dist(self, cm):
        self.dpi_cm = cm
        for v, ch in self._dpi_chips:
            on = v == cm
            ch.configure(bg=self.T["accent"] if on else self.T["panel2"], fg=self.T["on_accent"] if on else self.T["sub"])
        if self.dpi_state == "moving":
            self.dpi_msg.configure(text=t("dpi_step2", d=self._dist_text()))

    def _dist_text(self, cm=None):
        cm = self.dpi_cm if cm is None else cm
        return t(dict(DPI_DISTANCES).get(cm, "dpi_d_ruler"))

    def _draw_gauge(self, measured=None, level=None):
        """Budík jako na obrázku výrobce: oblouk se 6 stupni, ručička na naměřenou hodnotu."""
        T, px, g = self.T, self.px, self.gauge
        g.delete("all")
        W_, H_ = px(400), px(210)
        SS = 3
        im = Image.new("RGBA", (W_ * SS, H_ * SS), rgb(T["panel"]))
        d = ImageDraw.Draw(im, "RGBA")
        cx, cy, R = W_ / 2, H_ * 0.93, H_ * 0.72
        a0, a1 = 160.0, 20.0  # úhel pro 800 a 4800 DPI

        def ang(pos):  # pos = index stupně (lze desetinně)
            return math.radians(a0 + (a1 - a0) * pos / (len(DPI_LEVELS) - 1))

        def pt(a, r):
            return cx + r * math.cos(a), cy - r * math.sin(a)

        def S(*v):
            return [x * SS for x in v]

        box = S(cx - R, cy - R, cx + R, cy + R)
        lw = int(px(7) * SS)
        d.arc(box, start=-(a0 + 8), end=-(a1 - 8), fill=rgb(T["switch_off"]), width=lw)
        if level:
            i = DPI_LEVELS.index(level)
            d.arc(box, start=-(a0 + 8), end=-math.degrees(ang(i)), fill=rgb(T["accent"]), width=lw)
        for i in range(len(DPI_LEVELS) - 1):  # drobné dílky mezi stupni
            for f in (0.25, 0.5, 0.75):
                a = ang(i + f)
                d.line(S(*pt(a, R - px(14)), *pt(a, R - px(20))), fill=rgb(T["sub"], 140), width=int(px(1.5) * SS))
        for i, lv in enumerate(DPI_LEVELS):
            a = ang(i)
            on = lv == level
            d.line(S(*pt(a, R - px(12)), *pt(a, R - px(26))), fill=rgb(T["accent"] if on else T["text"]),
                   width=int(px(3) * SS))
        if measured:
            pos = dpi_pos(measured)
            a = ang(pos)
            col = rgb(T["accent"])
            d.line(S(cx, cy, *pt(a, R - px(30))), fill=col, width=int(px(3.5) * SS))
            d.ellipse(S(cx - px(8), cy - px(8), cx + px(8), cy + px(8)), fill=col)
            d.ellipse(S(cx - px(3), cy - px(3), cx + px(3), cy + px(3)), fill=rgb(T["panel"]))
        self._gauge_img = ImageTk.PhotoImage(im.reduce(SS), master=self.root)
        g.create_image(0, 0, image=self._gauge_img, anchor="nw")
        for i, lv in enumerate(DPI_LEVELS):
            x, y = pt(ang(i), R + px(20))
            on = lv == level
            g.create_text(x, y, text=str(lv), font=("Segoe UI Semibold", 11 if on else 9),
                          fill=T["accent"] if on else T["sub"])

    def _dpi_show(self):
        st = self.engine.tracker.status() if self.engine.tracker else {}
        self._dpi_drawn = (st.get("level"), st.get("estimate") and round(st["estimate"], -1))
        saved = self.cfg.get("dpi") or {}
        if st.get("level") and not self.dpi_result:
            est = st.get("estimate") if not st.get("learning") else None
            self.dpi_big.configure(text=f"{st['level']} DPI", fg=self.T["accent"])
            self.dpi_detail.configure(text=(f"≈ {est} DPI" if est else ""))
            self._draw_gauge(est or st["level"], st["level"])
        elif self.dpi_result:
            level, measured, counts, cm, conf = self.dpi_result
            self.dpi_big.configure(text=f"{level} DPI", fg=self.T["accent"])
            self.dpi_detail.configure(text=t("dpi_measured", dpi=measured, counts=counts, d=self._dist_text(cm)))
            self.dpi_msg.configure(text=t("dpi_sure") if conf >= 0.4 else t("dpi_unsure"),
                                   fg=self.T["ok"] if conf >= 0.4 else self.T["warn"])
            self._draw_gauge(measured, level)
        elif saved.get("level"):
            self.dpi_big.configure(text=f"{saved['level']} DPI", fg=self.T["text"])
            self.dpi_detail.configure(text=t("dpi_saved", when=saved.get("when", "")))
            self._draw_gauge(saved.get("measured"), saved["level"])
        else:
            self._draw_gauge()
        if self.dpi_state == "idle":
            self.dpi_cancel_btn.pack_forget()
            self.dpi_btn.configure(text=t("dpi_again") if self.dpi_result else t("dpi_measure"))
            if not self.dpi_result and not self.dpi_msg.cget("text"):
                self.dpi_msg.configure(text="")

    def _dpi_start(self):
        self.dpi_state = "ready"
        self.dpi_msg.configure(text="①  " + t("dpi_step1"), fg=self.T["text"])
        self.dpi_cancel_btn.pack(side="left", padx=px_(self, 8))
        self.root.bind_all("<space>", self._dpi_space)
        self.root.focus_force()

    def _dpi_space(self, _=None):
        if self.dpi_state == "ready":
            self.engine.measure_begin()
            self.dpi_state = "moving"
            self.dpi_msg.configure(text="②  " + t("dpi_step2", d=self._dist_text()))
        elif self.dpi_state == "moving":
            dx, dy, n = self.engine.measure_end()
            counts = int(round(math.hypot(dx, dy)))
            self.root.unbind_all("<space>")
            self.dpi_state = "idle"
            measured = int(round(counts / (self.dpi_cm / 2.54)))
            if counts < 50 or not (DPI_LEVELS[0] * 0.75 <= measured <= DPI_LEVELS[-1] * 1.33):
                # mimo rozsah myši = nepovedené měření (posun nebyl o celou vzdálenost apod.)
                self.dpi_msg.configure(text=t("dpi_nomove") if counts < 50 else t("dpi_outside", dpi=measured),
                                       fg=self.T["warn"])
            else:
                level, conf = snap_dpi(measured)
                self.dpi_result = (level, measured, counts, self.dpi_cm, conf)
                import time as _time
                self.cfg["dpi"] = {"level": level, "measured": measured,
                                   "when": _time.strftime("%d.%m.%Y %H:%M")}
                self.engine.tracker.anchor(level)  # přesné měření zároveň ukotví sledování
                self._save_tracker()
                self._update_dev_label()
            self._dpi_show()
            self._dpi_refresh()
        return "break"

    def _dpi_cancel(self):
        if self.dpi_state != "idle":
            self.engine.measure_end()
            self.root.unbind_all("<space>")
            self.dpi_state = "idle"
            try:
                self.dpi_msg.configure(text="")
                self._dpi_show()
            except tk.TclError:
                pass

    # ---------- kurzory
    def _scheme_tiles(self, grid, current):
        T, px = self.T, self.px
        schemes = WS.list_schemes()
        names = {s["name"] for s in schemes}
        tiles = [None] + schemes
        cols = 3
        for i in range(cols):
            grid.columnconfigure(i, weight=1, uniform="s")
        isz = px(32)
        chip = "#F3F4F7"
        for i, sch in enumerate(tiles):
            name = t("scheme_default") if sch is None else sch["name"]
            sel = (sch is None and current not in names) or (sch is not None and sch["name"] == current)
            bg = T["accent_soft"] if sel else T["panel2"]
            tile = tk.Frame(grid, bg=bg, cursor="hand2", highlightthickness=2 if sel else 1,
                            highlightbackground=T["accent"] if sel else T["border"])
            tile.grid(row=i // cols, column=i % cols, sticky="nsew", padx=px(5), pady=px(5))
            icons = tk.Frame(tile, bg=chip)
            icons.pack(fill="x", padx=px(10), pady=(px(10), px(6)), ipadx=px(4), ipady=px(4))
            files = WS.DEFAULT_FILES if sch is None else sch["files"]
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
                    tk.Label(icons, image=self.images[key], bg=chip).pack(side="left", padx=(px(6), 0))
            nrow = tk.Frame(tile, bg=bg)
            nrow.pack(fill="x", padx=px(12), pady=(0, px(10)))
            self.label(nrow, name, 9, sel, fg=T["accent"] if sel else T["text"], bg=bg, anchor="w").pack(side="left")
            bind_tree(tile, "<Button-1>", lambda e, s=sch: self._pick_scheme(s))
            if sch is not None and sch["source"] == 1:
                x = self.label(nrow, "✕", 9, fg=T["sub"], bg=bg, cursor="hand2")
                x.pack(side="right")
                x.bind("<Button-1>", lambda e, s=sch: (self._delete_scheme(s), "break")[1])

    def _rebuild_keep_scroll(self):
        y = self.win_scroll.cv.yview()[0]
        self.build_win_page()
        self.root.after(30, lambda: self.win_scroll.cv.yview_moveto(y))

    def _pick_scheme(self, sch):
        if self._apply(WS.apply_scheme, sch, msg=t("scheme_applied")):
            self._rebuild_keep_scroll()

    def _delete_scheme(self, sch):
        if not messagebox.askyesno(t("delete"), t("delete_scheme_q", name=sch["name"]), parent=self.root):
            return
        was = WS.current_scheme() == sch["name"]
        try:
            WS.delete_scheme(sch["name"])
            if was:
                WS.apply_scheme(None)
        except OSError as e:
            self.status(t("failed", err=e), error=True)
        self._rebuild_keep_scroll()

    def install_scheme(self):
        paths = filedialog.askopenfilenames(parent=self.root, title=t("install_scheme"),
                                            filetypes=[(t("install_types"), "*.zip *.inf *.cur *.ani"),
                                                       ("*", "*.*")])
        if not paths:
            return
        try:
            sch = WS.install_pack(list(paths))
            WS.apply_scheme(sch)
            self.status(t("installed", name=sch["name"]))
        except (OSError, ValueError, KeyError) as e:
            self.status(t("install_err", err=e), error=True)
        except Exception as e:  # poškozený zip apod.
            self.status(t("install_err", err=e), error=True)
        self._rebuild_keep_scroll()

    def reset_windows(self):
        if not messagebox.askyesno(t("reset"), t("reset_q"), parent=self.root):
            return
        d = WS.DEFAULTS
        steps = [(WS.set_speed, d["speed"]), (WS.set_accel, d["accel"]), (WS.set_lines, d["lines"]),
                 (WS.set_chars, d["chars"]), (WS.set_swap, d["swap"]), (WS.set_dblclick, d["dblclick"]),
                 (WS.set_hover_scroll, d["hover_scroll"]), (WS.set_trails, d["trails"]),
                 (WS.set_cursor_size, d["cursor_size"]), (WS.apply_scheme, None)]
        for name in ("sonar", "vanish", "snap"):
            steps.append((lambda on, n=name: WS.set_bool(n, on), d[name]))
        errors = 0
        for fn, arg in steps:
            try:
                fn(arg)
            except OSError:
                errors += 1
        self.build_win_page()
        self.status(t("reset_done") if not errors else t("reset_partial", n=errors), error=bool(errors))

    # ================================================================ okno
    def _set_win_icon(self, win):
        """Ikona okna přímo přes Win32 (titulek + hlavní panel)."""
        import ctypes
        from ctypes import wintypes as W
        u = ctypes.windll.user32
        u.LoadImageW.restype = W.HANDLE
        u.LoadImageW.argtypes = [W.HINSTANCE, W.LPCWSTR, W.UINT, ctypes.c_int, ctypes.c_int, W.UINT]
        u.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        u.SetClassLongPtrW.argtypes = [W.HWND, ctypes.c_int, ctypes.c_ssize_t]
        try:
            hwnd = E.u32.GetParent(win.winfo_id()) or win.winfo_id()
            ico = os.path.join(ASSETS, "app.ico")
            if not hasattr(self, "_hicons"):
                big = u.LoadImageW(None, ico, 1, u.GetSystemMetrics(11), u.GetSystemMetrics(12), 0x10)
                small = u.LoadImageW(None, ico, 1, u.GetSystemMetrics(49), u.GetSystemMetrics(50), 0x10)
                self._hicons = (big, small)
            big, small = self._hicons
            u.SendMessageW(hwnd, 0x0080, 1, big or 0)    # WM_SETICON, ICON_BIG
            u.SendMessageW(hwnd, 0x0080, 0, small or 0)  # ICON_SMALL
            u.SetClassLongPtrW(hwnd, -14, big or 0)      # GCLP_HICON
            u.SetClassLongPtrW(hwnd, -34, small or 0)    # GCLP_HICONSM
        except Exception:
            pass

    def _titlebar(self, win):
        super()._titlebar(win)
        self._set_win_icon(win)

    def _update_dev_label(self):
        ok = E.device_present(self.cfg.get("device_match", ""))
        tr = self.engine.tracker
        dpi = tr.level if tr else None
        text = (t("dev_ok") if ok else t("dev_missing")) + (f"  ·  {dpi} DPI" if ok and dpi else "")
        self.dev_lbl.configure(text=text, fg=self.T["ok"] if ok else self.T["warn"])

    def show(self):
        self._update_dev_label()
        self.sw_auto.set(G.autostart_get())
        self.root.deiconify()
        self._titlebar(self.root)
        self.root.lift()
        self.root.focus_force()
        if self.page == "win":
            self.build_win_page()

    def hide(self):
        self._dpi_cancel()
        self.root.withdraw()

    def quit(self):
        self._save_tracker()
        super().quit()

    def run(self, show=False):
        if "--page-win" in sys.argv:
            self.root.after(300, lambda: self.set_page("win"))
        super().run(show)


def px_(app, n):
    return app.px(n)
