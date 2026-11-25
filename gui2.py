"""Okno nastavení v2 – vlastní vzhled ve stylu Logi Options+ (obrázek myši, karty, kategorie akcí)."""
import base64
import copy
import ctypes
import os
import queue
import re
import struct
import tkinter as tk
import tkinter.font as tkfont
import winreg
import zlib
from ctypes import wintypes as W
from tkinter import filedialog

import config as C
import engine as E
from gui import autostart_get, autostart_set

# ---------------------------------------------------------------- vzhled

LIGHT = dict(bg="#F3F4F7", panel="#FFFFFF", panel2="#F7F8FA", border="#E2E5EB", text="#1B1F27",
             sub="#6B7280", accent="#2F7DE2", accent_soft="#E7F0FC", hover="#F1F3F7",
             body="#3A3F48", body_hi="#474D57", part="#626A77", part_line="#262A31", wheel="#22262C",
             shadow="#E1E4EA", line="#C5CAD3", ok="#2E9E5B", warn="#C0392B", switch_off="#C9CED6",
             on_accent="#FFFFFF")
DARK = dict(bg="#15171C", panel="#1E2127", panel2="#23262D", border="#2D313A", text="#E8EAEE",
            sub="#959CA8", accent="#4C93F0", accent_soft="#1F3250", hover="#272B33",
            body="#4B515C", body_hi="#58606C", part="#7A8290", part_line="#2A2E35", wheel="#2B2F36",
            shadow="#101216", line="#3A3F49", ok="#3DBE72", warn="#E5675A", switch_off="#454B55",
            on_accent="#FFFFFF")

CATEGORIES = [
    ("Základní", ["default", "none"]),
    ("Prohlížeč a taby", ["keys:ctrl+tab", "keys:ctrl+shift+tab", "keys:ctrl+w", "keys:ctrl+shift+t",
                          "keys:alt+left", "keys:alt+right"]),
    ("Hlasitost a média", ["keys:volume_up", "keys:volume_down", "keys:volume_mute",
                           "keys:media_play_pause", "keys:media_next", "keys:media_prev"]),
    ("Úpravy", ["keys:ctrl+c", "keys:ctrl+x", "keys:ctrl+v", "keys:ctrl+z", "keys:ctrl+y"]),
    ("Zobrazení", ["keys:ctrl+num_plus", "keys:ctrl+num_minus"]),
    ("Okna a plochy", ["keys:ctrl+win+right", "keys:ctrl+win+left", "keys:win+tab", "keys:win+d"]),
    ("Tlačítka myši", ["mouse:x1", "mouse:x2", "mouse:middle", "mouse:hleft", "mouse:hright"]),
]

TEMPLATES = {
    "Prohlížeč": {"x1": "keys:ctrl+shift+tab", "x2": "keys:ctrl+tab",
                  "hleft": "keys:volume_down", "hright": "keys:volume_up"},
    "Přehrávač": {"x1": "keys:media_prev", "x2": "keys:media_next",
                  "hleft": "keys:volume_down", "hright": "keys:volume_up"},
    "Původní funkce": {"x1": "default", "x2": "default", "hleft": "default", "hright": "default"},
}
PLAYERS = {"vlc.exe", "kodi.exe", "mpc-hc.exe", "mpc-hc64.exe", "mpc-be.exe", "mpc-be64.exe", "mpv.exe",
           "potplayer.exe", "potplayer64.exe", "potplayermini.exe", "potplayermini64.exe", "spotify.exe",
           "foobar2000.exe", "aimp.exe", "musicbee.exe", "wmplayer.exe", "stremio.exe", "plex.exe",
           "music.ui.exe", "tidal.exe", "deezer.exe"}

CONTROL_LABEL = dict(C.CONTROLS)
CARD_ORDER = ["hleft", "hright", "x2", "x1"]
PART_OF = {"hleft": "h", "hright": "h", "x1": "x1", "x2": "x2"}

# tvar myši v normalizovaných souřadnicích (0..1), přední část nahoře, palcová strana vlevo
BODY = [(0.50, 0.00), (0.72, 0.02), (0.86, 0.10), (0.93, 0.25), (0.95, 0.45), (0.94, 0.65), (0.90, 0.82),
        (0.80, 0.95), (0.62, 1.00), (0.40, 0.99), (0.20, 0.95), (0.04, 0.88), (-0.06, 0.79), (-0.05, 0.70),
        (0.03, 0.60), (0.10, 0.51), (0.12, 0.38), (0.16, 0.20), (0.28, 0.06)]
BUTTONS = [(0.50, 0.012), (0.71, 0.03), (0.845, 0.105), (0.915, 0.25), (0.925, 0.37), (0.72, 0.405),
           (0.52, 0.415), (0.32, 0.405), (0.15, 0.375), (0.165, 0.21), (0.285, 0.07)]
