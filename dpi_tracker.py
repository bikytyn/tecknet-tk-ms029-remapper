"""Pasivní sledování stupně DPI podle toho, jak uživatel běžně hýbe myší.

Princip: fyzicky podobné pohyby ruky dávají v bodech senzoru tím větší čísla, čím vyšší je DPI.
Program se jednou „ukotví“ (uživatel řekne aktuální stupeň), naučí se typické tahy v přepočtu na
fyzické jednotky (body / DPI) a pak porovnává poslední tahy s naučeným zvykem. Když se všechny
tahy najednou zvětší/zmenší o poměr odpovídající jinému stupni, stupeň se přepne.

Příznak tahu: f = ½·ln(délka tahu) + ½·ln(nejvyšší rychlost); obojí se škáluje s DPI, takže
f − ln(DPI) je „zvyk“ nezávislý na DPI.
"""
import math
import time
from collections import deque

LEVELS = [800, 1200, 1600, 2400, 3200, 4800]

STROKE_GAP = 0.08      # s bez pohybu = konec tahu
BIN = 0.032            # s – okno pro výpočet rychlosti
MIN_LEN = 30           # bodů – kratší tahy (chvění) se ignorují; pevně, aby nezáviselo na odhadu DPI
RECENT = 40            # počet posledních tahů pro rozhodování
LEARN_MIN = 25         # tahů, než začne rozhodovat
BASELINE_MAX = 400
Z_SWITCH = 2.5         # potřebná síla důkazu pro přepnutí
PERSIST = 8            # … a musí vydržet tolik tahů po sobě (méně planých poplachů)
UNLIKELY = 2.0         # přirážka k důkazu pro přechod, který by vyžadoval 4–5 stisků
AGREE = 0.07           # |ln(odhad/stupeň)| pod tímto = okno jasně odpovídá stupni → nejstarší tah se učí


def _median(xs):
    s = sorted(xs)
    n = len(s)
    return (s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])) if n else 0.0


class DpiTracker:
    def __init__(self, state=None):
        state = state or {}
        self.level = state.get("level")
        self.baseline = deque((float(x) for x in state.get("baseline", [])), maxlen=BASELINE_MAX)
        self.recent = deque(maxlen=RECENT)
        self.confidence = 0.0
        self.estimate = None
        self.strokes = 0
        self._streak = 0
        self._cand = None
        self._reset_stroke()
        self._last_t = None

    # ---------- stav
    def export(self):
        return {"level": self.level, "baseline": [round(x, 4) for x in self.baseline]}

    def status(self):
        return {"level": self.level, "confidence": self.confidence, "estimate": self.estimate,
                "learned": len(self.baseline), "learning": len(self.baseline) < LEARN_MIN}

    def anchor(self, level):
        """Uživatel řekl aktuální stupeň."""
        self.level = level
        self.recent.clear()
        self.confidence = 1.0
        self.estimate = level

    # ---------- vstup z Raw Input
    def _reset_stroke(self):
        self.s_len = 0.0
        self.s_vmax = 0.0
        self.s_t0 = None
        self.b_t0 = None
        self.b_sum = 0.0

    def feed(self, dx, dy, t=None):
        """Jeden relativní pohyb (body senzoru). Vrací nový stupeň, pokud se změnil, jinak None."""
        t = time.perf_counter() if t is None else t
        changed = None
        if self._last_t is not None and t - self._last_t > STROKE_GAP and self.s_t0 is not None:
            changed = self._end_stroke()
        self._last_t = t
        d = math.hypot(dx, dy)
        if self.s_t0 is None:
            self.s_t0 = self.b_t0 = t
        self.s_len += d
        self.b_sum += d
        if t - self.b_t0 >= BIN:
            self.s_vmax = max(self.s_vmax, self.b_sum / (t - self.b_t0))
            self.b_t0, self.b_sum = t, 0.0
        return changed

    def idle(self, t=None):
        """Zavolat občas bez pohybu – uzavře rozpracovaný tah."""
        t = time.perf_counter() if t is None else t
        if self._last_t is not None and self.s_t0 is not None and t - self._last_t > STROKE_GAP:
            return self._end_stroke()
        return None

    # ---------- vyhodnocení
    def _end_stroke(self):
        length, vmax = self.s_len, self.s_vmax
        dur = (self._last_t or 0) - (self.s_t0 or 0)
        if vmax <= 0 and dur > 0:
            vmax = length / dur
        self._reset_stroke()
        if self.level is None or length <= 0 or vmax <= 0:
            return None
        if length < MIN_LEN:
            return None
        self.strokes += 1
        f = 0.5 * math.log(length) + 0.5 * math.log(vmax)
        evicted = self.recent[0] if len(self.recent) == RECENT else None
        self.recent.append(f)
        if len(self.baseline) < LEARN_MIN:
            self.baseline.append(f - math.log(self.level))
            return None
        if len(self.recent) < RECENT // 2:
            return None
        b = _median(self.baseline)
        m = _median(self.recent)
        est = math.exp(m - b)
        self.estimate = int(round(est))
        mad = _median([abs(x - b) for x in self.baseline]) * 1.4826 or 0.5
        se = 1.2533 * mad / math.sqrt(len(self.recent))
        cur = abs(math.log(est / self.level))
        best = min(LEVELS, key=lambda lv: abs(math.log(est / lv)))
        if best != self.level:
            # tlačítko přepíná jen dopředu dokola: 1–3 stisky jsou běžné, 4–5 stisků (= „pokles“) nepravděpodobné
            presses = (LEVELS.index(best) - LEVELS.index(self.level)) % len(LEVELS)
            z = (cur - abs(math.log(est / best))) / se - (0 if presses <= 3 else UNLIKELY)
            self.confidence = max(0.0, min(1.0, 1 - z / Z_SWITCH))
            self._streak = self._streak + 1 if (z >= Z_SWITCH and best == self._cand) else (1 if z >= Z_SWITCH else 0)
            self._cand = best
            if self._streak >= PERSIST:
                self.level = best
                self.recent.clear()
                self._streak = 0
                self.confidence = 0.6
                return best
        else:
            self._streak = 0
            self.confidence = max(0.0, min(1.0, 1 - cur / 0.29))
            # učit se jen z tahu, který právě vypadl z okna, a jen když celé okno jasně sedí –
            # čerstvé tahy po změně DPI by jinak zvyk posunuly k nové hodnotě
            if cur < AGREE and evicted is not None:
                self.baseline.append(evicted - math.log(self.level))
        return None
