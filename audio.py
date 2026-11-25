"""Hlasitost systému přes Core Audio (IAudioEndpointVolume) – čistě ctypes, bez knihoven.

Klávesy hlasitosti mění hlasitost vždy o 2 %. Pro jiný krok: pošle se jedna klávesa (aby Windows
ukázaly bublinu s hlasitostí), počká se, až ji systém zpracuje, a pak se nastaví přesná hodnota.
"""
import ctypes
import queue
import threading
import time
from ctypes import wintypes as W

ole32 = ctypes.WinDLL("ole32")
HRESULT = ctypes.c_long


class GUID(ctypes.Structure):
    _fields_ = [("a", W.DWORD), ("b", W.WORD), ("c", W.WORD), ("d", ctypes.c_ubyte * 8)]

    def __init__(self, s):
        super().__init__()
        ole32.CLSIDFromString(ctypes.c_wchar_p("{" + s + "}"), ctypes.byref(self))


CLSID_MMDeviceEnumerator = GUID("BCDE0395-E52F-467C-8E3D-C4579291692E")
IID_IMMDeviceEnumerator = GUID("A95664D2-9614-4F35-A746-DE8DB63617E6")
IID_IAudioEndpointVolume = GUID("5CDF2C82-841E-4546-9722-0CF74078229A")
CLSCTX_ALL = 23


def _call(obj, index, argtypes, *args):
    """Volání metody COM rozhraní přes vtable (index včetně 3 metod IUnknown)."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, *argtypes)(vtbl[index])
    hr = fn(obj, *args)
    if hr < 0:
        raise OSError(f"COM chyba 0x{hr & 0xFFFFFFFF:08X}")
    return hr


def _release(obj):
    if obj:
        vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])(obj)


class EndpointVolume:
    """Hlasitost výchozího výstupního zařízení. Vytvářet a používat v jednom vlákně."""

    def __init__(self):
        ole32.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
        self.enum = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(CLSID_MMDeviceEnumerator), None, CLSCTX_ALL,
                                    ctypes.byref(IID_IMMDeviceEnumerator), ctypes.byref(self.enum))
        if hr < 0:
            raise OSError(f"MMDeviceEnumerator 0x{hr & 0xFFFFFFFF:08X}")

    def _endpoint(self):
        dev = ctypes.c_void_p()
        _call(self.enum, 4, [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)],
              0, 1, ctypes.byref(dev))  # eRender, eMultimedia
        vol = ctypes.c_void_p()
        try:
            _call(dev, 3, [ctypes.POINTER(GUID), W.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
                  ctypes.byref(IID_IAudioEndpointVolume), CLSCTX_ALL, None, ctypes.byref(vol))
        finally:
            _release(dev)
        return vol

    def get(self):
        vol = self._endpoint()
        try:
            v = ctypes.c_float()
            _call(vol, 9, [ctypes.POINTER(ctypes.c_float)], ctypes.byref(v))
            return v.value
        finally:
            _release(vol)

    def set(self, level):
        vol = self._endpoint()
        try:
            _call(vol, 7, [ctypes.c_float, ctypes.c_void_p], ctypes.c_float(max(0.0, min(1.0, level))), None)
        finally:
            _release(vol)


class VolumeStepper:
    """Fronta kroků hlasitosti zpracovávaná ve vlastním vlákně (jádro se nezdrží)."""

    def __init__(self, press_key):
        self.press_key = press_key  # funkce(up: bool) – pošle klávesu hlasitosti (kvůli bublině)
        self.q = queue.Queue()
        threading.Thread(target=self._run, name="volume", daemon=True).start()

    def step(self, up, percent):
        self.q.put((up, percent))

    def _run(self):
        try:
            ev = EndpointVolume()
        except OSError:
            ev = None
        while True:
            up, pct = self.q.get()
            if ev is None or pct == 2:
                for _ in range(max(1, round(pct / 2))):
                    self.press_key(up)
                continue
            try:
                before = ev.get()
                target = round(before * 100 + (pct if up else -pct)) / 100
                self.press_key(up)  # bublina s hlasitostí
                t0 = time.perf_counter()
                while time.perf_counter() - t0 < 0.3 and abs(ev.get() - before) < 0.001:
                    time.sleep(0.01)
                ev.set(target)
            except OSError:
                for _ in range(max(1, round(pct / 2))):
                    self.press_key(up)