# palcová opěrka (světlejší plocha pod bočními tlačítky)
THUMB = [(0.02, 0.765), (0.10, 0.75), (0.20, 0.79), (0.22, 0.88), (0.10, 0.90), (-0.02, 0.82)]
PARTS = {"h": (0.04, 0.505, 0.27, 0.575), "x2": (-0.015, 0.598, 0.22, 0.655), "x1": (-0.04, 0.668, 0.20, 0.728)}
TARGETS = {"hleft": (0.07, 0.54), "hright": (0.24, 0.54), "x2": (0.01, 0.6265), "x1": (-0.015, 0.698)}

# ---------------------------------------------------------------- Win32 pomocníci (ikony, názvy, procesy)

gdi = ctypes.WinDLL("gdi32")
ver = ctypes.WinDLL("version")
shell = ctypes.WinDLL("shell32")


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG), ("biPlanes", W.WORD),
                ("biBitCount", W.WORD), ("biCompression", W.DWORD), ("biSizeImage", W.DWORD),
                ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG), ("biClrUsed", W.DWORD),
                ("biClrImportant", W.DWORD)]


def _sig(fn, res, *args):
    fn.restype, fn.argtypes = res, list(args)


_sig(gdi.CreateCompatibleDC, W.HDC, W.HDC)
_sig(gdi.CreateDIBSection, W.HBITMAP, W.HDC, ctypes.c_void_p, W.UINT, ctypes.POINTER(ctypes.c_void_p), W.HANDLE, W.DWORD)
_sig(gdi.SelectObject, W.HGDIOBJ, W.HDC, W.HGDIOBJ)
_sig(gdi.DeleteObject, W.BOOL, W.HGDIOBJ)
_sig(gdi.DeleteDC, W.BOOL, W.HDC)
_sig(E.u32.DrawIconEx, W.BOOL, W.HDC, ctypes.c_int, ctypes.c_int, W.HICON, ctypes.c_int, ctypes.c_int, W.UINT, W.HBRUSH, W.UINT)
_sig(E.u32.DestroyIcon, W.BOOL, W.HICON)
_sig(E.u32.GetParent, W.HWND, W.HWND)
_sig(shell.SHDefExtractIconW, ctypes.c_long, W.LPCWSTR, ctypes.c_int, W.UINT, ctypes.POINTER(W.HICON),
     ctypes.POINTER(W.HICON), W.UINT)
_sig(ver.GetFileVersionInfoSizeW, W.DWORD, W.LPCWSTR, ctypes.POINTER(W.DWORD))
_sig(ver.GetFileVersionInfoW, W.BOOL, W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p)
_sig(ver.VerQueryValueW, W.BOOL, ctypes.c_void_p, W.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(W.UINT))
_sig(E.k32.K32EnumProcesses, W.BOOL, ctypes.POINTER(W.DWORD), W.DWORD, ctypes.POINTER(W.DWORD))


