"""Jádro: low-level mouse hook + Raw Input (rozlišení zařízení) + SendInput + tray ikona.

Princip:
  * WH_MOUSE_LL hook zachytí XBUTTON1/2 a WM_MOUSEHWHEEL (jen fyzické, ne injektované) a pohltí je.
  * Raw Input (WM_INPUT) řekne, ze kterého zařízení událost přišla.
  * Události se spárují (v libovolném pořadí). Z Tecknetu -> akce podle profilu aplikace v popředí,
    z jiné myši (nebo bez páru do 150 ms) -> původní událost se pošle zpět přes SendInput.
"""
import ctypes
import os
import subprocess
import threading
import time
from collections import deque
from ctypes import wintypes as W

import config as C
from i18n import t as T

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
sh32 = ctypes.WinDLL("shell32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, W.WPARAM, W.LPARAM)

# ---------------------------------------------------------------- struktury


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", W.HINSTANCE), ("hIcon", W.HICON),
                ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH), ("lpszMenuName", W.LPCWSTR),
                ("lpszClassName", W.LPCWSTR)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", W.POINT), ("mouseData", W.DWORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("_pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", W.DWORD), ("u", _INPUTUNION)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", W.USHORT), ("usUsage", W.USHORT), ("dwFlags", W.DWORD), ("hwndTarget", W.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", W.DWORD), ("dwSize", W.DWORD), ("hDevice", W.HANDLE), ("wParam", W.WPARAM)]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [("usFlags", W.USHORT), ("_pad", W.USHORT), ("usButtonFlags", W.USHORT),
                ("usButtonData", W.USHORT), ("ulRawButtons", W.ULONG), ("lLastX", W.LONG),
                ("lLastY", W.LONG), ("ulExtra", W.ULONG)]


class RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [("hDevice", W.HANDLE), ("dwType", W.DWORD)]


