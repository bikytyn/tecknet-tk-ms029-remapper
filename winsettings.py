"""Systémové nastavení myši ve Windows (SystemParametersInfo + registry). Změny platí hned a trvale."""
import ctypes
import os
import winreg
from ctypes import wintypes as W

u32 = ctypes.WinDLL("user32", use_last_error=True)
SPI = u32.SystemParametersInfoW
SPI.argtypes = [W.UINT, W.UINT, ctypes.c_void_p, W.UINT]
SPI.restype = W.BOOL
u32.GetDoubleClickTime.restype = W.UINT
u32.GetSystemMetrics.argtypes = [ctypes.c_int]
u32.LoadImageW.argtypes = [W.HINSTANCE, W.LPCWSTR, W.UINT, ctypes.c_int, ctypes.c_int, W.UINT]
u32.LoadImageW.restype = W.HANDLE

UPD = 0x01 | 0x02  # SPIF_UPDATEINIFILE | SPIF_SENDCHANGE

SPI_GETMOUSE, SPI_SETMOUSE = 0x0003, 0x0004
SPI_SETDOUBLECLICKTIME, SPI_SETMOUSEBUTTONSWAP = 0x0020, 0x0021
SPI_SETCURSORS = 0x0057
SPI_SETMOUSETRAILS, SPI_GETMOUSETRAILS = 0x005D, 0x005E
SPI_GETSNAPTODEFBUTTON, SPI_SETSNAPTODEFBUTTON = 0x005F, 0x0060
SPI_GETWHEELSCROLLLINES, SPI_SETWHEELSCROLLLINES = 0x0068, 0x0069
SPI_GETWHEELSCROLLCHARS, SPI_SETWHEELSCROLLCHARS = 0x006C, 0x006D
SPI_GETMOUSESPEED, SPI_SETMOUSESPEED = 0x0070, 0x0071
SPI_GETMOUSESONAR, SPI_SETMOUSESONAR = 0x101C, 0x101D
SPI_GETMOUSEVANISH, SPI_SETMOUSEVANISH = 0x1020, 0x1021
SPI_GETMOUSEWHEELROUTING, SPI_SETMOUSEWHEELROUTING = 0x201C, 0x201D
SPI_SETCURSORSIZE = 0x2029  # nedokumentované – používá ho Nastavení Windows 11 (Usnadnění › Ukazatel myši)
WHEEL_PAGESCROLL = 0xFFFFFFFF

CURSOR_ORDER = ["Arrow", "Help", "AppStarting", "Wait", "Crosshair", "IBeam", "NWPen", "No", "SizeNS",
                "SizeWE", "SizeNWSE", "SizeNESW", "SizeAll", "UpArrow", "Hand", "Pin", "Person"]
PREVIEW = ["Arrow", "Hand", "IBeam", "AppStarting"]
DEFAULT_FILES = {  # výchozí kurzory Windows (pro náhled schématu bez souborů)
    "Arrow": r"%SystemRoot%\cursors\aero_arrow.cur", "Hand": r"%SystemRoot%\cursors\aero_link.cur",
    "IBeam": r"%SystemRoot%\cursors\beam_r.cur", "AppStarting": r"%SystemRoot%\cursors\aero_working.ani",
}
CURSORS_KEY = r"Control Panel\Cursors"
SCHEMES = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Control Panel\Cursors\Schemes", 2),
           (winreg.HKEY_CURRENT_USER, r"Control Panel\Cursors\Schemes", 1)]

DEFAULTS = {"speed": 10, "accel": True, "lines": 3, "chars": 3, "swap": False, "dblclick": 500,
            "hover_scroll": True, "sonar": False, "vanish": True, "snap": False, "trails": 0, "cursor_size": 1}


def _check(ok):
    if not ok:
        raise OSError(ctypes.get_last_error(), "SystemParametersInfo selhalo")


def _get(action, ctype=ctypes.c_int):
    v = ctype()
    _check(SPI(action, 0, ctypes.byref(v), 0))
    return v.value


def _set_ui(action, value):
    _check(SPI(action, value, None, UPD))


def _set_pv(action, value):
    _check(SPI(action, 0, ctypes.c_void_p(value) if value else None, UPD))


# ---------------------------------------------------------------- ukazatel

