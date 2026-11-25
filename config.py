"""Konfigurace, katalog akcí a generování ikony."""
import copy
import json
import os
import struct
import math

APP_NAME = "TecknetRemap"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CFG_PATH = os.path.join(CFG_DIR, "config.json")
ICON_PATH = os.path.join(CFG_DIR, "icon.ico")
LOG_PATH = os.path.join(CFG_DIR, "remap.log")

GLOBAL = "*"  # profil „Všechny aplikace“

CONTROLS = [
    ("x1", "Boční tlačítko Zpět"),
    ("x2", "Boční tlačítko Vpřed"),
    ("hleft", "Horizontální kolečko doleva"),
    ("hright", "Horizontální kolečko doprava"),
]

DEFAULT_CFG = {
    "version": 1,
    "enabled": True,
    # podřetězec názvu HID zařízení (Raw Input), které se přemapovává
    # podřetězce názvu HID zařízení (Raw Input), která se přemapovávají:
    # USB přijímač a Bluetooth (BLE HID: „VID&02xxxx_PID&yyyy“)
    "device_match": ["VID_25A7&PID_FA61", "VID&0225A7_PID&FAA0"],
    "debug": False,
    "profiles": {
        GLOBAL: {
            "x1": "default",
            "x2": "default",
            "hleft": "keys:ctrl+shift+tab",
            "hright": "keys:ctrl+tab",
        }
    },
}

INHERIT = ("inherit", "↳ Jako ve „Všech aplikacích“")
CUSTOM_KEYS_LABEL = "Vlastní klávesová zkratka…"
RUN_LABEL = "Spustit program / soubor…"

PRESETS = [
    ("default", "Výchozí funkce (beze změny)"),
    ("none", "Vypnuto (nedělat nic)"),
    ("mouse:x1", "Zpět (tlačítko myši 4)"),
    ("mouse:x2", "Vpřed (tlačítko myši 5)"),
    ("mouse:middle", "Prostřední tlačítko"),
    ("mouse:hleft", "Vodorovný posun doleva"),
    ("mouse:hright", "Vodorovný posun doprava"),
    ("keys:ctrl+tab", "Další tab (Ctrl+Tab)"),
    ("keys:ctrl+shift+tab", "Předchozí tab (Ctrl+Shift+Tab)"),
    ("keys:ctrl+w", "Zavřít tab (Ctrl+W)"),
    ("keys:ctrl+shift+t", "Obnovit zavřený tab (Ctrl+Shift+T)"),
    ("keys:alt+left", "Zpět v historii (Alt+←)"),
    ("keys:alt+right", "Vpřed v historii (Alt+→)"),
    ("keys:ctrl+c", "Kopírovat (Ctrl+C)"),
    ("keys:ctrl+x", "Vyjmout (Ctrl+X)"),
    ("keys:ctrl+v", "Vložit (Ctrl+V)"),
    ("keys:ctrl+z", "Undo (Ctrl+Z)"),
    ("keys:ctrl+y", "Redo (Ctrl+Y)"),
    ("keys:ctrl+num_plus", "Přiblížit (Ctrl + +)"),
    ("keys:ctrl+num_minus", "Oddálit (Ctrl + −)"),
    ("keys:volume_up", "Hlasitost +"),
    ("keys:volume_down", "Hlasitost −"),
    ("keys:volume_mute", "Ztlumit / zrušit ztlumení"),
    ("keys:media_play_pause", "Přehrát / pozastavit"),
    ("keys:media_next", "Další skladba"),
    ("keys:media_prev", "Předchozí skladba"),
    ("keys:ctrl+win+right", "Další virtuální plocha"),
    ("keys:ctrl+win+left", "Předchozí virtuální plocha"),
    ("keys:win+tab", "Zobrazení úloh (Win+Tab)"),
    ("keys:win+d", "Zobrazit plochu (Win+D)"),
]
PRESET_LABEL = dict(PRESETS)


