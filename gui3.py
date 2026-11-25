"""Okno nastavení v3 – fotka myši se štítky (styl Logi Options+), hledání akcí, stránka „Myš ve Windows“.

Navazuje na gui2.App (profily, akce, šablony, komunikace s enginem) a mění vzhled.
"""
import ctypes
import json
import os
import tkinter as tk
from tkinter import messagebox

import config as C
import gui2 as G
import winsettings as WS
from gui2 import (CONTROL_LABEL, ScrollList, Switch, bind_tree, rrect, set_bg_tree, short_label,
                  split_label)

try:
    from PIL import Image, ImageTk
except ImportError:  # bez Pillow se použije kreslená myš z gui2
    Image = ImageTk = None

ASSETS = os.path.join(C.APP_DIR, "assets")

G.LIGHT.update(card="#FFFFFF", marker="#1B1F27", tab_on="#1B1F27")
G.DARK.update(card="#262A31", marker="#E8EAEE", tab_on="#FFFFFF")


def hicon_png(hicon, size, destroy=True, bg=(243, 244, 247)):
    """Vykreslí HICON/HCURSOR na neprůhledné pozadí bg do PNG (kvůli inverzním/černým kurzorům)."""
    hdc = G.gdi.CreateCompatibleDC(None)
    bmi = G.BITMAPINFOHEADER(40, size, -size, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    hbm = G.gdi.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    old = G.gdi.SelectObject(hdc, hbm)
    try:
        fill = bytes((bg[2], bg[1], bg[0], 255)) * (size * size)
        ctypes.memmove(bits, fill, len(fill))
        G.E.u32.DrawIconEx(hdc, 0, 0, hicon, size, size, 0, None, 3)
        px = bytearray(ctypes.string_at(bits, size * size * 4))
        px[3::4] = b"\xff" * (size * size)
    finally:
        G.gdi.SelectObject(hdc, old)
        G.gdi.DeleteObject(hbm)
        G.gdi.DeleteDC(hdc)
        if destroy:
            G.E.u32.DestroyIcon(hicon)
    px[0::4], px[2::4] = px[2::4], px[0::4]
    return G.png_bytes(size, size, bytes(px))


class Slider(tk.Canvas):
    """Plochý posuvník: hodnota se ukazuje průběžně, uloží se po puštění."""

    def __init__(self, parent, app, lo, hi, value, command, fmt=str, step=1, width=260):
        self.app, self.lo, self.hi, self.step = app, lo, hi, step
        self.command, self.fmt = command, fmt
        self.w, self.h = app.px(width), app.px(26)
        super().__init__(parent, width=self.w, height=self.h, bg=parent["bg"], highlightthickness=0, cursor="hand2")
        self.value = value
        self.out = tk.Label(parent, font=("Segoe UI Semibold", 10), bg=parent["bg"], fg=app.T["text"],
                            width=7, anchor="e")
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", lambda e: self.command(self.value))
        self.draw()

    def pack_with_value(self, **kw):
        self.pack(side="left", **kw)
        self.out.pack(side="left", padx=(self.app.px(8), 0))

    def _drag(self, e):
        pad = self.h / 2
        f = min(1.0, max(0.0, (e.x - pad) / (self.w - 2 * pad)))
        v = self.lo + round(f * (self.hi - self.lo) / self.step) * self.step
        if v != self.value:
            self.value = v
            self.draw()

    def draw(self):
        T, S = self.app.T, self.app.S
        self.delete("all")
        pad, my = self.h / 2, self.h / 2
        f = (self.value - self.lo) / (self.hi - self.lo) if self.hi > self.lo else 0
        x = pad + f * (self.w - 2 * pad)
        lw = max(2, int(4 * S))
        self.create_line(pad, my, self.w - pad, my, fill=T["switch_off"], width=lw, capstyle="round")
        self.create_line(pad, my, x, my, fill=T["accent"], width=lw, capstyle="round")
        r = 8 * S
        self.create_oval(x - r, my - r, x + r, my + r, fill="#FFFFFF", outline=T["accent"], width=max(2, int(2 * S)))
        self.out.configure(text=self.fmt(self.value))


class App(G.App):
    def __init__(self):
        self.page = "buttons"
        self.mouse_src = None
        self._mouse_key = None
        self._search_placeholder = True
        super().__init__()

    # ================================================================ stavba
    def _build(self):
        T, px, r = self.T, self.px, self.root
        r.geometry(f"{px(1180)}x{px(720)}")
        r.minsize(px(1040), px(640))
        self._load_mouse()

        # ---- hlavička: logo, název, záložky, přepínače
        hdr = tk.Frame(r, bg=T["panel"])
        hdr.pack(fill="x")
        inner = tk.Frame(hdr, bg=T["panel"])
        inner.pack(fill="x", padx=px(20))
        s = px(34)
        raw = C._render(s)[40:40 + s * s * 4]
        rows = [raw[i * s * 4:(i + 1) * s * 4] for i in range(s)][::-1]
        lp = bytearray(b"".join(rows))
        lp[0::4], lp[2::4] = lp[2::4], lp[0::4]
        import base64
        self.logo = tk.PhotoImage(data=base64.b64encode(G.png_bytes(s, s, bytes(lp))).decode())
        tk.Label(inner, image=self.logo, bg=T["panel"]).pack(side="left", pady=px(12))
        tb = tk.Frame(inner, bg=T["panel"])
        tb.pack(side="left", padx=px(12))
        self.label(tb, "Tecknet TK-MS029", 15, True).pack(anchor="w")
        self.dev_lbl = self.label(tb, "", 9, fg=T["sub"])
        self.dev_lbl.pack(anchor="w")

        tabs = tk.Frame(inner, bg=T["panel"])
        tabs.pack(side="left", padx=(px(40), 0), fill="y")
        self.tabs = {}
        for key, text in (("buttons", "Tlačítka"), ("win", "Myš ve Windows")):
            f = tk.Frame(tabs, bg=T["panel"], cursor="hand2")
            f.pack(side="left", fill="y", padx=px(4))
            lab = tk.Label(f, text=text, font=("Segoe UI Semibold", 11), bg=T["panel"], fg=T["sub"])
            lab.pack(side="top", padx=px(12), pady=(px(22), px(14)))
            und = tk.Frame(f, bg=T["panel"], height=px(3))
            und.pack(side="bottom", fill="x", padx=px(8))
            bind_tree(f, "<Button-1>", lambda e, k=key: self.set_page(k))
            self.tabs[key] = (lab, und)

        def switch(text, value, cmd):
            box = tk.Frame(inner, bg=T["panel"])
            box.pack(side="right", padx=(px(22), 0))
            sw = Switch(box, self, value, cmd)
            sw.pack(side="left")
            self.label(box, text, 10).pack(side="left", padx=(px(8), 0))
            return sw

        self.sw_auto = switch("Spustit po startu Windows", G.autostart_get(), self.on_autostart)
        self.sw_enabled = switch("Přemapování zapnuto", self.cfg.get("enabled", True), self.on_enabled)
        tk.Frame(r, bg=T["border"], height=1).pack(fill="x")

        # ---- patička
        foot = tk.Frame(r, bg=T["panel"])
        foot.pack(side="bottom", fill="x")
        tk.Frame(r, bg=T["border"], height=1).pack(side="bottom", fill="x")
        fi = tk.Frame(foot, bg=T["panel"])
        fi.pack(fill="x", padx=px(20), pady=px(8))
        self.label(fi, "Poslední akce", 9, True, fg=T["sub"]).pack(side="left")
        self.last_lbl = self.label(fi, "zmáčkni boční tlačítko nebo nakloň kolečko na myši", 9, fg=T["sub"])
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
        self.label(side, "APLIKACE", 8, True, fg=T["sub"]).pack(anchor="w", padx=px(20), pady=(px(18), px(8)))
        self.button(side, "+  Přidat aplikaci", self.add_app_dialog).pack(side="bottom", fill="x", padx=px(16), pady=px(16))
        self.app_scroll = ScrollList(side, T["panel"], px(20))
        self.app_scroll.cv.pack(fill="both", expand=True)

        right = tk.Frame(body, bg=T["panel"], width=px(330))
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        tk.Frame(body, bg=T["border"], width=1).pack(side="right", fill="y")
        rt = tk.Frame(right, bg=T["panel"])
        rt.pack(fill="x", padx=px(22), pady=(px(18), px(6)))
        self.label(rt, "AKCE PRO", 8, True, fg=T["sub"]).pack(anchor="w")
        self.ctl_title = self.label(rt, "", 13, True)
        self.ctl_title.pack(anchor="w")
        sbox = tk.Frame(rt, bg=T["panel2"], highlightthickness=1, highlightbackground=T["border"],
                        highlightcolor=T["accent"])
        sbox.pack(fill="x", pady=(px(12), px(2)))
        self.label(sbox, "⌕", 13, fg=T["sub"], bg=T["panel2"]).pack(side="left", padx=(px(10), 0))
        self.search_var = tk.StringVar(value="Hledat akci…")
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
        self.remove_btn = self.button(trow, "Odebrat profil", self.remove_app, kind="ghost")
        self.sub_lbl = self.label(top, "", 9, fg=T["sub"])
        self.sub_lbl.pack(anchor="w")
        chips = tk.Frame(top, bg=T["bg"])
        chips.pack(anchor="w", pady=(px(12), 0))
        self.label(chips, "Šablony", 9, True, fg=T["sub"]).pack(side="left", padx=(0, px(10)))
        for name in G.TEMPLATES:
            self.button(chips, name, lambda n=name: self.apply_template(n)).pack(side="left", padx=(0, px(8)))
        self.cv = tk.Canvas(center, bg=T["bg"], highlightthickness=0)
        self.cv.pack(fill="both", expand=True, padx=px(8), pady=px(8))
        self.cv.bind("<Configure>", lambda e: self.draw())

        # ---- stránka Myš ve Windows
        self.page_win = tk.Frame(r, bg=T["bg"])
        self.win_scroll = ScrollList(self.page_win, T["bg"], px(24))
        self.win_scroll.cv.pack(fill="both", expand=True)
        self._paint_tabs()

    # ================================================================ záložky
    def _paint_tabs(self):
        for key, (lab, und) in self.tabs.items():
            on = key == self.page
            lab.configure(fg=self.T["tab_on"] if on else self.T["sub"])
            und.configure(bg=self.T["accent"] if on else self.T["panel"])

    def set_page(self, page):
        if page == self.page:
            return
        self.page = page
        if page == "win":
            self.page_buttons.pack_forget()
            self.page_win.pack(fill="both", expand=True)
            self.build_win_page()
        else:
            self.page_win.pack_forget()
            self.page_buttons.pack(fill="both", expand=True)
            self.draw()
        self._paint_tabs()

    # ================================================================ hledání akcí
    def _search_focus(self, _):
        if self._search_placeholder:
            self._search_placeholder = True
            self.search_var.set("")
            self._search_placeholder = False
            self.search.configure(fg=self.T["text"])

    def _search_blur(self, _):
        if not self.search_var.get():
            self._search_placeholder = True
            self.search_var.set("Hledat akci…")
            self.search.configure(fg=self.T["sub"])

    def search_text(self):
        return "" if self._search_placeholder else self.search_var.get().strip()

    def build_actions(self):
        T, px = self.T, self.px
        sl = self.act_scroll
        sl.clear()
        cur = self.raw_action(self.control)
        q = self.search_text().lower()

        sections = []
        if self.current != C.GLOBAL:
            sections.append(("Profil", [("inherit", "Jako ve Všech aplikacích",
                                         short_label(self.raw_action(self.control, C.GLOBAL)))]))
        for cat, acts in G.CATEGORIES:
            sections.append((cat, [(a, *split_label(C.PRESET_LABEL[a])) for a in acts]))
        is_keys = cur.startswith("keys:") and cur not in C.PRESET_LABEL
        is_run = cur.startswith("run:")
        sections.append(("Vlastní", [
            ("custom_keys", "Vlastní klávesová zkratka…", cur[5:] if is_keys else ""),
            ("custom_run", "Spustit program nebo soubor…", os.path.basename(cur[4:]) if is_run else "")]))

        def selected(a):
            return a == cur or (a == "custom_keys" and is_keys) or (a == "custom_run" and is_run)

        shown = 0
        for title, items in sections:
            items = [i for i in items if not q or any(q in t.lower() for t in (i[1], i[2], title))]
            if not items:
                continue
            self.label(sl.frame, title.upper(), 8, True, fg=T["sub"]).pack(anchor="w", padx=px(22), pady=(px(14), px(4)))
            for action, text, sub in items:
                self._action_row(sl.frame, action, text, sub, selected(action))
                shown += 1
        if not shown:
            self.label(sl.frame, "Nic nenalezeno.", 9, fg=T["sub"]).pack(anchor="w", padx=px(22), pady=px(16))
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
        if sel:
            rc.create_oval(1, 1, d - 1, d - 1, outline=T["accent"], width=max(2, px(2)))
            rc.create_oval(d * 0.3, d * 0.3, d * 0.7, d * 0.7, fill=T["accent"], outline="")
        else:
            rc.create_oval(1, 1, d - 1, d - 1, outline=T["line"], width=max(1, px(1.5)))
        self.label(f, text, 10, sel, fg=T["accent"] if sel else T["text"], anchor="w").pack(side="left")
        if sub:
            self.label(f, sub, 8, fg=T["sub"]).pack(side="right", padx=px(12))
        bind_tree(f, "<Button-1>", lambda e, a=action: self.choose(a))
        if not sel:
            bind_tree(f, "<Enter>", lambda e, w=f: set_bg_tree(w, T["hover"]))
            bind_tree(f, "<Leave>", lambda e, w=f: set_bg_tree(w, T["panel"]))

    # ================================================================ fotka myši se štítky
    def _load_mouse(self):
        if Image is None:
            return
        try:
            with open(os.path.join(ASSETS, "mouse.json"), encoding="utf-8") as f:
                meta = json.load(f)
            name = "mouse_dark.png" if self.dark else "mouse.png"
            self.mouse_src = Image.open(os.path.join(ASSETS, name)).convert("RGBA")
            self.mouse_hs = meta["hotspots"]
        except (OSError, ValueError, KeyError):
            self.mouse_src = None

    def _mouse_image(self, w, h):
        key = (w, h)
        if self._mouse_key != key:
            self._mouse_tk = ImageTk.PhotoImage(self.mouse_src.resize(key, Image.LANCZOS), master=self.root)
            self._mouse_key = key
        return self._mouse_tk

    def draw(self):
        if self.page != "buttons":
            return
        if self.mouse_src is None:
            return G.App.draw(self)
        cv, T, px = self.cv, self.T, self.px
        cv.delete("all")
        Wd, Hd = cv.winfo_width(), cv.winfo_height()
        if Wd < 200 or Hd < 150:
            return
        sw, sh = self.mouse_src.size
        cw = px(214)
        # vpravo od ovladačů (≈ 66 % šířky fotky) musí zbýt místo na karty
        iw = min((Wd - px(24) - cw - px(70)) / 0.67, Hd * 0.9 * sw / sh, Wd * 0.95)
        k = iw / sw
        ih = sh * k
        free = Wd - (iw * 0.67 + px(70) + cw)
        ox, oy = max(px(8), free / 2), (Hd - ih) / 2 + px(20)
        cv.create_image(ox, oy, image=self._mouse_image(int(iw), int(ih)), anchor="nw")
        hs = {n: (ox + x * k, oy + y * k) for n, (x, y) in self.mouse_hs.items()}

        ctl = self.control
        flash = self.flash

        def clamp_box(x, y, w, h):
            return max(px(6), min(x, Wd - w - px(6))), max(px(6), min(y, Hd - h - px(6)))

        def leader(p, box, col, sel):
            x1, y1, x2, y2 = box
            qx, qy = min(max(p[0], x1), x2), min(max(p[1], y1), y2)
            cv.create_line(p[0], p[1], qx, qy, fill=col, width=px(2) if sel else max(1, px(1.2)))

        def fit(text, font, maxw):
            while font.measure(text) > maxw and len(text) > 3:
                text = text[:-2] + "…"
            return text

        def effective(c):
            raw = self.raw_action(c)
            return (self.raw_action(c, C.GLOBAL), True) if raw == "inherit" else (raw, False)

        # ---- kolečko: jedna karta se dvěma řádky (doleva / doprava)
        wx, wy = hs["h"]
        wsel = ctl in ("hleft", "hright")
        wfl = flash in ("hleft", "hright")
        row_h, head_h = px(34), px(34)
        chh = head_h + 2 * row_h + px(10)
        bx, by = clamp_box(hs["x1"][0] + px(64), wy - chh - px(14), cw, chh)
        box = (bx, by, bx + cw, by + chh)
        col = T["ok"] if wfl else T["accent"] if wsel else T["line"]
        leader((wx, wy), box, col, wsel or wfl)
        rrect(cv, *box, px(10), fill=T["card"], outline=col if (wsel or wfl) else T["border"],
              width=px(2) if (wsel or wfl) else 1, tags=("card_h",))
        cv.create_text(bx + px(14), by + head_h / 2 + px(3), text="Palcové kolečko", anchor="w",
                       font=self.f_cardsub, fill=T["sub"], tags=("card_h",))
        for i, (c, arrow) in enumerate((("hleft", "◀"), ("hright", "▶"))):
            ry = by + head_h + i * row_h
            on = ctl == c
            tag = "card_" + c
            if on or flash == c:
                rrect(cv, bx + px(6), ry + px(2), bx + cw - px(6), ry + row_h - px(2), px(7),
                      fill=T["ok"] if flash == c else T["accent"], outline="", tags=(tag,))
            fg = "#FFFFFF" if (on or flash == c) else T["text"]
            eff, inh = effective(c)
            cv.create_text(bx + px(18), ry + row_h / 2, text=arrow, anchor="w", font=self.f_cardsub,
                           fill=fg, tags=(tag,))
            cv.create_text(bx + px(40), ry + row_h / 2, anchor="w", font=self.f_card, fill=fg, tags=(tag,),
                           text=fit(short_label(eff) + ("  ·  výchozí" if inh else ""), self.f_card, cw - px(54)))
            cv.tag_bind(tag, "<Button-1>", lambda e, c=c: self.select_control(c))
        cv.tag_bind("card_h", "<Button-1>", lambda e: self.select_control("hleft" if ctl not in ("hleft", "hright") else ctl))

        # ---- boční tlačítka
        cards = {"x1": (hs["x1"][0] + px(64), max(hs["x1"][1] + px(4), by + chh + px(12)), "nw"),
                 "x2": (hs["x2"][0] - px(64), hs["x2"][1] + px(22), "ne")}
        for c, (ax, ay, anchor) in cards.items():
            sel, fl = ctl == c, flash == c
            eff, inh = effective(c)
            chh = px(64)
            x = ax - cw if anchor == "ne" else ax
            x, y = clamp_box(x, ay, cw, chh)
            box = (x, y, x + cw, y + chh)
            col = T["ok"] if fl else T["accent"] if sel else T["line"]
            leader(hs[c], box, col, sel or fl)
            fill = T["ok"] if fl else T["accent"] if sel else T["card"]
            tag = "card_" + c
            rrect(cv, *box, px(10), fill=fill, outline=fill if (sel or fl) else T["border"], tags=(tag,))
            fg = "#FFFFFF" if (sel or fl) else T["text"]
            sub_fg = "#E6EEFB" if (sel or fl) else T["sub"]
            cv.create_text(x + px(14), y + px(23), anchor="w", font=self.f_card, fill=fg, tags=(tag,),
                           text=fit(short_label(eff), self.f_card, cw - px(28)))
            cv.create_text(x + px(14), y + px(45), anchor="w", font=self.f_cardsub, fill=sub_fg, tags=(tag,),
                           text=CONTROL_LABEL[c] + ("  ·  výchozí" if inh else ""))
            cv.tag_bind(tag, "<Button-1>", lambda e, c=c: self.select_control(c))

        # ---- kroužky na ovladačích
        r = px(9)
        for name, (x, y) in hs.items():
            cs = ("hleft", "hright") if name == "h" else (name,)
            sel = ctl in cs
            fl = flash in cs
            tag = "mark_" + name
            cv.create_oval(x - r - px(3), y - r - px(3), x + r + px(3), y + r + px(3), fill="", outline="",
                           tags=(tag,))
            cv.create_oval(x - r, y - r, x + r, y + r, outline=T["ok"] if fl else T["accent"] if sel else T["marker"],
                           width=max(2, px(2)), fill=T["ok"] if fl else T["accent"] if sel else "", tags=(tag,))
            if sel or fl:
                cv.create_oval(x - r * 0.4, y - r * 0.4, x + r * 0.4, y + r * 0.4, fill="#FFFFFF", outline="", tags=(tag,))
            target = ("hleft" if ctl not in cs else ctl) if name == "h" else name
            cv.tag_bind(tag, "<Button-1>", lambda e, c=target: self.select_control(c))
        for tag in ("card_h", "card_hleft", "card_hright", "card_x1", "card_x2", "mark_h", "mark_x1", "mark_x2"):
            cv.tag_bind(tag, "<Enter>", lambda e: cv.configure(cursor="hand2"))
            cv.tag_bind(tag, "<Leave>", lambda e: cv.configure(cursor=""))

    def select_control(self, control):
        super().select_control(control)
        names = {"hleft": "Palcové kolečko – doleva", "hright": "Palcové kolečko – doprava"}
        self.ctl_title.configure(text=names.get(control, CONTROL_LABEL[control]))

    # ================================================================ stránka Myš ve Windows
    def _apply(self, fn, *args, msg="Uloženo do Windows"):
        try:
            fn(*args)
            self.status(msg)
            return True
        except OSError as e:
            self.status(f"Nepodařilo se: {e}", error=True)
            return False

    def _section(self, parent, title, sub=None):
        T, px = self.T, self.px
        self.label(parent, title, 13, True, bg=T["bg"]).pack(anchor="w", pady=(px(26), px(2)))
        if sub:
            self.label(parent, sub, 9, fg=T["sub"], bg=T["bg"]).pack(anchor="w")
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
        if also_right:  # po prohození tlačítek reaguje i na „druhé“ tlačítko
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
        self.label(intro, "Myš ve Windows", 17, True, bg=T["bg"]).pack(anchor="w")
        self.label(intro, "Systémové nastavení – platí pro všechny myši i touchpad a změna se projeví hned. "
                          "Citlivost (DPI) Tecknetu se přepíná tlačítkem pod kolečkem na myši.",
                   9, fg=T["sub"], bg=T["bg"], wraplength=px(760), justify="left").pack(anchor="w")

        # ---- ukazatel
        c = self._section(outer, "Ukazatel")
        self._row(c, "Rychlost ukazatele", "Výchozí je 10.",
                  lambda p: Slider(p, self, 1, 20, v["speed"], lambda x: self._apply(WS.set_speed, x)).pack_with_value())
        self._row(c, "Zvýšit přesnost ukazatele",
                  "Akcelerace – při rychlém pohybu ujede kurzor dál. Pro hry a grafiku se často vypíná.",
                  lambda p: self._switch(p, v["accel"], lambda on: self._apply(WS.set_accel, on)))

        # ---- kolečko
        c = self._section(outer, "Posouvání kolečkem")
        lines = {"v": v["lines"] if v["lines"] > 0 else 3}

        def set_lines(x):
            lines["v"] = x
            if not page_sw.value:
                self._apply(WS.set_lines, x)

        self._row(c, "Počet řádků na jedno cvaknutí", "Výchozí jsou 3 řádky.",
                  lambda p: Slider(p, self, 1, 20, lines["v"], set_lines).pack_with_value())
        holder = {}
        self._row(c, "Posouvat po celých stránkách", "Jedno cvaknutí posune o celou obrazovku.",
                  lambda p: holder.setdefault("sw", self._switch(
                      p, v["lines"] < 0, lambda on: self._apply(WS.set_lines, -1 if on else lines["v"]))))
        page_sw = holder["sw"]
        self._row(c, "Posouvat neaktivní okna pod kurzorem",
                  "Kolečko posouvá okno, nad kterým je myš, i když není aktivní.",
                  lambda p: self._switch(p, v["hover_scroll"], lambda on: self._apply(WS.set_hover_scroll, on)))
        self._row(c, "Znaků při vodorovném posunu",
                  "Uplatní se jen tam, kde má palcové kolečko výchozí funkci (např. Excel).",
                  lambda p: Slider(p, self, 1, 20, v["chars"], lambda x: self._apply(WS.set_chars, x)).pack_with_value())

        # ---- tlačítka
        c = self._section(outer, "Tlačítka")
        self._row(c, "Prohodit levé a pravé tlačítko", "Pro leváky. Přepínač jde vrátit kterýmkoli tlačítkem.",
                  lambda p: self._switch(p, v["swap"], lambda on: self._apply(WS.set_swap, on), also_right=True))

        def dbl(p):
            test = tk.Canvas(p, width=px(110), height=px(40), bg=T["panel"], highlightthickness=0, cursor="hand2")
            state = {"on": False}

            def paint():
                test.delete("all")
                fill = T["ok"] if state["on"] else T["panel2"]
                rrect(test, 2, 2, px(110) - 2, px(40) - 2, px(10), fill=fill, outline=T["border"])
                test.create_text(px(55), px(20), text="Funguje!" if state["on"] else "Dvojklik sem",
                                 fill="#FFFFFF" if state["on"] else T["sub"], font=("Segoe UI", 9))

            def flip(_):
                state["on"] = not state["on"]
                paint()

            test.bind("<Double-Button-1>", flip)
            paint()
            test.pack(side="right", padx=(px(16), 0))
            Slider(p, self, 200, 900, v["dblclick"], lambda x: self._apply(WS.set_dblclick, x),
                   fmt=lambda x: f"{x} ms", step=10, width=200).pack_with_value()

        self._row(c, "Rychlost dvojkliku", "Kratší čas = rychlejší dvojklik. Výchozí je 500 ms.", dbl)

        # ---- kurzor
        c = self._section(outer, "Kurzor")
        self._row(c, "Velikost kurzoru", "1 = výchozí velikost (jako v Nastavení › Usnadnění › Ukazatel myši).",
                  lambda p: Slider(p, self, 1, 15, v["cursor_size"],
                                   lambda x: self._apply(WS.set_cursor_size, x)).pack_with_value())
        self._row(c, "Schéma kurzorů", "Vzhled všech kurzorů najednou. Klikni na schéma.", lambda p: None)
        grid = tk.Frame(c, bg=T["panel"])
        grid.pack(fill="x", padx=px(14), pady=(0, px(16)))
        self._scheme_tiles(grid, v["scheme"])

        # ---- další
        c = self._section(outer, "Další")
        self._row(c, "Ukázat polohu kurzoru klávesou Ctrl", "Po stisku Ctrl se kolem kurzoru zobrazí kruh.",
                  lambda p: self._switch(p, v["sonar"], lambda on: self._apply(WS.set_bool, "sonar", on)))
        self._row(c, "Skrýt kurzor při psaní", None,
                  lambda p: self._switch(p, v["vanish"], lambda on: self._apply(WS.set_bool, "vanish", on)))
        self._row(c, "Skočit kurzorem na výchozí tlačítko", "V nových dialozích se kurzor přesune na OK / Ano.",
                  lambda p: self._switch(p, v["snap"], lambda on: self._apply(WS.set_bool, "snap", on)))
        self._row(c, "Stopa kurzoru", "Za kurzorem zůstává krátká stopa – lépe ho uvidíš.",
                  lambda p: self._switch(p, v["trails"] > 0, lambda on: self._apply(WS.set_trails, 7 if on else 0)))

        bar = tk.Frame(outer, bg=T["bg"])
        bar.pack(fill="x", pady=(px(26), 0))
        self.button(bar, "Nastavení myši ve Windows", WS.open_windows_settings).pack(side="left")
        self.button(bar, "Klasické vlastnosti myši", WS.open_classic_panel).pack(side="left", padx=px(8))
        self.button(bar, "Obnovit výchozí hodnoty", self.reset_windows, kind="ghost").pack(side="right")

    def _scheme_tiles(self, grid, current):
        T, px = self.T, self.px
        schemes = WS.list_schemes()
        names = {s["name"] for s in schemes}
        tiles = [None] + schemes
        cols = 3
        for i in range(cols):
            grid.columnconfigure(i, weight=1, uniform="s")
        isz = px(32)
        for i, sch in enumerate(tiles):
            name = "Výchozí Windows" if sch is None else sch["name"]
            sel = (sch is None and current not in names) or (sch is not None and sch["name"] == current)
            bg = T["accent_soft"] if sel else T["panel2"]
            t = tk.Frame(grid, bg=bg, cursor="hand2", highlightthickness=2 if sel else 1,
                         highlightbackground=T["accent"] if sel else T["border"])
            t.grid(row=i // cols, column=i % cols, sticky="nsew", padx=px(5), pady=px(5))
            icons = tk.Frame(t, bg="#F3F4F7")
            icons.pack(fill="x", padx=px(10), pady=(px(10), px(6)), ipadx=px(4), ipady=px(4))
            files = WS.DEFAULT_FILES if sch is None else sch["files"]
            for cur in WS.PREVIEW:
                key = ("cur", name, cur, isz)
                if key not in self.images:
                    h = WS.load_cursor(files.get(cur) or WS.DEFAULT_FILES.get(cur), isz)
                    img = None
                    if h:
                        try:
                            import base64
                            img = tk.PhotoImage(data=base64.b64encode(hicon_png(h, isz)).decode())
                        except Exception:
                            img = None
                    self.images[key] = img
                if self.images[key]:
                    tk.Label(icons, image=self.images[key], bg="#F3F4F7").pack(side="left", padx=(px(6), 0))
            self.label(t, name, 9, sel, fg=T["accent"] if sel else T["text"], bg=bg, anchor="w").pack(
                anchor="w", padx=px(12), pady=(0, px(10)))
            bind_tree(t, "<Button-1>", lambda e, s=sch: self._pick_scheme(s))

    def _pick_scheme(self, sch):
        if self._apply(WS.apply_scheme, sch, msg="Schéma kurzorů použito"):
            y = self.win_scroll.cv.yview()[0]
            self.build_win_page()
            self.root.after(30, lambda: self.win_scroll.cv.yview_moveto(y))

    def reset_windows(self):
        if not messagebox.askyesno("Obnovit výchozí", "Vrátit všechna nastavení myši ve Windows na výchozí hodnoty?",
                                   parent=self.root):
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
        self.status("Výchozí hodnoty obnoveny" if not errors else f"Obnoveno, {errors} položek se nepodařilo",
                    error=bool(errors))

    def show(self):
        super().show()
        if self.page == "win":
            self.build_win_page()

    def run(self, show=False):
        import sys
        if "--page-win" in sys.argv:
            self.root.after(300, lambda: self.set_page("win"))
        super().run(show)