def get_speed():
    return _get(SPI_GETMOUSESPEED)


def set_speed(v):
    _set_pv(SPI_SETMOUSESPEED, max(1, min(20, int(v))))


def get_accel():
    arr = (ctypes.c_int * 3)()
    _check(SPI(SPI_GETMOUSE, 0, arr, 0))
    return arr[2] != 0


def set_accel(on):
    arr = (ctypes.c_int * 3)(*((6, 10, 1) if on else (0, 0, 0)))
    _check(SPI(SPI_SETMOUSE, 0, arr, UPD))


# ---------------------------------------------------------------- kolečko

def get_lines():
    """počet řádků, nebo -1 = po celých stránkách"""
    v = _get(SPI_GETWHEELSCROLLLINES, ctypes.c_uint)
    return -1 if v == WHEEL_PAGESCROLL else v


def set_lines(v):
    _set_ui(SPI_SETWHEELSCROLLLINES, WHEEL_PAGESCROLL if v < 0 else max(1, min(100, int(v))))


def get_chars():
    return _get(SPI_GETWHEELSCROLLCHARS, ctypes.c_uint)


def set_chars(v):
    _set_ui(SPI_SETWHEELSCROLLCHARS, max(1, min(100, int(v))))


def get_hover_scroll():
    return _get(SPI_GETMOUSEWHEELROUTING, W.DWORD) == 2


def set_hover_scroll(on):
    _set_pv(SPI_SETMOUSEWHEELROUTING, 2 if on else 0)


# ---------------------------------------------------------------- tlačítka

def get_swap():
    return bool(u32.GetSystemMetrics(23))  # SM_SWAPBUTTON


def set_swap(on):
    _set_ui(SPI_SETMOUSEBUTTONSWAP, 1 if on else 0)


def get_dblclick():
    return int(u32.GetDoubleClickTime())


def set_dblclick(ms):
    _set_ui(SPI_SETDOUBLECLICKTIME, max(200, min(900, int(ms))))


# ---------------------------------------------------------------- drobnosti

def get_bool(name):
    act = {"sonar": SPI_GETMOUSESONAR, "vanish": SPI_GETMOUSEVANISH, "snap": SPI_GETSNAPTODEFBUTTON}[name]
    return bool(_get(act, W.BOOL))


def set_bool(name, on):
    if name == "snap":
        _set_ui(SPI_SETSNAPTODEFBUTTON, 1 if on else 0)
    else:
        _set_pv({"sonar": SPI_SETMOUSESONAR, "vanish": SPI_SETMOUSEVANISH}[name], 1 if on else 0)


def get_trails():
    v = _get(SPI_GETMOUSETRAILS)
    return v if v > 1 else 0


def set_trails(n):
    _set_ui(SPI_SETMOUSETRAILS, n if n > 1 else 0)


# ---------------------------------------------------------------- kurzory