def action_label(action):
    if action in PRESET_LABEL:
        return PRESET_LABEL[action]
    if action == INHERIT[0]:
        return INHERIT[1]
    if action.startswith("keys:"):
        return "Zkratka " + action[5:]
    if action.startswith("run:"):
        return "Spustit " + os.path.basename(action[4:])
    return action


def load_config():
    cfg = copy.deepcopy(DEFAULT_CFG)
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            user = json.load(f)
        for k, v in user.items():
            if k != "profiles":
                cfg[k] = v
        if cfg.get("device_match") == "VID_25A7&PID_FA61":  # starý výchozí (jen USB) -> i Bluetooth
            cfg["device_match"] = list(DEFAULT_CFG["device_match"])
        profs = user.get("profiles") or {}
        for exe, p in profs.items():
            cfg["profiles"].setdefault(exe, {}).update(p)
    except FileNotFoundError:
        pass
    except Exception as e:  # poškozený soubor – nepřepisovat, jen záloha
        try:
            os.replace(CFG_PATH, CFG_PATH + ".broken")
        except OSError:
            pass
        print("config load error:", e)
    return cfg


def save_config(cfg):
    os.makedirs(CFG_DIR, exist_ok=True)
    tmp = CFG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CFG_PATH)


def resolve(cfg, exe, control):
    profs = cfg["profiles"]
    a = profs.get(exe, {}).get(control, "inherit") if exe else "inherit"
    if a == "inherit":
        a = profs.get(GLOBAL, {}).get(control, "default")
    return a


# ---------------------------------------------------------------- ikona (.ico bez knihoven)

def _sd_round_rect(px, py, cx, cy, hw, hh, r):
    qx, qy = abs(px - cx) - (hw - r), abs(py - cy) - (hh - r)
    ox, oy = max(qx, 0.0), max(qy, 0.0)
    return math.hypot(ox, oy) + min(max(qx, qy), 0.0) - r


def _render(size):
    s = size
    px = bytearray()
    body = (226, 125, 47)  # BGR -> modrá #2F7DE2
    for y in range(s - 1, -1, -1):  # BMP je zdola nahoru
        for x in range(s):
            fx, fy = x + 0.5, y + 0.5
            d = _sd_round_rect(fx, fy, s / 2, s / 2, s * 0.30, s * 0.45, s * 0.29)
            a = max(0.0, min(1.0, 0.5 - d))
            b, g, r = body
            # dělicí čáry tlačítek
            lw = max(1.0, s / 20)
            split_y = s * 0.42
            on_line = (abs(fx - s / 2) < lw / 2 and fy < split_y) or (abs(fy - split_y) < lw / 2)
            # kolečko
            wd = _sd_round_rect(fx, fy, s / 2, s * 0.27, s * 0.055, s * 0.10, s * 0.05)
            if wd < 0.5:
                k = max(0.0, min(1.0, 0.5 - wd))
                b, g, r = [int(c * (1 - k) + 255 * k) for c in (b, g, r)]
            elif on_line:
                b, g, r = 140, 70, 20
            px += bytes((b, g, r, int(a * 255)))
    mask = b"\x00" * (((s + 31) // 32) * 4 * s)
    hdr = struct.pack("<IiiHHIIiiII", 40, s, s * 2, 1, 32, 0, len(px) + len(mask), 0, 0, 0, 0)
    return hdr + bytes(px) + mask


def ensure_icon():
    asset = os.path.join(APP_DIR, "assets", "app.ico")
    if os.path.exists(asset):
        return asset
    if os.path.exists(ICON_PATH):
        return ICON_PATH
    os.makedirs(CFG_DIR, exist_ok=True)
    sizes = [16, 24, 32, 48, 64]
    imgs = [_render(s) for s in sizes]
    out = struct.pack("<HHH", 0, 1, len(sizes))
    off = 6 + 16 * len(sizes)
    for s, img in zip(sizes, imgs):
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(img), off)
        off += len(img)
    with open(ICON_PATH, "wb") as f:
        f.write(out + b"".join(imgs))
    return ICON_PATH
