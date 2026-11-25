"""Texty aplikace – angličtina (výchozí) a čeština."""
import os

LANG = "en"
LANGS = [("en", "EN"), ("cs", "CS")]


def set_lang(lang):
    global LANG
    LANG = lang if lang in ("en", "cs") else "en"


S = {
    # hlavička a obecné
    "tab_buttons": ("Mouse", "Myš"),
    "tab_windows": ("More settings", "Další nastavení"),
    # ovladače s nastavením Windows (klik na myš na hlavní stránce)
    "ctl_wheel": ("Scroll wheel", "Kolečko"),
    "ctl_buttons": ("Left & right button", "Levé a pravé tlačítko"),
    "ctl_dpi": ("DPI & pointer", "DPI a ukazatel"),
    "settings_for": ("SETTINGS", "NASTAVENÍ"),
    "sum_lines": ("{n} lines per notch", "řádků na cvaknutí: {n}"),
    "sum_page": ("one screen per notch", "po celých stránkách"),
    "sum_hover": ("inactive windows too", "i neaktivní okna"),
    "sum_swapped": ("swapped", "prohozeno"),
    "sum_dbl": ("double-click {n} ms", "dvojklik {n} ms"),
    "sum_speed": ("speed {n}", "rychlost {n}"),
    "mid_note": ("Pressing the wheel is the middle button – unchanged.",
                 "Stisk kolečka = prostřední tlačítko (beze změny)."),
    "test_hint": ("Tip: click, right-click or scroll over the picture – the mouse lights up.",
                  "Tip: klikni, klikni pravým nebo otoč kolečkem nad obrázkem – myš se rozsvítí."),
    "t_left": ("Left button", "Levé tlačítko"),
    "t_right": ("Right button", "Pravé tlačítko"),
    "t_middle": ("Wheel click", "Stisk kolečka"),
    "t_up": ("Wheel ▲", "Kolečko ▲"),
    "t_down": ("Wheel ▼", "Kolečko ▼"),
    "t_hup": ("Thumb wheel ▲", "Palcové kolečko ▲"),
    "t_hdown": ("Thumb wheel ▼", "Palcové kolečko ▼"),
    "open_win":("Open in Windows settings ↗", "Otevřít v nastavení Windows ↗"),
    "exact_link": ("Exact measurement with a ruler →", "Přesné měření pravítkem →"),
    "win_intro2": ("Pointer speed and appearance and a few extras. The wheel and buttons are set by clicking "
                   "the mouse on the Mouse tab. These are Windows settings – they apply to all mice.",
                   "Rychlost a vzhled kurzoru a pár drobností. Kolečko a tlačítka nastavíš kliknutím na myš na "
                   "záložce Myš. Jde o nastavení Windows – platí pro všechny myši."),
    "sw_enabled": ("Remapping on", "Přemapování zapnuto"),
    "sw_autostart": ("Start with Windows", "Spustit po startu Windows"),
    "dev_ok": ("● mouse connected", "● myš připojena"),
    "dev_missing": ("○ mouse not found", "○ myš nenalezena"),
    "conn_bt": ("Bluetooth", "Bluetooth"),
    "conn_usb": ("USB", "USB"),
    "conn_builtin": ("built-in", "vestavěné"),
    # výběr myši
    "dev_change": ("change", "změnit"),
    "dev_choose": ("choose a mouse", "vybrat myš"),
    "dev_title": ("Which mouse to remap?", "Kterou myš přemapovat?"),
    "dev_sub": ("Only the selected mice are remapped – others keep working as usual. Any mouse with standard "
                "side buttons (Back / Forward) or a horizontal wheel works.",
                "Přemapují se jen vybrané myši – ostatní fungují jako dřív. Funguje každá myš se standardními "
                "bočními tlačítky (Zpět / Vpřed) nebo vodorovným kolečkem."),
    "dev_not_connected": ("not connected", "není připojena"),
    "dev_detect": ("Detect by pressing a button", "Rozpoznat stisknutím"),
    "dev_detect_wait": ("Press a side button or roll the thumb wheel on the mouse you want to remap…",
                        "Zmáčkni boční tlačítko nebo otoč palcovým kolečkem na myši, kterou chceš přemapovat…"),
    "dev_detected": ("Detected: {name}", "Rozpoznáno: {name}"),
    "dev_none": ("Select at least one mouse.", "Vyber aspoň jednu myš."),
    "dev_saved": ("Mouse selection saved", "Výběr myši uložen"),
    "sec_device": ("Mouse", "Myš"),
    "dev_row": ("Remapped mouse", "Přemapovaná myš"),
    "dev_row_sub": ("Which mouse the side buttons and thumb wheel are remapped on.",
                    "Na které myši se přemapovávají boční tlačítka a palcové kolečko."),
    "dev_btn": ("Choose…", "Vybrat…"),
    "last_action": ("Last action", "Poslední akce"),
    "last_hint": ("press a side button or roll the thumb wheel", "zmáčkni boční tlačítko nebo otoč palcovým kolečkem"),
    "apps": ("APPLICATIONS", "APLIKACE"),
    "add_app": ("+  Add application", "+  Přidat aplikaci"),
    "all_apps": ("All applications", "Všechny aplikace"),
    "default_profile": ("default profile", "výchozí profil"),
    "actions_for": ("ACTION FOR", "AKCE PRO"),
    "search": ("Search actions…", "Hledat akci…"),
    "remove_profile": ("Remove profile", "Odebrat profil"),
    "global_sub": ("Default settings – used everywhere an application has no profile of its own.",
                   "Výchozí nastavení – platí všude, kde aplikace nemá vlastní profil."),
    "app_sub": ("Applies while {exe} is in the foreground. Unchanged controls follow the default profile.",
                "Platí, když je {exe} v popředí. Neupravené ovladače se řídí výchozím profilem."),
    "presets": ("Presets", "Šablony"),
    "tpl_browser": ("Browser", "Prohlížeč"),
    "tpl_player": ("Media player", "Přehrávač"),
    "tpl_original": ("Original functions", "Původní funkce"),
    "thumb_wheel": ("Thumb wheel", "Palcové kolečko"),
    "ctl_x1": ("Back button", "Boční tlačítko Zpět"),
    "ctl_x2": ("Forward button", "Boční tlačítko Vpřed"),
    # palcové kolečko: otočení nahoru posílá „doprava“ (+120), dolů „doleva“ (−120)
    "ctl_hleft": ("Thumb wheel down", "Palcové kolečko dolů"),
    "ctl_hright": ("Thumb wheel up", "Palcové kolečko nahoru"),
    "inherited": ("default", "výchozí"),
    "nothing_found": ("Nothing found.", "Nic nenalezeno."),
    "sec_profile": ("Profile", "Profil"),
    "inherit": ("Same as All applications", "Jako ve Všech aplikacích"),
    "sec_custom": ("Custom", "Vlastní"),
    "custom_keys": ("Custom keyboard shortcut…", "Vlastní klávesová zkratka…"),
    "custom_run": ("Run a program or file…", "Spustit program nebo soubor…"),
    "editor_keys": ("Keyboard shortcut", "Klávesová zkratka"),
    "record": ("Record", "Nahrát"),
    "save": ("Save", "Uložit"),
    "keys_hint": ("Click Record and press the shortcut, or type it: ctrl+shift+t, alt+f4, f5, win+e",
                  "Klikni na Nahrát a stiskni zkratku, nebo ji napiš: ctrl+shift+t, alt+f4, f5, win+e"),
    "press_shortcut": ("press the shortcut…", "stiskni zkratku…"),
    "key_unknown": ("This key can't be recorded – type it instead.", "Tuhle klávesu neumím nahrát – napiš ji ručně."),
    "bad_shortcut": ("Shortcut can't be used: {err}", "Zkratku nelze použít: {err}"),
    "editor_run": ("Program or file", "Program nebo soubor"),
    "change": ("Change…", "Změnit…"),
    "pick_file": ("Choose a program or file", "Vyber program nebo soubor"),
    "saved": ("Saved", "Uloženo"),
    "tpl_applied": ("Preset “{name}” applied", "Použita šablona {name}"),
    "profile_removed": ("Profile {exe} removed", "Profil {exe} odebrán"),
    "player_tpl": ("Media player preset applied (thumb wheel = volume, buttons = tracks)",
                   "Nastavena šablona Přehrávač (kolečko = hlasitost, tlačítka = skladby)"),
    "enabled_on": ("Remapping on", "Přemapování zapnuto"),
    "enabled_off": ("Remapping paused", "Přemapování pozastaveno"),
    "auto_on": ("Will start with Windows", "Spustí se po startu Windows"),
    "auto_off": ("Autostart off", "Autostart vypnut"),
    "auto_err": ("Couldn't set autostart: {err}", "Autostart se nepodařilo nastavit: {err}"),
    "add_title": ("Add application", "Přidat aplikaci"),
    "add_sub": ("Pick a running application, or find another program with Browse.",
                "Vyber spuštěnou aplikaci, nebo najdi jiný program přes Procházet."),
    "browse": ("Browse…", "Procházet…"),
    "close": ("Close", "Zavřít"),
    "player_badge": ("media player", "přehrávač"),
    "programs": ("Programs", "Programy"),
    "pick_program": ("Choose a program", "Vyber program"),
    "lang_restart": ("Switching language…", "Přepínám jazyk…"),
    # myš ve Windows
    "win_title": ("More settings", "Další nastavení"),
    "win_intro": ("System settings – they apply to all mice and touchpads and take effect immediately.",
                  "Systémové nastavení – platí pro všechny myši i touchpad a změna se projeví hned."),
    "sec_dpi": ("Sensitivity (DPI)", "Citlivost (DPI)"),
    "dpi_sub": ("The TK-MS029 has 6 levels (800–4800 DPI), switched with the button below the scroll wheel. The mouse "
                "doesn't report them, but one short move identifies the level – the result snaps to the nearest "
                "level, so moving roughly the chosen distance (±10 %) is enough.",
                "TK-MS029 má 6 stupňů (800–4800 DPI), přepínají se tlačítkem pod kolečkem. Myš je počítači nehlásí, "
                "ale stupeň pozná jeden krátký posun – výsledek se přichytí k nejbližšímu stupni, takže stačí posunout "
                "myš zhruba o zvolenou vzdálenost (±10 %)."),
    "dpi_sub2": ("The TK-MS029 has 6 levels (800–4800 DPI) and doesn't report them to the PC. Tell the app your "
                 "current level once – it then learns how you move and notices by itself when you switch with the "
                 "DPI button (after a few dozen strokes of normal use).",
                 "TK-MS029 má 6 stupňů (800–4800 DPI) a počítači je nehlásí. Jednou programu řekni aktuální stupeň – "
                 "pak se naučí, jak hýbeš rukou, a sám pozná, když tlačítkem DPI přepneš (po pár desítkách tahů "
                 "běžného používání)."),
    "dpi_now": ("Current level", "Aktuální stupeň"),
    "dpi_track_none": ("Click your current level to start watching (after switching the mouse on it's 1600).",
                       "Klikni na aktuální stupeň a sledování začne (po zapnutí myši je to 1600)."),
    "dpi_track_learning": ("Learning your movements… {n}/25 strokes", "Učím se tvoje pohyby… {n}/25 tahů"),
    "dpi_track_ok": ("Watching automatically · confidence {c} % · learned from {n} strokes. Wrong? Click the right level.",
                     "Sleduji automaticky · jistota {c} % · naučeno z {n} tahů. Nesedí? Klikni na správný stupeň."),
    "dpi_changed": ("DPI switched to {dpi}", "DPI přepnuto na {dpi}"),
    "vol_step": ("Volume step", "Krok hlasitosti"),
    "vol_step_hint": ("Per notch of the thumb wheel or per button press. Windows' own volume keys use 2 %. "
                      "Applies to all volume actions.",
                      "Na jeden dílek palcového kolečka nebo stisk tlačítka. Klávesy hlasitosti ve Windows mají 2 %. "
                      "Platí pro všechny akce s hlasitostí."),
    "vol_step_saved": ("Volume step {n} %", "Krok hlasitosti {n} %"),
    "vol_step_sub": ("step {n} %", "krok {n} %"),
    "dpi_exact":("Exact measurement (optional)", "Přesné měření (nepovinné)"),
    "dpi_distance": ("Distance", "Vzdálenost"),
    "dpi_d_ruler": ("10 cm (ruler)", "10 cm (pravítko)"),
    "dpi_d_card": ("8.56 cm (payment card)", "8,56 cm (platební karta)"),
    "dpi_d_a4": ("21 cm (A4 width)", "21 cm (šířka A4)"),
    "dpi_measured": ("measured ≈ {dpi} DPI · {counts} counts over {d}", "naměřeno ≈ {dpi} DPI · {counts} bodů na {d}"),
    "dpi_sure": ("Clear match.", "Jednoznačný zásah."),
    "dpi_unsure": ("Between two levels – measure again, ideally over a longer distance.",
                   "Mezi dvěma stupni – změř znovu, nejlépe na delší vzdálenost."),
    "dpi_saved": ("last measured {when}", "naposledy změřeno {when}"),
    "dpi_measure": ("Measure DPI", "Změřit DPI"),
    "dpi_step1": ("Put the mouse at the start of the distance and press Space.",
                  "Polož myš na začátek vzdálenosti a stiskni mezerník."),
    "dpi_step2": ("Now move the mouse exactly {d} and press Space again.",
                  "Teď posuň myš přesně o {d} a znovu stiskni mezerník."),
    "dpi_detail": ("{counts} sensor counts over {d}", "{counts} bodů senzoru na {d}"),
    "dpi_nomove": ("No movement from the Tecknet was detected – try again.",
                   "Z Tecknetu nepřišel žádný pohyb – zkus to znovu."),
    "dpi_outside": ("Measured {dpi} DPI – outside the mouse's range, so the move probably wasn't the full distance. "
                    "Try again.",
                    "Naměřeno {dpi} DPI – to je mimo rozsah myši, nejspíš posun nebyl o celou vzdálenost. Zkus to znovu."),
    "dpi_again":("Measure again", "Měřit znovu"),
    "cancel": ("Cancel", "Zrušit"),
    "sec_pointer": ("Pointer", "Ukazatel"),
    "speed": ("Pointer speed", "Rychlost ukazatele"),
    "speed_sub": ("Default is 10.", "Výchozí je 10."),
    "accel": ("Enhance pointer precision", "Zvýšit přesnost ukazatele"),
    "accel_sub": ("Acceleration – fast movements move the pointer further. Often turned off for games and graphics.",
                  "Akcelerace – při rychlém pohybu ujede kurzor dál. Pro hry a grafiku se často vypíná."),
    "sec_scroll": ("Scrolling", "Posouvání kolečkem"),
    "lines": ("Lines per wheel notch", "Počet řádků na jedno cvaknutí"),
    "lines_sub": ("Default is 3.", "Výchozí jsou 3 řádky."),
    "page": ("Scroll one screen at a time", "Posouvat po celých stránkách"),
    "page_sub": ("One notch scrolls a whole screen.", "Jedno cvaknutí posune o celou obrazovku."),
    "hover": ("Scroll inactive windows when hovering", "Posouvat neaktivní okna pod kurzorem"),
    "hover_sub": ("The wheel scrolls the window under the pointer even if it isn't active.",
                  "Kolečko posouvá okno, nad kterým je myš, i když není aktivní."),
    "chars": ("Characters per horizontal scroll", "Znaků při vodorovném posunu"),
    "chars_sub": ("Only where the thumb wheel keeps its default function (e.g. Excel).",
                  "Uplatní se jen tam, kde má palcové kolečko výchozí funkci (např. Excel)."),
    "sec_btn": ("Buttons", "Tlačítka"),
    "swap": ("Swap left and right buttons", "Prohodit levé a pravé tlačítko"),
    "swap_sub": ("For left-handers. The switch reacts to either button.",
                 "Pro leváky. Přepínač jde vrátit kterýmkoli tlačítkem."),
    "dbl": ("Double-click speed", "Rychlost dvojkliku"),
    "dbl_sub": ("Shorter = faster double-click. Default is 500 ms.", "Kratší čas = rychlejší dvojklik. Výchozí je 500 ms."),
    "dbl_test": ("Double-click", "Dvojklik sem"),
    "dbl_ok": ("Works!", "Funguje!"),
    "sec_cursor": ("Pointer appearance", "Kurzor"),
    "csize": ("Pointer size", "Velikost kurzoru"),
    "csize_sub": ("1 = default size (as in Settings › Accessibility › Mouse pointer).",
                  "1 = výchozí velikost (jako v Nastavení › Usnadnění › Ukazatel myši)."),
    "schemes": ("Pointer scheme", "Schéma kurzorů"),
    "schemes_sub": ("Changes all pointers at once. Click a scheme.", "Vzhled všech kurzorů najednou. Klikni na schéma."),
    "scheme_default": ("Windows default", "Výchozí Windows"),
    "install_scheme": ("Install from file…", "Nainstalovat ze souboru…"),
    "find_schemes": ("Find more pointer schemes ↗", "Najít další sady kurzorů ↗"),
    "install_types": ("Pointer packs", "Sady kurzorů"),
    "installed": ("Scheme “{name}” installed and applied", "Schéma {name} nainstalováno a použito"),
    "install_err": ("Couldn't install: {err}", "Nepodařilo se nainstalovat: {err}"),
    "delete_scheme_q": ("Delete pointer scheme “{name}”?", "Smazat schéma kurzorů {name}?"),
    "delete": ("Delete", "Smazat"),
    "scheme_applied": ("Pointer scheme applied", "Schéma kurzorů použito"),
    "scheme_hint": ("Packs usually come as a .zip with install.inf – pick the .zip (no admin rights needed).",
                    "Sady bývají .zip s install.inf – stačí vybrat ten .zip (nejsou potřeba práva správce)."),
    "sec_more": ("More", "Další"),
    "sonar": ("Show pointer location with Ctrl", "Ukázat polohu kurzoru klávesou Ctrl"),
    "sonar_sub": ("Pressing Ctrl shows a circle around the pointer.", "Po stisku Ctrl se kolem kurzoru zobrazí kruh."),
    "vanish": ("Hide pointer while typing", "Skrýt kurzor při psaní"),
    "snap": ("Snap pointer to the default button", "Skočit kurzorem na výchozí tlačítko"),
    "snap_sub": ("In new dialogs the pointer jumps to OK / Yes.", "V nových dialozích se kurzor přesune na OK / Ano."),
    "trails": ("Pointer trails", "Stopa kurzoru"),
    "trails_sub": ("A short trail follows the pointer so it's easier to spot.",
                   "Za kurzorem zůstává krátká stopa – lépe ho uvidíš."),
    "open_settings": ("Windows mouse settings", "Nastavení myši ve Windows"),
    "open_classic": ("Classic mouse properties", "Klasické vlastnosti myši"),
    "reset": ("Restore defaults", "Obnovit výchozí hodnoty"),
    "reset_q": ("Reset all Windows mouse settings to their defaults?",
                "Vrátit všechna nastavení myši ve Windows na výchozí hodnoty?"),
    "reset_done": ("Defaults restored", "Výchozí hodnoty obnoveny"),
    "reset_partial": ("Restored, {n} items failed", "Obnoveno, {n} položek se nepodařilo"),
    "saved_win": ("Saved to Windows", "Uloženo do Windows"),
    "failed": ("Failed: {err}", "Nepodařilo se: {err}"),
    # tray
    "tray_settings": ("Settings…", "Nastavení…"),
    "tray_enabled": ("Remapping on", "Přemapování zapnuto"),
    "tray_quit": ("Quit", "Ukončit"),
    "tray_paused": (" (paused)", " (pozastaveno)"),
}