def _reg_get(hive, path, name, default=None):
    try:
        with winreg.OpenKey(hive, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return default


def get_cursor_size():
    """1..15 jako v Nastavení Windows 11"""
    v = _reg_get(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Accessibility", "CursorSize", 1)
    try:
        return max(1, min(15, int(v)))
    except (TypeError, ValueError):
        return 1


def set_cursor_size(n):
    n = max(1, min(15, int(n)))
    base = 32 + (n - 1) * 16
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Accessibility") as k:
        winreg.SetValueEx(k, "CursorSize", 0, winreg.REG_DWORD, n)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CURSORS_KEY) as k:
        winreg.SetValueEx(k, "CursorBaseSize", 0, winreg.REG_DWORD, base)
    _set_pv(SPI_SETCURSORSIZE, base)


def list_schemes():
    """[{name, files: {Arrow: path,...}, source}] – systémová i uživatelská schémata."""
    out, seen = [], set()
    for hive, path, source in SCHEMES:
        try:
            with winreg.OpenKey(hive, path) as k:
                i = 0
                while True:
                    try:
                        name, data, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    i += 1
                    if not name or name in seen or not isinstance(data, str):
                        continue
                    seen.add(name)
                    parts = [p.strip() for p in data.split(",")]
                    out.append({"name": name, "source": source,
                                "files": {n: (parts[j] if j < len(parts) else "") for j, n in enumerate(CURSOR_ORDER)}})
        except OSError:
            pass
    return out


def current_scheme():
    return _reg_get(winreg.HKEY_CURRENT_USER, CURSORS_KEY, "", "") or ""


def apply_scheme(scheme):
    """scheme=None -> výchozí kurzory Windows."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CURSORS_KEY) as k:
        for n in CURSOR_ORDER:
            val = scheme["files"].get(n, "") if scheme else ""
            winreg.SetValueEx(k, n, 0, winreg.REG_EXPAND_SZ, val)
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, scheme["name"] if scheme else "")
        winreg.SetValueEx(k, "Scheme Source", 0, winreg.REG_DWORD, scheme["source"] if scheme else 0)
    _check(SPI(SPI_SETCURSORS, 0, None, UPD))
    # vlastní velikost (Win 11) by se po přepnutí schématu ztratila
    size = get_cursor_size()
    if size > 1:
        _set_pv(SPI_SETCURSORSIZE, 32 + (size - 1) * 16)


def load_cursor(path, size):
    """HICON kurzoru ze souboru (.cur/.ani), nebo None."""
    p = os.path.expandvars(path or "")
    if not p or not os.path.exists(p):
        return None
    return u32.LoadImageW(None, p, 2, size, size, 0x10) or None  # IMAGE_CURSOR, LR_LOADFROMFILE


# ---------------------------------------------------------------- instalace sad kurzorů

import re
import shutil
import tempfile
import zipfile

CURSOR_LINKS = [("RW Designer – Cursor library", "https://www.rw-designer.com/cursor-library"),
                ("DeviantArt – Windows cursors", "https://www.deviantart.com/search?q=windows%20cursors")]
INSTALL_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TecknetRemap", "Cursors")
CUR_EXT = (".cur", ".ani")

# odhad role podle názvu souboru (když sada nemá install.inf)
GUESS = [("Arrow", r"normal|arrow|pointer|select|default"), ("Help", r"help|question"),
         ("AppStarting", r"working|appstart|background|work"), ("Wait", r"busy|wait|loading"),
         ("Crosshair", r"precision|cross"), ("IBeam", r"text|beam|ibeam"), ("NWPen", r"handwrit|pen"),
         ("No", r"unavail|forbid|^no$|^not"), ("SizeNS", r"vert|sizens|^ns"), ("SizeWE", r"horz|horiz|sizewe|^we"),
         ("SizeNWSE", r"dgn1|diag1|nwse"), ("SizeNESW", r"dgn2|diag2|nesw"), ("SizeAll", r"move|sizeall"),
         ("UpArrow", r"alt|up"), ("Hand", r"link|hand"), ("Pin", r"pin|location"), ("Person", r"person")]


def _read_text(path):
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace")


def _parse_inf(path):
    """-> (název schématu, [soubor pro každou roli v pořadí CURSOR_ORDER])"""
    text = _read_text(path)
    strings, section = {}, ""
    for line in text.splitlines():
        s = line.split(";", 1)[0].strip()
        if s.startswith("[") and s.endswith("]"):
            section = s[1:-1].strip().lower()
        elif section == "strings" and "=" in s:
            k, v = s.split("=", 1)
            strings[k.strip().lower()] = v.strip().strip('"')
    name, files = None, []
    for line in text.splitlines():
        if "cursors\\schemes" in line.lower() and "hkcu" in line.lower():
            quoted = re.findall(r'"([^"]*)"', line)
            if len(quoted) >= 3:
                nm = quoted[1]
                name = strings.get(nm.strip("%").lower(), nm) if nm.startswith("%") else nm
                for item in quoted[-1].split(","):
                    vars_ = re.findall(r"%(\w+)%", item)
                    tail = item.replace("\\", "/").rsplit("/", 1)[-1]
                    if vars_ and vars_[-1].lower() in strings and tail.startswith("%"):
                        files.append(strings[vars_[-1].lower()])
                    else:
                        files.append(tail.strip("%"))
                break
    return (name or strings.get("scheme_name")), files


def install_pack(paths):
    """Nainstaluje sadu kurzorů (zip / inf / složka / .cur+.ani) do uživatelského profilu a vrátí schéma."""
    tmp = None
    try:
        found, infs = {}, []

        def add(p):
            low = p.lower()
            if low.endswith(CUR_EXT):
                found.setdefault(os.path.basename(low), p)
            elif low.endswith(".inf"):
                infs.append(p)

        base_name = None
        for p in paths:
            if p.lower().endswith(".zip"):
                tmp = tmp or tempfile.mkdtemp(prefix="tecknet_cur_")
                with zipfile.ZipFile(p) as z:
                    for info in z.infolist():
                        fn = os.path.basename(info.filename.replace("\\", "/"))
                        if fn and fn.lower().endswith(CUR_EXT + (".inf",)) and info.file_size < 5_000_000:
                            dest = os.path.join(tmp, fn)  # jen název souboru – žádné cesty z archivu
                            with z.open(info) as src, open(dest, "wb") as out:
                                shutil.copyfileobj(src, out)
                            add(dest)
                base_name = base_name or os.path.splitext(os.path.basename(p))[0]
            elif os.path.isdir(p):
                for root, _, fns in os.walk(p):
                    for fn in fns:
                        add(os.path.join(root, fn))
                base_name = base_name or os.path.basename(p.rstrip("\\/"))
            else:
                add(p)
                if p.lower().endswith(".inf"):
                    folder = os.path.dirname(p)
                    for fn in os.listdir(folder):
                        add(os.path.join(folder, fn))
                base_name = base_name or os.path.splitext(os.path.basename(p))[0]
        if not found:
            raise OSError("v souborech nejsou žádné kurzory .cur/.ani")

        name, roles = None, {}
        for inf in infs:
            n, files = _parse_inf(inf)
            if files:
                name = n
                for role, fn in zip(CURSOR_ORDER, files):
                    src = found.get(os.path.basename(fn).lower())
                    if src:
                        roles[role] = src
                break
        if "Arrow" not in roles:  # bez inf: odhad podle názvů
            unused = dict(found)
            for role, pat in GUESS:
                if role in roles:
                    continue
                for key in list(unused):
                    if re.search(pat, os.path.splitext(key)[0]):
                        roles[role] = unused.pop(key)
                        break
            if "Arrow" not in roles and len(found) == 1:
                roles["Arrow"] = next(iter(found.values()))
        if "Arrow" not in roles:
            raise OSError("nepodařilo se poznat hlavní kurzor (šipku)")

        name = (name or base_name or "Custom").strip()[:60]
        safe = re.sub(r'[<>:"/\\|?*]', "_", name)
        dest_dir = os.path.join(INSTALL_DIR, safe)
        os.makedirs(dest_dir, exist_ok=True)
        files = {}
        for role in CURSOR_ORDER:
            src = roles.get(role)
            if src:
                dst = os.path.join(dest_dir, os.path.basename(src))
                if os.path.abspath(src) != os.path.abspath(dst):
                    shutil.copy2(src, dst)
                files[role] = dst
            else:
                files[role] = ""
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Cursors\Schemes") as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_EXPAND_SZ, ",".join(files[r] for r in CURSOR_ORDER))
        return {"name": name, "source": 1, "files": files}
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def delete_scheme(name):
    """Smaže uživatelské schéma (HKCU); soubory smaže jen pokud jsou v naší složce."""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Cursors\Schemes", 0, winreg.KEY_SET_VALUE) as k:
        winreg.DeleteValue(k, name)
    folder = os.path.join(INSTALL_DIR, re.sub(r'[<>:"/\\|?*]', "_", name))
    if os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------- souhrn

def read_all():
    def safe(fn, default):
        try:
            return fn()
        except OSError:
            return default

    return {
        "speed": safe(get_speed, 10), "accel": safe(get_accel, True), "lines": safe(get_lines, 3),
        "chars": safe(get_chars, 3), "swap": safe(get_swap, False), "dblclick": safe(get_dblclick, 500),
        "hover_scroll": safe(get_hover_scroll, True), "sonar": safe(lambda: get_bool("sonar"), False),
        "vanish": safe(lambda: get_bool("vanish"), True), "snap": safe(lambda: get_bool("snap"), False),
        "trails": safe(get_trails, 0), "cursor_size": get_cursor_size(), "scheme": current_scheme(),
    }


def open_windows_settings():
    os.startfile("ms-settings:mousetouchpad")


def open_classic_panel():
    os.startfile("main.cpl")
