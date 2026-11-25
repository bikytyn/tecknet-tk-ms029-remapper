"""Čitelné názvy myší pro výběr zařízení (Správce zařízení přes CfgMgr32) a stabilní ID pro config.

Raw Input dává jen cestu typu \\\\?\\HID#VID_25A7&PID_FA61&MI_01&Col01#…  nebo u Bluetooth
\\\\?\\HID#{00001812-…}_Dev_VID&0225a7_PID&faa0_…  – název zařízení je o pár uzlů výš ve stromu zařízení.
"""
import ctypes
import re
from ctypes import wintypes as W

cm = ctypes.WinDLL("cfgmgr32")


class GUID(ctypes.Structure):
    _fields_ = [("a", W.DWORD), ("b", W.WORD), ("c", W.WORD), ("d", ctypes.c_ubyte * 8)]


class DEVPROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", W.ULONG)]


def _key(s, pid):
    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p("{" + s + "}"), ctypes.byref(g))
    return DEVPROPKEY(g, pid)


KEY_FRIENDLY = _key("a45c254e-df1c-4efd-8020-67d146a850e0", 14)
KEY_DESC = _key("a45c254e-df1c-4efd-8020-67d146a850e0", 2)
KEY_BUSDESC = _key("540b947e-8b40-45bc-a8a2-6a0b894cbda2", 4)  # název z popisu výrobce (USB)

cm.CM_Locate_DevNodeW.argtypes = [ctypes.POINTER(W.DWORD), W.LPCWSTR, W.ULONG]
cm.CM_Get_Parent.argtypes = [ctypes.POINTER(W.DWORD), W.DWORD, W.ULONG]
cm.CM_Get_Device_IDW.argtypes = [W.DWORD, W.LPWSTR, W.ULONG, W.ULONG]
cm.CM_Get_DevNode_PropertyW.argtypes = [W.DWORD, ctypes.POINTER(DEVPROPKEY), ctypes.POINTER(W.ULONG),
                                        ctypes.c_void_p, ctypes.POINTER(W.ULONG), W.ULONG]

KNOWN = {"vid_25a7&pid_fa61": "Tecknet TK-MS029", "vid&0225a7_pid&faa0": "Tecknet TK-MS029"}


def device_id(path):
    """Stabilní identifikátor do configu: 'VID_25A7&PID_FA61' (USB) nebo 'VID&0225A7_PID&FAA0' (Bluetooth)."""
    m = re.search(r"VID_[0-9A-F]{4}&PID_[0-9A-F]{4}", path, re.I) or \
        re.search(r"VID&[0-9A-F]{6}_PID&[0-9A-F]{4}", path, re.I)
    if m:
        return m.group(0).upper()
    m = re.search(r"HID#([^#]+)#", path, re.I)  # vestavěná zařízení (touchpad ELAN…)
    return m.group(1).upper().split("&COL")[0] if m else path


def is_bluetooth(path):
    return "{00001812-0000-1000-8000-00805f9b34fb}" in path.lower()


def connection(path):
    """'bt' | 'usb' | 'builtin'"""
    if is_bluetooth(path):
        return "bt"
    return "usb" if re.search(r"VID_[0-9A-F]{4}", path, re.I) else "builtin"


def _prop(dev, key):
    t, size = W.ULONG(), W.ULONG(0)
    cm.CM_Get_DevNode_PropertyW(dev, ctypes.byref(key), ctypes.byref(t), None, ctypes.byref(size), 0)
    if not size.value:
        return None
    buf = ctypes.create_string_buffer(size.value)
    if cm.CM_Get_DevNode_PropertyW(dev, ctypes.byref(key), ctypes.byref(t), buf, ctypes.byref(size), 0) != 0:
        return None
    return ctypes.wstring_at(buf).strip() or None


def _instance_id(dev):
    buf = ctypes.create_unicode_buffer(512)
    return buf.value if cm.CM_Get_Device_IDW(dev, buf, 512, 0) == 0 else ""


def friendly_name(path):
    """Název myši jako ve Správci zařízení / nastavení Bluetooth (např. „TK-MS029 BT1“)."""
    known = KNOWN.get(device_id(path).lower())
    inst = path[4:] if path.startswith("\\\\?\\") else path
    inst = "\\".join(inst.split("#")[:3])  # HID\…\… (bez GUID rozhraní)
    dev = W.DWORD()
    if cm.CM_Locate_DevNodeW(ctypes.byref(dev), inst, 0) != 0:
        return known
    cur, bus_desc = dev.value, None
    for _ in range(5):  # nahoru stromem: HID -> USB rozhraní -> USB zařízení / BTHLEDEVICE -> BTHLE\Dev_…
        iid = _instance_id(cur).upper()
        if iid.startswith(("BTHLE\\DEV_", "BTHENUM\\")):
            name = _prop(cur, KEY_FRIENDLY) or _prop(cur, KEY_DESC)
            if name:
                return name
        bus_desc = bus_desc or _prop(cur, KEY_BUSDESC)
        parent = W.DWORD()
        if cm.CM_Get_Parent(ctypes.byref(parent), cur, 0) != 0:
            break
        cur = parent.value
    if known and bus_desc:
        return f"{known} ({bus_desc})"
    return known or bus_desc or device_id(path)