def t(key, **kw):
    en, cs = S.get(key, (key, key))
    s = cs if LANG == "cs" else en
    return s.format(**kw) if kw else s


# ---------------------------------------------------------------- akce

A = {
    "default": (("Default function", "unchanged"), ("Výchozí funkce", "beze změny")),
    "none": (("Disabled", "do nothing"), ("Vypnuto", "nedělat nic")),
    "keys:ctrl+tab": (("Next tab", "Ctrl+Tab"), ("Další tab", "Ctrl+Tab")),
    "keys:ctrl+shift+tab": (("Previous tab", "Ctrl+Shift+Tab"), ("Předchozí tab", "Ctrl+Shift+Tab")),
    "keys:ctrl+w": (("Close tab", "Ctrl+W"), ("Zavřít tab", "Ctrl+W")),
    "keys:ctrl+shift+t": (("Reopen closed tab", "Ctrl+Shift+T"), ("Obnovit zavřený tab", "Ctrl+Shift+T")),
    "keys:alt+left": (("History back", "Alt+←"), ("Zpět v historii", "Alt+←")),
    "keys:alt+right": (("History forward", "Alt+→"), ("Vpřed v historii", "Alt+→")),
    "keys:volume_up": (("Volume up", ""), ("Hlasitost +", "")),
    "keys:volume_down": (("Volume down", ""), ("Hlasitost −", "")),
    "keys:volume_mute": (("Mute / unmute", ""), ("Ztlumit / zrušit ztlumení", "")),
    "keys:media_play_pause": (("Play / pause", ""), ("Přehrát / pozastavit", "")),
    "keys:media_next": (("Next track", ""), ("Další skladba", "")),
    "keys:media_prev": (("Previous track", ""), ("Předchozí skladba", "")),
    "keys:ctrl+c": (("Copy", "Ctrl+C"), ("Kopírovat", "Ctrl+C")),
    "keys:ctrl+x": (("Cut", "Ctrl+X"), ("Vyjmout", "Ctrl+X")),
    "keys:ctrl+v": (("Paste", "Ctrl+V"), ("Vložit", "Ctrl+V")),
    "keys:ctrl+z": (("Undo", "Ctrl+Z"), ("Zpět (undo)", "Ctrl+Z")),
    "keys:ctrl+y": (("Redo", "Ctrl+Y"), ("Znovu (redo)", "Ctrl+Y")),
    "keys:ctrl+num_plus": (("Zoom in", "Ctrl + +"), ("Přiblížit", "Ctrl + +")),
    "keys:ctrl+num_minus": (("Zoom out", "Ctrl + −"), ("Oddálit", "Ctrl + −")),
    "keys:ctrl+win+right": (("Next virtual desktop", "Ctrl+Win+→"), ("Další virtuální plocha", "Ctrl+Win+→")),
    "keys:ctrl+win+left": (("Previous virtual desktop", "Ctrl+Win+←"), ("Předchozí virtuální plocha", "Ctrl+Win+←")),
    "keys:win+tab": (("Task view", "Win+Tab"), ("Zobrazení úloh", "Win+Tab")),
    "keys:win+d": (("Show desktop", "Win+D"), ("Zobrazit plochu", "Win+D")),
    "mouse:x1": (("Back", "mouse button 4"), ("Zpět", "tlačítko myši 4")),
    "mouse:x2": (("Forward", "mouse button 5"), ("Vpřed", "tlačítko myši 5")),
    "mouse:middle": (("Middle button", ""), ("Prostřední tlačítko", "")),
    "mouse:hleft": (("Scroll left", ""), ("Vodorovný posun doleva", "")),
    "mouse:hright": (("Scroll right", ""), ("Vodorovný posun doprava", "")),
}