class GUID(ctypes.Structure):
    _fields_ = [("a", W.DWORD), ("b", W.WORD), ("c", W.WORD), ("d", ctypes.c_byte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("hWnd", W.HWND), ("uID", W.UINT), ("uFlags", W.UINT),
                ("uCallbackMessage", W.UINT), ("hIcon", W.HICON), ("szTip", W.WCHAR * 128),
                ("dwState", W.DWORD), ("dwStateMask", W.DWORD), ("szInfo", W.WCHAR * 256),
                ("uVersion", W.UINT), ("szInfoTitle", W.WCHAR * 64), ("dwInfoFlags", W.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", W.HICON)]


# ---------------------------------------------------------------- signatury

def _sig(fn, res, *args):
    fn.restype = res
    fn.argtypes = list(args)


_sig(u32.DefWindowProcW, LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
_sig(u32.CallNextHookEx, LRESULT, W.HHOOK, ctypes.c_int, W.WPARAM, W.LPARAM)
_sig(u32.SetWindowsHookExW, W.HHOOK, ctypes.c_int, HOOKPROC, W.HINSTANCE, W.DWORD)
_sig(u32.UnhookWindowsHookEx, W.BOOL, W.HHOOK)
_sig(u32.CreateWindowExW, W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int,
     ctypes.c_int, ctypes.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID)
_sig(u32.PostMessageW, W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
_sig(u32.GetRawInputData, W.UINT, W.HANDLE, W.UINT, ctypes.c_void_p, ctypes.POINTER(W.UINT), W.UINT)
_sig(u32.GetRawInputDeviceInfoW, W.UINT, W.HANDLE, W.UINT, ctypes.c_void_p, ctypes.POINTER(W.UINT))
_sig(u32.GetRawInputDeviceList, W.UINT, ctypes.c_void_p, ctypes.POINTER(W.UINT), W.UINT)
_sig(u32.SendInput, W.UINT, W.UINT, ctypes.c_void_p, ctypes.c_int)
_sig(u32.MapVirtualKeyW, W.UINT, W.UINT, W.UINT)
_sig(u32.GetForegroundWindow, W.HWND)
_sig(u32.GetWindowThreadProcessId, W.DWORD, W.HWND, ctypes.POINTER(W.DWORD))
_sig(u32.SetTimer, ULONG_PTR, W.HWND, ULONG_PTR, W.UINT, ctypes.c_void_p)
_sig(u32.KillTimer, W.BOOL, W.HWND, ULONG_PTR)
_sig(u32.LoadImageW, W.HANDLE, W.HINSTANCE, W.LPCWSTR, W.UINT, ctypes.c_int, ctypes.c_int, W.UINT)
_sig(u32.CreatePopupMenu, W.HMENU)
_sig(u32.AppendMenuW, W.BOOL, W.HMENU, W.UINT, ULONG_PTR, W.LPCWSTR)
_sig(u32.TrackPopupMenu, W.BOOL, W.HMENU, W.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HWND, ctypes.c_void_p)
_sig(u32.DestroyMenu, W.BOOL, W.HMENU)
_sig(u32.SetForegroundWindow, W.BOOL, W.HWND)
_sig(u32.GetCursorPos, W.BOOL, ctypes.POINTER(W.POINT))
_sig(u32.RegisterWindowMessageW, W.UINT, W.LPCWSTR)
_sig(u32.DestroyWindow, W.BOOL, W.HWND)
_sig(u32.FindWindowW, W.HWND, W.LPCWSTR, W.LPCWSTR)
_sig(u32.IsWindowVisible, W.BOOL, W.HWND)
_sig(u32.GetWindowTextW, ctypes.c_int, W.HWND, W.LPWSTR, ctypes.c_int)
_sig(u32.GetWindow, W.HWND, W.HWND, W.UINT)
_sig(u32.GetWindowLongW, W.LONG, W.HWND, ctypes.c_int)
_sig(sh32.Shell_NotifyIconW, W.BOOL, W.DWORD, ctypes.POINTER(NOTIFYICONDATAW))
_sig(k32.GetModuleHandleW, W.HMODULE, W.LPCWSTR)
_sig(k32.OpenProcess, W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
_sig(k32.CloseHandle, W.BOOL, W.HANDLE)
_sig(k32.QueryFullProcessImageNameW, W.BOOL, W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD))

# ---------------------------------------------------------------- konstanty

WH_MOUSE_LL = 14
WM_DESTROY, WM_CLOSE, WM_TIMER, WM_INPUT, WM_NULL = 0x0002, 0x0010, 0x0113, 0x00FF, 0x0000
WM_XBUTTONDOWN, WM_XBUTTONUP, WM_MOUSEHWHEEL = 0x020B, 0x020C, 0x020E
WM_LBUTTONUP, WM_RBUTTONUP, WM_LBUTTONDBLCLK = 0x0202, 0x0205, 0x0203
WM_APP = 0x8000
WM_APP_MATCH, WM_APP_TRAY, WM_APP_SHOW, WM_APP_REFRESH = WM_APP + 1, WM_APP + 2, WM_APP + 3, WM_APP + 4
# zprávy od okna nastavení (samostatný proces) -> jádro
WM_APP_HELLO = WM_APP + 5    # wParam = UDP port okna (0 = okno končí)
WM_APP_RELOAD = WM_APP + 6   # znovu načíst config.json
WM_APP_MEASURE = WM_APP + 7  # wParam 1 = začít, 0 = skončit (výsledek jde UDP zprávou „measure“)
WM_APP_ANCHOR = WM_APP + 8   # wParam = stupeň DPI
WM_APP_STATUS = WM_APP + 9   # pošli stav sledování DPI
TIMER_SAVE = 3
GUI_MUTEX = "Local\\TecknetRemapGui"
TRACK_PATH = os.path.join(C.CFG_DIR, "dpi_track.json")
LLMHF_INJECTED = 0x01
RID_INPUT, RIDI_DEVICENAME, RIDEV_INPUTSINK, RIM_TYPEMOUSE = 0x10000003, 0x20000007, 0x100, 0
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP, MOUSEEVENTF_HWHEEL = 0x0080, 0x0100, 0x01000
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x0001, 0x0002
MAGIC = 0x54454B4E  # "TEKN" – podpis našich injektovaných událostí
TIMER_MATCH, TIMER_REHOOK = 1, 2
MATCH_TIMEOUT = 0.15
RAW_TTL = 0.5
WHEEL_DELTA = 120
HDR = ctypes.sizeof(RAWINPUTHEADER)
WINDOW_CLASS = "TecknetRemapEngine"

# ---------------------------------------------------------------- klávesy

VK = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "tab": 0x09, "enter": 0x0D, "esc": 0x1B, "escape": 0x1B, "space": 0x20, "backspace": 0x08,
    "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "capslock": 0x14, "apps": 0x5D, "menu": 0x5D,
    "plus": 0xBB, "minus": 0xBD, "comma": 0xBC, "period": 0xBE,
    "num_plus": 0x6B, "num_minus": 0x6D, "num_multiply": 0x6A, "num_divide": 0x6F,
    "volume_up": 0xAF, "volume_down": 0xAE, "volume_mute": 0xAD,
    "media_next": 0xB0, "media_prev": 0xB1, "media_stop": 0xB2, "media_play_pause": 0xB3,
    "browser_back": 0xA6, "browser_forward": 0xA7, "browser_refresh": 0xA8, "browser_home": 0xAC,
}
VK.update({chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)})
VK.update({str(d): 0x30 + d for d in range(10)})
VK.update({f"f{i}": 0x6F + i for i in range(1, 25)})
EXTENDED = {0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x5B, 0x5D, 0x6F,
            0xAF, 0xAE, 0xAD, 0xB0, 0xB1, 0xB2, 0xB3, 0xA6, 0xA7, 0xA8, 0xAC}
VK_TO_NAME = {}
for _n, _v in VK.items():
    VK_TO_NAME.setdefault(_v, _n)
VK_TO_NAME[0x11], VK_TO_NAME[0x5B] = "ctrl", "win"


def parse_combo(text):
    """'ctrl+shift+tab' -> [vk, ...]; vyhodí ValueError u neznámé klávesy."""
    parts = [p.strip().lower() for p in text.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise ValueError("prázdná zkratka")
    out = []
    for p in parts:
        if p not in VK:
            raise ValueError(f"neznámá klávesa „{p}“")
        out.append(VK[p])
    return out


def _key_input(vk, up):
    i = INPUT(type=INPUT_KEYBOARD)
    i.u.ki.wVk = vk
    i.u.ki.wScan = u32.MapVirtualKeyW(vk, 0)
    i.u.ki.dwFlags = (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED else 0) | (KEYEVENTF_KEYUP if up else 0)
    i.u.ki.dwExtraInfo = MAGIC
    return i


def _mouse_input(flags, data=0):
    i = INPUT(type=INPUT_MOUSE)
    i.u.mi.dwFlags = flags
    i.u.mi.mouseData = data & 0xFFFFFFFF
    i.u.mi.dwExtraInfo = MAGIC
    return i


def send(inputs):
    if not inputs:
        return
    arr = (INPUT * len(inputs))(*inputs)
    u32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


# ---------------------------------------------------------------- pomocné funkce


def exe_of_hwnd(hwnd):
    pid = W.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = W.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return os.path.basename(buf.value).lower()
    finally:
        k32.CloseHandle(h)
    return None


def foreground_exe():
    hwnd = u32.GetForegroundWindow()
    return exe_of_hwnd(hwnd) if hwnd else None


def list_window_apps():
    """Seznam (exe, titulek) aplikací s viditelným oknem – pro dialog „Přidat aplikaci“."""
    found = {}
    EnumProc = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    def cb(hwnd, _):
        if not u32.IsWindowVisible(hwnd) or u32.GetWindow(hwnd, 4):  # GW_OWNER
            return True
        if u32.GetWindowLongW(hwnd, -20) & 0x80:  # WS_EX_TOOLWINDOW
            return True
        buf = ctypes.create_unicode_buffer(256)
        if u32.GetWindowTextW(hwnd, buf, 256) <= 0:
            return True
        exe = exe_of_hwnd(hwnd)
        if exe and exe not in found:
            found[exe] = buf.value
        return True

    u32.EnumWindows(EnumProc(cb), 0)
    return sorted(found.items())


def device_name(h):
    n = W.UINT(0)
    u32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, None, ctypes.byref(n))
    buf = ctypes.create_unicode_buffer(n.value + 1)
    u32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, buf, ctypes.byref(n))
    return buf.value


def device_matches(name, match):
    """match = podřetězec nebo seznam podřetězců názvu zařízení (USB přijímač, Bluetooth…)."""
    pats = [match] if isinstance(match, str) else list(match or [])
    low = name.lower()
    return any(p and p.lower() in low for p in pats)


def connected_mice(match):
    """Názvy připojených myší, které odpovídají match."""
    n = W.UINT(0)
    sz = ctypes.sizeof(RAWINPUTDEVICELIST)
    u32.GetRawInputDeviceList(None, ctypes.byref(n), sz)
    arr = (RAWINPUTDEVICELIST * n.value)()
    cnt = u32.GetRawInputDeviceList(arr, ctypes.byref(n), sz)
    out = []
    for i in range(min(cnt, n.value)):
        if arr[i].dwType == RIM_TYPEMOUSE:
            name = device_name(arr[i].hDevice)
            if device_matches(name, match):
                out.append(name)
    return out


def device_present(match):
    return bool(connected_mice(match))


def is_bluetooth(name):
    return "{00001812-0000-1000-8000-00805f9b34fb}" in name.lower()  # služba HID over GATT


# ---------------------------------------------------------------- engine


class Engine:
    def __init__(self, cfg, notify):
        """notify(kind, *args) – volá se z vlákna enginu (GUI si to předá do své fronty)."""
        self.cfg = cfg
        self.notify = notify
        self.hwnd = None
        self.hook = None
        self.msg_taskbar = None  # wndproc dostává zprávy už během CreateWindowEx
        self.measuring = False   # měření DPI: součet surových posunů z cílové myši
        self.meas_dx = self.meas_dy = self.meas_n = 0
        self.tracker = None      # DpiTracker – pasivní sledování stupně DPI
        self.gui_port = None     # UDP port okna nastavení (samostatný proces)
        self._stepper = None     # audio.VolumeStepper – vlastní krok hlasitosti
        self._sock = None
        self.pending = deque()  # (key, payload, t)
        self.raws = deque()     # (key, is_target, t)
        self.dev_cache = {}
        self.held = {}          # btn -> akce použitá při stisku
        self.hacc = 0
        self._thread = None
        self._ready = threading.Event()
        self._log = None

    # ---------- veřejné API (volatelné z jiného vlákna)
    def start(self):
        self._thread = threading.Thread(target=self._run, name="engine", daemon=True)
        self._thread.start()
        self._ready.wait(5)

    def stop(self):
        if self.hwnd:
            u32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        if self._thread:
            self._thread.join(3)

    # ---------- spojení s oknem nastavení (samostatný proces)
    def send_gui(self, kind, *args):
        if not self.gui_port:
            return
        import json
        import socket
        try:
            if self._sock is None:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.sendto(json.dumps({"k": kind, "a": list(args)}).encode("utf-8"),
                              ("127.0.0.1", self.gui_port))
        except OSError:
            self.gui_port = None

    def reload(self):
        import i18n
        self.cfg = C.load_config()
        i18n.set_lang(self.cfg.get("language", "en"))
        self.dev_cache.clear()
        if self.hwnd:
            self._tray_update()

    def save_tracker(self):
        if not self.tracker:
            return
        import json
        try:
            os.makedirs(C.CFG_DIR, exist_ok=True)
            tmp = TRACK_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.tracker.export(), f)
            os.replace(tmp, TRACK_PATH)
        except OSError:
            pass

    def measure_begin(self):
        self.meas_dx = self.meas_dy = self.meas_n = 0
        self.measuring = True

    def measure_end(self):
        """-> (dx, dy, počet zpráv) surových bodů senzoru od measure_begin"""
        self.measuring = False
        return self.meas_dx, self.meas_dy, self.meas_n

    def set_config(self, cfg):
        self.cfg = cfg
        if self.hwnd:
            u32.PostMessageW(self.hwnd, WM_APP_REFRESH, 0, 0)

    # ---------- log
    def log(self, msg):
        if not self.cfg.get("debug"):
            return
        try:
            if self._log is None:
                os.makedirs(C.CFG_DIR, exist_ok=True)
                self._log = open(C.LOG_PATH, "a", encoding="utf-8")
            self._log.write(f"{time.strftime('%H:%M:%S')}.{int(time.time()*1000)%1000:03d} {msg}\n")
            self._log.flush()
        except OSError:
            pass

    # ---------- vlákno enginu
    def _run(self):
        hinst = k32.GetModuleHandleW(None)
        self._wndproc = WNDPROC(self._wnd)
        self._hookproc = HOOKPROC(self._hook)
        wc = WNDCLASSW(lpfnWndProc=self._wndproc, hInstance=hinst, lpszClassName=WINDOW_CLASS)
        u32.RegisterClassW(ctypes.byref(wc))
        # skryté top-level okno (kvůli tray menu a SetForegroundWindow), nikdy se nezobrazí
        self.hwnd = u32.CreateWindowExW(0x80, WINDOW_CLASS, "Tecknet Remap", 0x80000000,
                                        0, 0, 0, 0, None, None, hinst, None)
        self.msg_taskbar = u32.RegisterWindowMessageW("TaskbarCreated")
        rid = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, self.hwnd)
        if not u32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE)):
            self.notify("error", f"Raw Input se nepodařilo zaregistrovat ({ctypes.get_last_error()})")
        self._install_hook()
        u32.SetTimer(self.hwnd, TIMER_REHOOK, 60_000, None)
        u32.SetTimer(self.hwnd, TIMER_SAVE, 120_000, None)
        self._tray_add()
        self._ready.set()
        msg = W.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
        if self.hook:
            u32.UnhookWindowsHookEx(self.hook)

    def _install_hook(self):
        # Windows tiše odstraní LL hook, který jednou nestihne odpovědět -> pravidelně ho obnovujeme.
        new = u32.SetWindowsHookExW(WH_MOUSE_LL, self._hookproc, k32.GetModuleHandleW(None), 0)
        if not new:
            self.notify("error", f"Hook myši se nepodařilo nainstalovat ({ctypes.get_last_error()})")
            return
        old, self.hook = self.hook, new
        if old:
            u32.UnhookWindowsHookEx(old)

    # ---------- hook (musí být rychlý!)
    def _hook(self, n, wp, lp):
        if n == 0 and (wp == WM_XBUTTONDOWN or wp == WM_XBUTTONUP or wp == WM_MOUSEHWHEEL) \
                and self.cfg.get("enabled", True):
            ms = MSLLHOOKSTRUCT.from_address(lp)
            if not (ms.flags & LLMHF_INJECTED):
                hi = (ms.mouseData >> 16) & 0xFFFF
                if wp == WM_MOUSEHWHEEL:
                    key, payload = "h", ctypes.c_short(hi).value
                elif hi in (1, 2):
                    key, payload = (f"x{hi}", wp == WM_XBUTTONDOWN), None
                else:
                    return u32.CallNextHookEx(None, n, wp, lp)
                self.pending.append((key, payload, time.monotonic()))
                u32.PostMessageW(self.hwnd, WM_APP_MATCH, 0, 0)
                return 1  # pohltit
        return u32.CallNextHookEx(None, n, wp, lp)

    # ---------- okno
    def _wnd(self, hwnd, msg, wp, lp):
        try:
            if msg == WM_INPUT:
                self._on_raw(lp)
                self._match()
            elif msg == WM_APP_MATCH:
                self._match()
            elif msg == WM_TIMER:
                if wp == TIMER_MATCH:
                    self._match()
                elif wp == TIMER_REHOOK:
                    self._install_hook()
                elif wp == TIMER_SAVE:
                    self.save_tracker()
            elif msg == WM_APP_HELLO:
                self.gui_port = int(wp) or None
                if self.gui_port and self.tracker:
                    self.send_gui("dpi_status", self.tracker.status())
                return 0
            elif msg == WM_APP_RELOAD:
                self.reload()
                return 0
            elif msg == WM_APP_MEASURE:
                if wp:
                    self.measure_begin()
                else:
                    self.send_gui("measure", *self.measure_end())
                return 0
            elif msg == WM_APP_ANCHOR:
                if self.tracker:
                    self.tracker.anchor(int(wp))
                    self.save_tracker()
                    self.send_gui("dpi_status", self.tracker.status())
                return 0
            elif msg == WM_APP_STATUS:
                if self.tracker:
                    self.send_gui("dpi_status", self.tracker.status())
                return 0
            elif msg == WM_APP_TRAY:
                if lp in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self.notify("show")
                elif lp == WM_RBUTTONUP:
                    self._tray_menu()
                return 0
            elif msg == WM_APP_REFRESH:
                self.dev_cache.clear()
                self._tray_update()
                return 0
            elif msg == self.msg_taskbar and msg:
                self._tray_add()
            elif msg == WM_CLOSE:
                self._tray_del()
                u32.DestroyWindow(hwnd)
                return 0
            elif msg == WM_DESTROY:
                u32.PostQuitMessage(0)
                return 0
        except Exception as e:  # nikdy nespadnout ve wndproc
            self.log(f"ERROR {e!r}")
        return u32.DefWindowProcW(hwnd, msg, wp, lp)

    # ---------- raw input
    def _on_raw(self, lp):
        size = W.UINT(0)
        u32.GetRawInputData(lp, RID_INPUT, None, ctypes.byref(size), HDR)
        buf = ctypes.create_string_buffer(size.value)
        if u32.GetRawInputData(lp, RID_INPUT, buf, ctypes.byref(size), HDR) == 0xFFFFFFFF:
            return
        hdr = RAWINPUTHEADER.from_buffer_copy(buf, 0)
        if hdr.dwType != RIM_TYPEMOUSE or not hdr.hDevice:
            return  # hDevice 0 = injektovaný vstup
        m = RAWMOUSE.from_buffer_copy(buf, HDR)
        f = m.usButtonFlags
        if not (f & 0x3C0 or f & 0x800 or self.measuring or self.tracker):
            return
        h = hdr.hDevice
        if h not in self.dev_cache:
            name = device_name(h)
            self.dev_cache[h] = device_matches(name, self.cfg.get("device_match", ""))
            self.log(f"device {name} target={self.dev_cache[h]}")
        target = self.dev_cache[h]
        if target and not (m.usFlags & 0x1) and (m.lLastX or m.lLastY):  # jen relativní pohyb
            if self.measuring:
                self.meas_dx += m.lLastX
                self.meas_dy += m.lLastY
                self.meas_n += 1
            if self.tracker:
                new = self.tracker.feed(m.lLastX, m.lLastY)
                if new:
                    self.log(f"dpi tracker -> {new}")
                    self.notify("dpi", new)
        if not (f & 0x3C0 or f & 0x800):
            return
        t = time.monotonic()
        for bit, key in ((0x40, ("x1", True)), (0x80, ("x1", False)),
                         (0x100, ("x2", True)), (0x200, ("x2", False)), (0x800, "h")):
            if f & bit:
                self.raws.append((key, target, t))

    # ---------- párování hook <-> raw
    def _match(self):
        now = time.monotonic()
        while self.raws and now - self.raws[0][2] > RAW_TTL:
            self.raws.popleft()
        while self.pending:
            key, payload, t = self.pending[0]
            hit = next((r for r in self.raws if r[0] == key), None)
            if hit is not None:
                self.raws.remove(hit)
                self.pending.popleft()
                self._handle(key, payload, hit[1])
            elif now - t > MATCH_TIMEOUT:
                self.pending.popleft()
                self.log(f"no raw match for {key} -> passthrough")
                self._handle(key, payload, False)
            else:
                u32.SetTimer(self.hwnd, TIMER_MATCH, 20, None)
                return
        u32.KillTimer(self.hwnd, TIMER_MATCH)

    # ---------- akce
    def _reinject(self, key, payload):
        if key == "h":
            send([_mouse_input(MOUSEEVENTF_HWHEEL, payload)])
        else:
            btn, down = key
            send([_mouse_input(MOUSEEVENTF_XDOWN if down else MOUSEEVENTF_XUP, 1 if btn == "x1" else 2)])

    def _handle(self, key, payload, target):
        if not target:
            self._reinject(key, payload)
            return
        exe = foreground_exe()
        if key == "h":
            control = "hleft" if payload < 0 else "hright"
            action = C.resolve(self.cfg, exe, control)
            self.log(f"{control} delta={payload} in {exe} -> {action}")
            if action == "default":
                self._reinject(key, payload)
                return
            if (self.hacc < 0) != (payload < 0):
                self.hacc = 0
            self.hacc += payload
            fired = False
            while abs(self.hacc) >= WHEEL_DELTA:
                self.hacc -= WHEEL_DELTA if self.hacc > 0 else -WHEEL_DELTA
                self._do(action, "tap")
                fired = True
            if fired:
                self.notify("event", control, exe, action)
            return
        btn, down = key
        if down:
            action = C.resolve(self.cfg, exe, btn)
            self.held[btn] = action
            self.log(f"{btn} down in {exe} -> {action}")
            self.notify("event", btn, exe, action)
            if action == "default":
                self._reinject(key, payload)
            else:
                self._do(action, "down")
        else:
            action = self.held.pop(btn, None) or C.resolve(self.cfg, exe, btn)
            if action == "default":
                self._reinject(key, payload)
            else:
                self._do(action, "up")

    def _do(self, action, phase):
        """phase: 'down' (stisk), 'up' (uvolnění), 'tap' (stisk+uvolnění)."""
        dn, up = phase in ("down", "tap"), phase in ("up", "tap")
        if action in ("none", "default", "inherit"):
            return
        if action.startswith("mouse:"):
            what = action[6:]
            ev = []
            if what in ("x1", "x2"):
                data = 1 if what == "x1" else 2
                if dn:
                    ev.append(_mouse_input(MOUSEEVENTF_XDOWN, data))
                if up:
                    ev.append(_mouse_input(MOUSEEVENTF_XUP, data))
            elif what == "middle":
                if dn:
                    ev.append(_mouse_input(MOUSEEVENTF_MIDDLEDOWN))
                if up:
                    ev.append(_mouse_input(MOUSEEVENTF_MIDDLEUP))
            elif what in ("hleft", "hright") and dn:
                ev.append(_mouse_input(MOUSEEVENTF_HWHEEL, -WHEEL_DELTA if what == "hleft" else WHEEL_DELTA))
            send(ev)
        elif action.startswith("keys:"):
            try:
                vks = parse_combo(action[5:])
            except ValueError as e:
                self.log(f"bad combo {action}: {e}")
                return
            ev = []
            if dn:
                ev += [_key_input(v, False) for v in vks]
            if up:
                ev += [_key_input(v, True) for v in reversed(vks)]
            send(ev)
        elif action.startswith("run:") and dn:
            target = action[4:]
            threading.Thread(target=self._launch, args=(target,), daemon=True).start()

    def _launch(self, target):
        try:
            os.startfile(target)
        except OSError:
            try:
                subprocess.Popen(target, shell=True)
            except Exception as e:
                self.notify("error", f"Nelze spustit {target}: {e}")

    # ---------- tray
    def _nid(self):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        return nid

    def _tray_add(self):
        if not hasattr(self, "_hicon"):
            sz = u32.GetSystemMetrics(49)  # SM_CXSMICON
            self._hicon = u32.LoadImageW(None, C.ensure_icon(), 1, sz, sz, 0x10)
        nid = self._nid()
        nid.uFlags = 0x1 | 0x2 | 0x4  # MESSAGE | ICON | TIP
        nid.uCallbackMessage = WM_APP_TRAY
        nid.hIcon = self._hicon
        nid.szTip = self._tip()
        sh32.Shell_NotifyIconW(0, ctypes.byref(nid))

    def _tip(self):
        return "Tecknet Remap" + ("" if self.cfg.get("enabled", True) else T("tray_paused"))

    def _tray_update(self):
        nid = self._nid()
        nid.uFlags = 0x4
        nid.szTip = self._tip()
        sh32.Shell_NotifyIconW(1, ctypes.byref(nid))

    def _tray_del(self):
        nid = self._nid()
        sh32.Shell_NotifyIconW(2, ctypes.byref(nid))

    def _tray_menu(self):
        menu = u32.CreatePopupMenu()
        u32.AppendMenuW(menu, 0, 1, T("tray_settings"))
        u32.AppendMenuW(menu, 0x8 if self.cfg.get("enabled", True) else 0, 2, T("tray_enabled"))
        u32.AppendMenuW(menu, 0x800, 0, None)
        u32.AppendMenuW(menu, 0, 3, T("tray_quit"))
        pt = W.POINT()
        u32.GetCursorPos(ctypes.byref(pt))
        u32.SetForegroundWindow(self.hwnd)
        cmd = u32.TrackPopupMenu(menu, 0x0100 | 0x0002, pt.x, pt.y, 0, self.hwnd, None)  # RETURNCMD|RIGHTBUTTON
        u32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        u32.DestroyMenu(menu)
        if cmd == 1:
            self.notify("show")
        elif cmd == 2:
            self.notify("toggle")
        elif cmd == 3:
            self.notify("quit")