def png_bytes(w, h, rgba):
    raw = b"".join(b"\x00" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def exe_icon_png(path, size):
    hicon = W.HICON()
    if shell.SHDefExtractIconW(path, 0, 0, ctypes.byref(hicon), None, size | (16 << 16)) != 0 or not hicon:
        return None
    hdc = gdi.CreateCompatibleDC(None)
    bmi = BITMAPINFOHEADER(40, size, -size, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    hbm = gdi.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    old = gdi.SelectObject(hdc, hbm)
    try:
        E.u32.DrawIconEx(hdc, 0, 0, hicon, size, size, 0, None, 3)
        px = bytearray(ctypes.string_at(bits, size * size * 4))
    finally:
        gdi.SelectObject(hdc, old)
        gdi.DeleteObject(hbm)
        gdi.DeleteDC(hdc)
        E.u32.DestroyIcon(hicon)
    px[0::4], px[2::4] = px[2::4], px[0::4]  # BGRA -> RGBA
    if not any(px[3::4]):
        px[3::4] = b"\xff" * (size * size)
    return png_bytes(size, size, bytes(px))


def file_description(path):
    n = ver.GetFileVersionInfoSizeW(path, None)
    if not n:
        return None
    buf = ctypes.create_string_buffer(n)
    if not ver.GetFileVersionInfoW(path, 0, n, buf):
        return None
    p, ln = ctypes.c_void_p(), W.UINT()
    langs = []
    if ver.VerQueryValueW(buf, r"\VarFileInfo\Translation", ctypes.byref(p), ctypes.byref(ln)) and ln.value >= 4:
        langs.append("%04x%04x" % struct.unpack("<HH", ctypes.string_at(p, 4)))
    langs += ["040904b0", "040904e4"]
    for lang in langs:
        for field in ("FileDescription", "ProductName"):
            if ver.VerQueryValueW(buf, f"\\StringFileInfo\\{lang}\\{field}", ctypes.byref(p), ctypes.byref(ln)) \
                    and ln.value > 1:
                # do první nuly – některé programy (Spotify) mají v délce i data za koncem řetězce
                s = ctypes.wstring_at(p, ln.value).split("\x00", 1)[0].strip()
                if s:
                    return s
    return None


def proc_path(pid):
    h = E.k32.OpenProcess(0x1000, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = W.DWORD(1024)
        if E.k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return buf.value
    finally:
        E.k32.CloseHandle(h)
    return None


def running_paths():
    arr = (W.DWORD * 4096)()
    needed = W.DWORD()
    E.k32.K32EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed))
    out = {}
    for pid in arr[:needed.value // 4]:
        p = proc_path(pid) if pid else None
        if p:
            out.setdefault(os.path.basename(p).lower(), p)
    return out


def window_apps():
    """[(exe, titulek, cesta)] aplikací s viditelným oknem."""
    found = {}
    EnumProc = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    def cb(hwnd, _):
        u = E.u32
        if not u.IsWindowVisible(hwnd) or u.GetWindow(hwnd, 4) or u.GetWindowLongW(hwnd, -20) & 0x80:
            return True
        t = ctypes.create_unicode_buffer(256)
        if u.GetWindowTextW(hwnd, t, 256) <= 0:
            return True
        pid = W.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        p = proc_path(pid.value)
        if p:
            found.setdefault(os.path.basename(p).lower(), (t.value, p))
        return True

    E.u32.EnumWindows(EnumProc(cb), 0)
    return sorted((exe, t, p) for exe, (t, p) in found.items())


def system_dark():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def split_label(label):
    """'Další tab (Ctrl+Tab)' -> ('Další tab', 'Ctrl+Tab')"""
    m = re.match(r"^(.*?)\s*\((.*)\)$", label)
    return (m.group(1), m.group(2)) if m else (label, "")


def short_label(action):
    if action in C.PRESET_LABEL:
        return split_label(C.PRESET_LABEL[action])[0]
    return C.action_label(action)


# ---------------------------------------------------------------- widgety


class Switch(tk.Canvas):
    def __init__(self, parent, app, value, command):
        self.app = app
        S = app.S
        self.w, self.h = int(40 * S), int(22 * S)
        super().__init__(parent, width=self.w, height=self.h, bg=parent["bg"], highlightthickness=0, cursor="hand2")
        self.value, self.command = value, command
        self.bind("<Button-1>", self.toggle)
        self.draw()

    def draw(self):
        T, w, h = self.app.T, self.w, self.h
        self.delete("all")
        col = T["accent"] if self.value else T["switch_off"]
        self.create_oval(0, 0, h, h, fill=col, outline=col)
        self.create_oval(w - h, 0, w, h, fill=col, outline=col)
        self.create_rectangle(h / 2, 0, w - h / 2, h, fill=col, outline=col)
        pad = 3 * self.app.S
        kx = w - h + pad if self.value else pad
        self.create_oval(kx, pad, kx + h - 2 * pad, h - pad, fill="#FFFFFF", outline="")

    def set(self, v):
        self.value = bool(v)
        self.draw()

    def toggle(self, _=None):
        self.set(not self.value)
        self.command(self.value)


def rrect(cv, x1, y1, x2, y2, r, **kw):
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
           x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


def bind_tree(widget, seq, fn):
    widget.bind(seq, fn)
    for ch in widget.winfo_children():
        bind_tree(ch, seq, fn)


def set_bg_tree(widget, bg):
    try:
        widget.configure(bg=bg)
    except tk.TclError:
        pass
    for ch in widget.winfo_children():
        set_bg_tree(ch, bg)


class ScrollList:
    """Svisle rolovatelný rámeček (kolečkem myši)."""

    def __init__(self, parent, bg, step):
        self.cv = tk.Canvas(parent, bg=bg, highlightthickness=0, yscrollincrement=step)
        self.frame = tk.Frame(self.cv, bg=bg)
        self.win = self.cv.create_window(0, 0, window=self.frame, anchor="nw")
        self.frame.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfigure(self.win, width=e.width))
        self.cv.bind("<Enter>", lambda e: self.cv.bind_all("<MouseWheel>", self._wheel))
        self.cv.bind("<Leave>", lambda e: self.cv.unbind_all("<MouseWheel>"))

    def _wheel(self, e):
        if self.frame.winfo_height() > self.cv.winfo_height():
            self.cv.yview_scroll(int(-e.delta / 40), "units")

    def clear(self):
        for ch in self.frame.winfo_children():
            ch.destroy()
        self.cv.yview_moveto(0)


# ---------------------------------------------------------------- aplikace


class App:
    def __init__(self):
        self.cfg = C.load_config()
        self.cfg.setdefault("app_info", {})
        self.q = queue.Queue()
        self.engine = E.Engine(copy.deepcopy(self.cfg), lambda kind, *a: self.q.put((kind, a)))

        self.root = tk.Tk()
        self.root.withdraw()
        self.S = self.root.winfo_fpixels("1i") / 96.0
        self.dark = system_dark()
        self.T = DARK if self.dark else LIGHT
        self.root.title("Tecknet Remap")
        try:
            self.root.iconbitmap(default=C.ensure_icon())
        except tk.TclError:
            pass
        self.root.configure(bg=self.T["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.images = {}
        self.current = C.GLOBAL
        self.control = "x2"
        self.flash = None
        self.capturing = False
        self.f_card = tkfont.Font(family="Segoe UI Semibold", size=11)
        self.f_cardsub = tkfont.Font(family="Segoe UI", size=9)
        self._build()
        self.update_app_info()
        self.select_app(C.GLOBAL)
        self.root.after(100, self._poll)

    def px(self, n):
        return int(round(n * self.S))

    # ---------- engine -> GUI
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
                    self.last_lbl.configure(
                        text=f"{CONTROL_LABEL[control]}  ·  {self.app_name(exe) if exe else '?'}  →  {short_label(action)}")
                    self.flash = control
                    self.draw()
                    self.root.after(450, self._unflash, control)
                elif kind == "error":
                    self.status(args[0], error=True)
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _unflash(self, control):
        if self.flash == control:
            self.flash = None
            self.draw()

    def push_config(self):
        C.save_config(self.cfg)
        self.engine.set_config(copy.deepcopy(self.cfg))

    # ---------- data aplikací
    def update_app_info(self):
        missing = [e for e in self.cfg["profiles"] if e != C.GLOBAL and not self.cfg["app_info"].get(e)]
        if not missing:
            return
        paths = running_paths()
        changed = False
        for exe in missing:
            if exe in paths:
                self.cfg["app_info"][exe] = {"path": paths[exe], "name": file_description(paths[exe]) or ""}
                changed = True
        if changed:
            C.save_config(self.cfg)

    def app_name(self, exe):
        if exe == C.GLOBAL:
            return "Všechny aplikace"
        info = self.cfg["app_info"].get(exe) or {}
        return info.get("name") or os.path.splitext(exe)[0].capitalize()

    def app_image(self, exe, size, path=None):
        key = (exe, size)
        if key not in self.images:
            path = path or (self.cfg["app_info"].get(exe) or {}).get("path")
            img = None
            if path and os.path.exists(path):
                try:
                    data = exe_icon_png(path, size)
                    if data:
                        img = tk.PhotoImage(data=base64.b64encode(data).decode())
                except Exception:
                    img = None
            self.images[key] = img
        return self.images[key]

    def icon_widget(self, parent, exe, bg, size=28, path=None):
        s = self.px(size)
        cv = tk.Canvas(parent, width=s, height=s, bg=bg, highlightthickness=0)
        T = self.T
        if exe == C.GLOBAL:
            g, q = s * 0.1, s * 0.4
            for ix in (0, 1):
                for iy in (0, 1):
                    x, y = g + ix * (q + g * 0.8), g + iy * (q + g * 0.8)
                    rrect(cv, x, y, x + q, y + q, s * 0.08, fill=T["accent"], outline="")
            return cv
        img = self.app_image(exe, s, path)
        if img:
            cv.create_image(s / 2, s / 2, image=img)
        else:
            hue = ["#5B8DEF", "#E0795A", "#4FB286", "#A877E0", "#D9A441", "#E06A9A"][sum(map(ord, exe)) % 6]
            cv.create_oval(1, 1, s - 1, s - 1, fill=hue, outline="")
            cv.create_text(s / 2, s / 2, text=exe[:1].upper(), fill="#FFFFFF",
                           font=("Segoe UI Semibold", max(8, int(size * 0.38))))
        return cv

    # ---------- stavba UI
    def label(self, parent, text="", size=10, bold=False, fg=None, bg=None, **kw):
        return tk.Label(parent, text=text, font=("Segoe UI Semibold" if bold else "Segoe UI", size),
                        fg=fg or self.T["text"], bg=bg or parent["bg"], **kw)

    def button(self, parent, text, command, kind="soft"):
        T = self.T
        if kind == "primary":
            n_bg, n_fg, h_bg, h_fg = T["accent"], T["on_accent"], T["accent"], T["on_accent"]
        elif kind == "ghost":
            n_bg, n_fg, h_bg, h_fg = parent["bg"], T["sub"], T["hover"], T["text"]
        else:
            n_bg, n_fg, h_bg, h_fg = T["accent_soft"], T["accent"], T["accent"], T["on_accent"]
        b = tk.Label(parent, text=text, font=("Segoe UI Semibold", 10), bg=n_bg, fg=n_fg, cursor="hand2",
                     padx=self.px(14), pady=self.px(7))
        b.bind("<Enter>", lambda e: b.configure(bg=h_bg, fg=h_fg))
        b.bind("<Leave>", lambda e: b.configure(bg=n_bg, fg=n_fg))
        b.bind("<Button-1>", lambda e: command())
        return b

    def _build(self):
        T, px, r = self.T, self.px, self.root
        r.geometry(f"{px(1140)}x{px(700)}")
        r.minsize(px(1000), px(620))

        # hlavička
        hdr = tk.Frame(r, bg=T["panel"])
        hdr.pack(fill="x")
        inner = tk.Frame(hdr, bg=T["panel"])
        inner.pack(fill="x", padx=px(20), pady=px(12))
        s = px(34)
        raw = C._render(s)[40:40 + s * s * 4]
        rows = [raw[i * s * 4:(i + 1) * s * 4] for i in range(s)][::-1]
        lp = bytearray(b"".join(rows))
        lp[0::4], lp[2::4] = lp[2::4], lp[0::4]
        self.logo = tk.PhotoImage(data=base64.b64encode(png_bytes(s, s, bytes(lp))).decode())
        tk.Label(inner, image=self.logo, bg=T["panel"]).pack(side="left")
        tb = tk.Frame(inner, bg=T["panel"])
        tb.pack(side="left", padx=px(12))
        self.label(tb, "Tecknet TK-MS029", 15, True).pack(anchor="w")
        self.dev_lbl = self.label(tb, "", 9, fg=T["sub"])
        self.dev_lbl.pack(anchor="w")

        def switch(text, value, cmd):
            box = tk.Frame(inner, bg=T["panel"])
            box.pack(side="right", padx=(px(22), 0))
            sw = Switch(box, self, value, cmd)
            sw.pack(side="left")
            self.label(box, text, 10).pack(side="left", padx=(px(8), 0))
            return sw

        self.sw_auto = switch("Spustit po startu Windows", autostart_get(), self.on_autostart)
        self.sw_enabled = switch("Přemapování zapnuto", self.cfg.get("enabled", True), self.on_enabled)
        tk.Frame(r, bg=T["border"], height=1).pack(fill="x")

        # patička
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

        body = tk.Frame(r, bg=T["bg"])
        body.pack(fill="both", expand=True)

        # levý panel – aplikace
        side = tk.Frame(body, bg=T["panel"], width=px(236))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Frame(body, bg=T["border"], width=1).pack(side="left", fill="y")
        self.label(side, "APLIKACE", 8, True, fg=T["sub"]).pack(anchor="w", padx=px(20), pady=(px(18), px(8)))
        self.button(side, "+  Přidat aplikaci", self.add_app_dialog).pack(side="bottom", fill="x", padx=px(16), pady=px(16))
        self.app_scroll = ScrollList(side, T["panel"], px(20))
        self.app_scroll.cv.pack(fill="both", expand=True)

        # pravý panel – akce
        right = tk.Frame(body, bg=T["panel"], width=px(318))
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        tk.Frame(body, bg=T["border"], width=1).pack(side="right", fill="y")
        rt = tk.Frame(right, bg=T["panel"])
        rt.pack(fill="x", padx=px(22), pady=(px(18), px(6)))
        self.label(rt, "AKCE PRO", 8, True, fg=T["sub"]).pack(anchor="w")
        self.ctl_title = self.label(rt, "", 13, True)
        self.ctl_title.pack(anchor="w")
        self.editor = tk.Frame(right, bg=T["panel2"])
        self.act_scroll = ScrollList(right, T["panel"], px(20))
        self.act_scroll.cv.pack(fill="both", expand=True)

        # střed – profil a myš
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
        for name in TEMPLATES:
            self.button(chips, name, lambda n=name: self.apply_template(n)).pack(side="left", padx=(0, px(8)))
        self.cv = tk.Canvas(center, bg=T["bg"], highlightthickness=0)
        self.cv.pack(fill="both", expand=True, padx=px(8), pady=px(8))
        self.cv.bind("<Configure>", lambda e: self.draw())

    # ---------- levý panel
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
            self.label(tx, "výchozí profil" if exe == C.GLOBAL else exe, 8, fg=T["sub"], anchor="w").pack(anchor="w")
            bind_tree(row, "<Button-1>", lambda e, x=exe: self.select_app(x))
            if not sel:
                bind_tree(row, "<Enter>", lambda e, w=row: set_bg_tree(w, T["hover"]))
                bind_tree(row, "<Leave>", lambda e, w=row: set_bg_tree(w, T["panel"]))

    def select_app(self, exe):
        self.current = exe
        self.refresh_apps()
        if exe == C.GLOBAL:
            self.title_lbl.configure(text="Všechny aplikace")
            self.sub_lbl.configure(text="Výchozí nastavení – platí všude, kde aplikace nemá vlastní profil.")
            self.remove_btn.pack_forget()
        else:
            self.title_lbl.configure(text=self.app_name(exe))
            self.sub_lbl.configure(text=f"Platí, když je {exe} v popředí. Neupravené ovladače se řídí výchozím profilem.")
            self.remove_btn.pack(side="right")
        self.select_control(self.control)

    # ---------- akce pro ovladač
    def raw_action(self, control, exe=None):
        exe = exe or self.current
        prof = self.cfg["profiles"].get(exe, {})
        return prof.get(control, "default" if exe == C.GLOBAL else "inherit")

    def select_control(self, control):
        self.control = control
        self.ctl_title.configure(text=CONTROL_LABEL[control])
        self.build_actions()
        self.draw()

    def build_actions(self):
        T, px = self.T, self.px
        sl = self.act_scroll
        sl.clear()
        cur = self.raw_action(self.control)

        def header(text):
            self.label(sl.frame, text.upper(), 8, True, fg=T["sub"]).pack(anchor="w", padx=px(22), pady=(px(14), px(4)))

        def row(action, text, sub="", selected=False):
            bg = T["accent_soft"] if selected else T["panel"]
            f = tk.Frame(sl.frame, bg=bg, cursor="hand2")
            f.pack(fill="x", padx=px(12), pady=1)
            self.label(f, text, 10, selected, fg=T["accent"] if selected else T["text"], anchor="w").pack(
                side="left", padx=px(12), pady=px(7))
            if selected:
                self.label(f, "✓", 11, True, fg=T["accent"]).pack(side="right", padx=(0, px(12)))
            if sub:
                self.label(f, sub, 8, fg=T["sub"]).pack(side="right", padx=px(8))
            bind_tree(f, "<Button-1>", lambda e, a=action: self.choose(a))
            if not selected:
                bind_tree(f, "<Enter>", lambda e, w=f: set_bg_tree(w, T["hover"]))
                bind_tree(f, "<Leave>", lambda e, w=f: set_bg_tree(w, T["panel"]))

        if self.current != C.GLOBAL:
            header("Profil")
            g = self.raw_action(self.control, C.GLOBAL)
            row("inherit", "Jako ve Všech aplikacích", short_label(g), cur == "inherit")
        for cat, actions in CATEGORIES:
            header(cat)
            for a in actions:
                main, sub = split_label(C.PRESET_LABEL[a])
                row(a, main, sub, cur == a)
        header("Vlastní")
        is_keys = cur.startswith("keys:") and cur not in C.PRESET_LABEL
        is_run = cur.startswith("run:")
        row("custom_keys", "Vlastní klávesová zkratka…", cur[5:] if is_keys else "", is_keys)
        row("custom_run", "Spustit program nebo soubor…", os.path.basename(cur[4:]) if is_run else "", is_run)
        tk.Frame(sl.frame, bg=T["panel"], height=px(16)).pack()
        self.build_editor("keys" if is_keys else "run" if is_run else None, cur)

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
            self.label(box, "Klávesová zkratka", 9, True, fg=T["sub"]).pack(anchor="w")
            line = tk.Frame(box, bg=T["panel2"])
            line.pack(fill="x", pady=(px(6), px(4)))
            self.key_var = tk.StringVar(value=cur[5:] if cur.startswith("keys:") else "")
            ent = tk.Entry(line, textvariable=self.key_var, font=("Segoe UI", 11), bg=T["panel"], fg=T["text"],
                           insertbackground=T["text"], relief="flat", highlightthickness=1,
                           highlightbackground=T["border"], highlightcolor=T["accent"])
            ent.pack(side="left", fill="x", expand=True, ipady=px(5))
            ent.bind("<Return>", lambda e: self.save_custom_keys())
            self.key_entry = ent
            self.button(line, "Nahrát", self.capture).pack(side="left", padx=(px(8), 0))
            self.button(line, "Uložit", self.save_custom_keys, kind="primary").pack(side="left", padx=(px(6), 0))
            self.label(box, "Klikni na Nahrát a stiskni zkratku, nebo ji napiš: ctrl+shift+t, alt+f4, f5, win+e",
                       8, fg=T["sub"], wraplength=px(290), justify="left").pack(anchor="w")
        else:
            self.label(box, "Program nebo soubor", 9, True, fg=T["sub"]).pack(anchor="w")
            self.label(box, cur[4:], 9, wraplength=px(290), justify="left").pack(anchor="w", pady=px(4))
            self.button(box, "Změnit…", lambda: self.choose("custom_run")).pack(anchor="w")

    def choose(self, action):
        if action == "custom_keys":
            self.build_editor("keys", "keys:")
            self.capture()
            return
        if action == "custom_run":
            p = filedialog.askopenfilename(parent=self.root, title="Vyber program nebo soubor")
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
        self.draw()
        self.status("Uloženo")

    def save_custom_keys(self):
        text = self.key_var.get().strip().lower().replace(" ", "")
        try:
            E.parse_combo(text)
        except ValueError as e:
            self.status(f"Zkratku nelze použít: {e}", error=True)
            return
        self.set_action(self.control, "keys:" + text)

    def capture(self):
        self.capturing = True
        self.key_var.set("stiskni zkratku…")
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
            self.status("Tuhle klávesu neumím nahrát – napiš ji ručně.", error=True)
            return "break"
        mods = [m for m, bit in (("ctrl", 0x4), ("shift", 0x1), ("alt", 0x20000)) if ev.state & bit]
        self.key_var.set("+".join(mods + [name]))
        self.save_custom_keys()
        return "break"

    def apply_template(self, name):
        t = TEMPLATES[name]
        self.cfg["profiles"][self.current] = dict(t)
        self.push_config()
        self.build_actions()
        self.draw()
        self.status(f"Použita šablona {name}")

    # ---------- obrázek myši a karty
    def draw(self):
        cv, T, px = self.cv, self.T, self.px
        cv.delete("all")
        Wd, Hd = cv.winfo_width(), cv.winfo_height()
        if Wd < 100 or Hd < 100:
            return
        left = px(18 + 232 + 76)  # karty + vodicí čáry
        mh = min(Hd * 0.92, (Wd - left - px(24)) / 0.70)
        mw = mh * 0.66
        mx0 = left + max(0, (Wd - left - mw) / 2 - px(10))
        my0 = (Hd - mh) / 2

        def P(x, y):
            return mx0 + x * mw, my0 + y * mh

        def poly(pts, dx=0.0, dy=0.0, **kw):
            flat = [c for x, y in pts for c in P(x + dx, y + dy)]
            return cv.create_polygon(flat, smooth=True, **kw)

        def rect(a, b, c, d, r, **kw):
            x1, y1 = P(a, b)
            x2, y2 = P(c, d)
            return rrect(cv, x1, y1, x2, y2, r, **kw)

        poly(BODY, 0.03, 0.02, fill=T["shadow"], outline="")
        poly(BODY, fill=T["body"], outline=T["part_line"], width=max(1, px(1)))
        poly(BUTTONS, fill=T["body_hi"], outline=T["part_line"], width=max(1, px(1)))
        cv.create_line(*P(0.515, 0.015), *P(0.515, 0.41), fill=T["part_line"], width=px(2))
        rect(0.462, 0.10, 0.568, 0.26, px(8), fill=T["wheel"], outline=T["part_line"])
        for i in range(7):
            y = 0.115 + i * 0.021
            cv.create_line(*P(0.48, y), *P(0.55, y), fill=T["part"], width=1)
        cv.create_oval(*P(0.50, 0.30), *P(0.53, 0.318), fill=T["part"], outline="")

        sel_part = PART_OF[self.control]
        flash_part = PART_OF.get(self.flash) if self.flash else None
        for key, (a, b, c, d) in PARTS.items():
            fill = T["ok"] if key == flash_part else T["accent"] if key == sel_part else T["part"]
            rect(a, b, c, d, px(6), fill=fill, outline=T["part_line"], tags=("part_" + key,))
            if key == "h":
                for i in range(1, 9):
                    x = a + (c - a) * i / 9
                    cv.create_line(*P(x, b + 0.008), *P(x, d - 0.008), fill=T["part_line"], width=1,
                                   tags=("part_h",))
        for key in PARTS:
            ctl = {"h": "hright" if self.control == "hright" else "hleft", "x1": "x1", "x2": "x2"}[key]
            cv.tag_bind("part_" + key, "<Button-1>", lambda e, c=ctl: self.select_control(c))

        # karty
        cw = min(px(232), mx0 - px(76))
        ch, gap = px(66), px(14)
        ty = sum(P(*TARGETS[c])[1] for c in CARD_ORDER) / 4
        total = 4 * ch + 3 * gap
        y0 = max(px(8), min(ty - total / 2, Hd - total - px(8)))
        x0 = px(18)
        for i, ctl in enumerate(CARD_ORDER):
            cy = y0 + i * (ch + gap)
            sel = ctl == self.control
            fl = ctl == self.flash
            col = T["ok"] if fl else T["accent"] if sel else T["line"]
            tx, tyy = P(*TARGETS[ctl])
            ex = x0 + cw + px(16) + i * px(10)
            cv.create_line(x0 + cw, cy + ch / 2, ex, cy + ch / 2, tx, tyy, fill=col,
                           width=px(2) if sel or fl else 1, joinstyle="round")
            rad = px(4)
            cv.create_oval(tx - rad, tyy - rad, tx + rad, tyy + rad, fill=col, outline=T["bg"])
            tag = "card_" + ctl
            rrect(cv, x0, cy, x0 + cw, cy + ch, px(12), fill=T["panel"],
                  outline=col if (sel or fl) else T["border"], width=px(2) if (sel or fl) else 1, tags=(tag,))
            raw = self.raw_action(ctl)
            inherited = raw == "inherit"
            eff = self.raw_action(ctl, C.GLOBAL) if inherited else raw
            title = CONTROL_LABEL[ctl] + ("  ·  výchozí" if inherited else "")
            cv.create_text(x0 + px(16), cy + px(20), text=title, anchor="w", font=self.f_cardsub,
                           fill=T["sub"], tags=(tag,))
            text = short_label(eff)
            maxw = cw - px(32)
            while self.f_card.measure(text) > maxw and len(text) > 3:
                text = text[:-2] + "…"
            cv.create_text(x0 + px(16), cy + px(44), text=text, anchor="w", font=self.f_card,
                           fill=T["accent"] if sel else T["text"], tags=(tag,))
            cv.tag_bind(tag, "<Button-1>", lambda e, c=ctl: self.select_control(c))
            cv.tag_bind(tag, "<Enter>", lambda e: cv.configure(cursor="hand2"))
            cv.tag_bind(tag, "<Leave>", lambda e: cv.configure(cursor=""))

    # ---------- přidání / odebrání aplikace
    def add_app_dialog(self):
        T, px = self.T, self.px
        dlg = tk.Toplevel(self.root, bg=T["panel"])
        dlg.title("Přidat aplikaci")
        dlg.transient(self.root)
        dlg.geometry(f"{px(500)}x{px(560)}")
        dlg.after(10, lambda: self._titlebar(dlg))
        head = tk.Frame(dlg, bg=T["panel"])
        head.pack(fill="x", padx=px(22), pady=(px(18), px(6)))
        self.label(head, "Přidat aplikaci", 14, True).pack(anchor="w")
        self.label(head, "Vyber spuštěnou aplikaci, nebo najdi jiný program přes Procházet.", 9,
                   fg=T["sub"]).pack(anchor="w")
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
        apps = [a for a in window_apps() if a[0] not in self.cfg["profiles"]
                and a[0] not in ("pythonw.exe", "python.exe", "explorer.exe", "applicationframehost.exe",
                                 "textinputhost.exe", "shellexperiencehost.exe", "searchhost.exe",
                                 "startmenuexperiencehost.exe", "lockapp.exe")]
        for exe, _, path in apps:
            if exe not in self.cfg["app_info"]:
                self.cfg["app_info"][exe] = {"path": path, "name": file_description(path) or ""}

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
                if exe in PLAYERS:
                    self.label(f, "přehrávač", 8, fg=T["accent"]).pack(side="right", padx=px(12))
                bind_tree(f, "<Button-1>", lambda e, x=exe, p=path: (self.add_app(x, p), dlg.destroy()))
                bind_tree(f, "<Enter>", lambda e, w=f: set_bg_tree(w, T["hover"]))
                bind_tree(f, "<Leave>", lambda e, w=f: set_bg_tree(w, T["panel"]))
            if not sl.frame.winfo_children():
                self.label(sl.frame, "Nic nenalezeno.", 9, fg=T["sub"]).pack(pady=px(20))

        q.trace_add("write", fill)
        fill()

        def browse():
            p = filedialog.askopenfilename(parent=dlg, title="Vyber program", filetypes=[("Programy", "*.exe")])
            if p:
                self.add_app(os.path.basename(p).lower(), os.path.normpath(p))
                dlg.destroy()

        self.button(bar, "Procházet…", browse).pack(side="left")
        self.button(bar, "Zavřít", dlg.destroy, kind="ghost").pack(side="right")

    def add_app(self, exe, path=None):
        exe = exe.lower()
        if path:
            self.cfg["app_info"][exe] = {"path": path, "name": file_description(path) or ""}
        new = exe not in self.cfg["profiles"]
        self.cfg["profiles"].setdefault(exe, {})
        if new and exe in PLAYERS:
            self.cfg["profiles"][exe] = dict(TEMPLATES["Přehrávač"])
        self.push_config()
        self.select_app(exe)
        if new and exe in PLAYERS:
            self.status("Přehrávač: nastavena šablona Přehrávač (kolečko = hlasitost, tlačítka = skladby)")

    def remove_app(self):
        if self.current == C.GLOBAL:
            return
        exe = self.current
        self.cfg["profiles"].pop(exe, None)
        self.push_config()
        self.select_app(C.GLOBAL)
        self.status(f"Profil {exe} odebrán")

    # ---------- přepínače
    def on_enabled(self, value):
        self.cfg["enabled"] = bool(value)
        self.push_config()
        self.status("Přemapování zapnuto" if value else "Přemapování pozastaveno")

    def on_autostart(self, value):
        try:
            autostart_set(value)
            self.status("Spustí se po startu Windows" if value else "Autostart vypnut")
        except OSError as e:
            self.sw_auto.set(autostart_get())
            self.status(f"Autostart se nepodařilo nastavit: {e}", error=True)

    def status(self, text, error=False):
        self.status_lbl.configure(text=text, fg=self.T["warn"] if error else self.T["ok"])
        self.root.after(5000, lambda: self.status_lbl.cget("text") == text and self.status_lbl.configure(text=""))

    # ---------- okno
    def _titlebar(self, win):
        try:
            hwnd = E.u32.GetParent(win.winfo_id())
            v = ctypes.c_int(1 if self.dark else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), 4)
        except Exception:
            pass

    def show(self):
        ok = E.device_present(self.cfg.get("device_match", ""))
        self.dev_lbl.configure(text="● přijímač myši připojen" if ok else "○ přijímač myši nenalezen",
                               fg=self.T["ok"] if ok else self.T["warn"])
        self.sw_auto.set(autostart_get())
        self.root.deiconify()
        self._titlebar(self.root)
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