CATEGORIES = [
    (("Basic", "Základní"), ["default", "none"]),
    (("Browser & tabs", "Prohlížeč a taby"), ["keys:ctrl+tab", "keys:ctrl+shift+tab", "keys:ctrl+w",
                                              "keys:ctrl+shift+t", "keys:alt+left", "keys:alt+right"]),
    (("Volume & media", "Hlasitost a média"), ["keys:volume_up", "keys:volume_down", "keys:volume_mute",
                                               "keys:media_play_pause", "keys:media_next", "keys:media_prev"]),
    (("Editing", "Úpravy"), ["keys:ctrl+c", "keys:ctrl+x", "keys:ctrl+v", "keys:ctrl+z", "keys:ctrl+y"]),
    (("View", "Zobrazení"), ["keys:ctrl+num_plus", "keys:ctrl+num_minus"]),
    (("Windows & desktops", "Okna a plochy"), ["keys:ctrl+win+right", "keys:ctrl+win+left", "keys:win+tab",
                                               "keys:win+d"]),
    (("Mouse buttons", "Tlačítka myši"), ["mouse:x1", "mouse:x2", "mouse:middle", "mouse:hleft", "mouse:hright"]),
]

TEMPLATES = [
    ("tpl_browser", {"x1": "keys:ctrl+shift+tab", "x2": "keys:ctrl+tab",
                     "hleft": "keys:volume_down", "hright": "keys:volume_up"}),
    ("tpl_player", {"x1": "keys:media_prev", "x2": "keys:media_next",
                    "hleft": "keys:volume_down", "hright": "keys:volume_up"}),
    ("tpl_original", {"x1": "default", "x2": "default", "hleft": "default", "hright": "default"}),
]


def action(a):
    """-> (hlavní text, vedlejší text)"""
    if a in A:
        return A[a][1 if LANG == "cs" else 0]
    if a == "inherit":
        return t("inherit"), ""
    if a.startswith("keys:"):
        return ("Zkratka" if LANG == "cs" else "Shortcut"), a[5:]
    if a.startswith("run:"):
        return ("Spustit" if LANG == "cs" else "Run"), os.path.basename(a[4:])
    return a, ""


def action_short(a):
    main, sub = action(a)
    if a.startswith(("keys:", "run:")) and a not in A:
        return f"{main} {sub}"
    return main


def category(names):
    return names[1] if LANG == "cs" else names[0]


def control(c):
    return t("ctl_" + c)