def gui_running():
    k32.OpenMutexW.restype = W.HANDLE
    h = k32.OpenMutexW(0x00100000, False, GUI_MUTEX)  # SYNCHRONIZE
    if h:
        k32.CloseHandle(h)
        return True
    return False


def launch_gui(*extra):
    import sys
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(w):
        exe = w
    subprocess.Popen([exe, os.path.join(C.APP_DIR, "remap.pyw"), "--gui", *extra])


def load_tracker_state(cfg):
    import json
    try:
        with open(TRACK_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return cfg.get("dpi_track")


def run_standalone(open_gui=False):
    """Jádro jako samostatný lehký proces (bez okna). Okno nastavení je zvláštní proces (--gui)."""
    import i18n
    cfg = C.load_config()
    i18n.set_lang(cfg.get("language", "en"))
    eng = Engine(cfg, lambda *a: None)  # bez sledování DPI (odstraněno – nefungovalo spolehlivě)

    def notify(kind, *args):
        if kind == "show":
            if gui_running():
                eng.send_gui("show")
            else:
                launch_gui()
        elif kind == "toggle":
            c = C.load_config()
            c["enabled"] = not c.get("enabled", True)
            C.save_config(c)
            eng.reload()
            eng.send_gui("reload")
        elif kind == "quit":
            eng.send_gui("quit")
            u32.PostMessageW(eng.hwnd, WM_CLOSE, 0, 0)
        else:  # event, error -> do okna
            eng.send_gui(kind, *args)

    eng.notify = notify
    if open_gui:
        launch_gui()
    eng._run()


def signal_running_instance():
    """Je-li už spuštěná jiná instance, řekne jí, ať ukáže okno. Vrací True, pokud běží."""
    hwnd = u32.FindWindowW(WINDOW_CLASS, None)
    if hwnd:
        u32.PostMessageW(hwnd, WM_APP_TRAY, 0, WM_LBUTTONUP)
        return True
    return False
