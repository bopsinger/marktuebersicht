"""Rohstoffseite: Wert der Weltproduktion je Rohstoff, Terminkurven, Preisverhältnisse.

Produktionsmengen stehen fest (Quellen und Jahr in PRODUKTION) und werden einmal im Jahr nachgetragen;
bewertet wird mit dem aktuellen Terminpreis von Yahoo Finance. Liefert eine Liste eigenständiger Teile.
"""
import datetime as dt
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import aktien_markt as am

TEILE = ("produktion", "terminkurven", "verhaeltnisse")
OZ_JE_T = 32150.7466
LB_JE_T = 2204.62262
MMBTU_JE_BCM = 34.12e6       # 1 Mrd. m³ Erdgas ≈ 0,036 EJ (Umrechnung Energy Institute)
GJ_JE_T_KOHLE = 25.12        # Kraftwerkskohle mit 6000 kcal/kg (Basis des API2-Preises)
MWH_JE_MMBTU = 0.293071

# key, Name, Sektor, Yahoo-Symbol, Menge pro Jahr, Einheit der Menge, Quelle
PRODUKTION = [
    ("oel", "Rohöl", "Energie", "BZ=F", 82.79e6 * 365, "Fass", "Energy Institute 2025: Rohöl und Kondensat 2024, 82,8 Mio. Fass/Tag"),
    ("gas", "Erdgas", "Energie", ("NG=F", "TTF=F"), 4124, "Mrd. m³", "Energy Institute 2025: 4124 Mrd. m³ (2024)"),
    ("kohle", "Kohle", "Energie", "MTF=F", 182e18 / (GJ_JE_T_KOHLE * 1e9), "t", "Energy Institute 2025: 182 EJ (2024), umgerechnet auf Kohle mit 6000 kcal/kg"),
    ("gold", "Gold", "Edelmetalle", "GC=F", 3300, "t", "USGS 2026: 3300 t (2025); World Gold Council rund 3600 t"),
    ("silber", "Silber", "Edelmetalle", "SI=F", 26000, "t", "USGS 2026: 26 000 t (2025)"),
    ("platin", "Platin", "Edelmetalle", "PL=F", 170, "t", "rund 170 t (2025, Angaben nach WPIC)"),
    ("palladium", "Palladium", "Edelmetalle", "PA=F", 190, "t", "rund 190 t (2025)"),
    ("kupfer", "Kupfer", "Industriemetalle", "HG=F", 23e6, "t", "USGS 2026: 23 Mio. t Minenproduktion (2025)"),
    ("alu", "Aluminium", "Industriemetalle", "ALI=F", 73.78e6, "t", "International Aluminium Institute: 73,8 Mio. t Primäraluminium (2025)"),
    ("eisen", "Eisenerz", "Industriemetalle", "TIO=F", 2.6e9, "t", "USGS 2026: 2,6 Mrd. t verwertbares Erz (2025)"),
    ("mais", "Mais", "Agrar", "ZC=F", 1291.6e6, "t", "USDA November 2026: 1291,6 Mio. t (2026/27)"),
    ("weizen", "Weizen", "Agrar", "ZW=F", 827.5e6, "t", "USDA November 2026: 827,5 Mio. t (2026/27)"),
    ("soja", "Sojabohnen", "Agrar", "ZS=F", 442.5e6, "t", "USDA November 2026: 442,5 Mio. t (2026/27)"),
    ("zucker", "Zucker", "Agrar", "SB=F", 180e6, "t", "Internationale Zuckerorganisation rund 180 Mio. t (2025/26); USDA 184,9 Mio. t"),
    ("kaffee", "Kaffee", "Agrar", "KC=F", 178.8e6 * 60 / 1000, "t", "USDA: 178,8 Mio. Sack zu 60 kg (2025/26)"),
    ("kakao", "Kakao", "Agrar", "CC=F", 5.0e6, "t", "rund 5,0 Mio. t (2025/26, Schätzung StoneX)"),
    ("rind", "Rindfleisch", "Vieh", "LE=F", 61e6, "t", "USDA: rund 61 Mio. t Schlachtgewicht (2026; Angaben zwischen 60 und 61,6), bewertet zum US-Lebendrindpreis"),
    ("schwein", "Schweinefleisch", "Vieh", "HE=F", 120e6, "t", "USDA: rund 120 Mio. t Schlachtgewicht (2026), bewertet zum US-Mastschweinpreis"),
]

# Terminkurven: Basissymbol, Börse, Name, gehandelte Kontraktmonate
EINHEIT = {"GC=F": "USD/Unze", "SI=F": "USD/Unze", "PL=F": "USD/Unze", "PA=F": "USD/Unze", "HG=F": "USD/Pfund",
           "ZC=F": "US-Cent/Bushel", "ZW=F": "US-Cent/Bushel", "ZS=F": "US-Cent/Bushel", "SB=F": "US-Cent/Pfund", "KC=F": "US-Cent/Pfund",
           "LE=F": "US-Cent/Pfund Lebendgewicht", "HE=F": "US-Cent/Pfund"}
MONATE = "FGHJKMNQUVXZ"
KURVEN = [("CL", "NYM", "Rohöl WTI", MONATE), ("BZ", "NYM", "Rohöl Brent", MONATE), ("NG", "NYM", "Erdgas USA", MONATE),
          ("TTF", "NYM", "Erdgas TTF", MONATE), ("HG", "CMX", "Kupfer", "HKNUZ"), ("GC", "CMX", "Gold", "GJMQVZ"),
          ("ZC", "CBT", "Mais", "HKNUZ"), ("ZW", "CBT", "Weizen", "HKNUZ"), ("ZS", "CBT", "Sojabohnen", "FHKNQUX")]

VERHAELTNISSE = [("gold_silber", "Gold zu Silber", "GC=F", "SI=F", 1, "Unzen Silber für eine Unze Gold"),
                 ("kupfer_gold", "Kupfer zu Gold", "HG=F", "GC=F", 1000, "Kupferpreis (USD/lb) je 1000 USD Goldpreis; steigt in Aufschwüngen"),
                 ("oel_gold", "Gold zu Öl", "GC=F", "CL=F", 1, "Fass Rohöl WTI für eine Unze Gold")]


def _usd_je_t(sym, preis, eurusd):
    """Preis je Tonne in USD aus der Notierung des jeweiligen Kontrakts."""
    if sym in ("GC=F", "SI=F", "PL=F", "PA=F"):
        return preis * OZ_JE_T
    if sym == "HG=F":
        return preis * LB_JE_T
    if sym in ("ZC=F",):
        return preis / 100 * 39.3683       # US-Cent je Bushel (25,4 kg)
    if sym in ("ZW=F", "ZS=F"):
        return preis / 100 * 36.7437       # US-Cent je Bushel (27,2 kg)
    if sym in ("SB=F", "KC=F", "HE=F"):
        return preis / 100 * LB_JE_T       # US-Cent je Pfund (Mastschwein: je Pfund Schlachtgewicht)
    if sym == "LE=F":
        return preis / 100 * LB_JE_T / 0.63   # Lebendgewicht, umgerechnet auf Schlachtgewicht (Ausbeute rund 63 %)
    return preis                           # ALI, TIO, MTF, CC: USD je Tonne


def produktion(daten):
    eurusd = daten["EURUSD=X"]["reihe"][-1][1]
    zeilen, spanne = [], None
    for key, name, sektor, sym, menge, einheit, quelle in PRODUKTION:
        if key == "oel":
            preis = daten[sym]["reihe"][-1][1]
            wert, preistext = menge * preis, f"{preis:.1f} USD/Fass"
        elif key == "gas":
            hh = daten["NG=F"]["reihe"][-1][1]
            ttf = daten["TTF=F"]["reihe"][-1][1] * eurusd * MWH_JE_MMBTU   # EUR/MWh -> USD/MMBtu
            preis = (hh + ttf) / 2
            wert, preistext = menge * MMBTU_JE_BCM * preis, f"{preis:.1f} USD/MMBtu (Mittel aus Henry Hub {hh:.1f} und TTF {ttf:.1f})"
            spanne = (round(menge * MMBTU_JE_BCM * hh / 1e9), round(menge * MMBTU_JE_BCM * ttf / 1e9))
            sym = "NG=F"
        else:
            notiz = daten[sym]["reihe"][-1][1]
            je_t = _usd_je_t(sym, notiz, eurusd)
            wert = menge * je_t
            preistext = f"{notiz:,.{2 if notiz < 100 else 0}f} {EINHEIT.get(sym, 'USD/t')}".replace(",", "'")
        k = am._kennzahlen(daten[sym]["reihe"])
        zeilen.append({"key": key, "name": name, "sektor": sektor, "symbol": sym, "wert": round(wert / 1e9, 1),
                       "spanne": spanne if key == "gas" else None,
                       "preis": preistext, "quelle": quelle, **{f: k.get(f) for f in am.FELDER}})
    zeilen.sort(key=lambda z: -z["wert"])
    return {"teil": "produktion", "zeilen": zeilen, "stand": daten["BZ=F"]["stand"]}


def _kandidaten(heute):
    """Kontraktkürzel der nächsten 15 Monate je Rohstoff."""
    aus = []
    for basis, boerse, name, monate in KURVEN:
        for i in range(16):
            m = (heute.month - 1 + i) % 12
            j = heute.year + (heute.month - 1 + i) // 12
            if MONATE[m] in monate:
                aus.append((basis, f"{basis}{MONATE[m]}{j % 100:02d}.{boerse}", dt.date(j, m + 1, 1)))
    return aus


def terminkurven(hole, crumb):
    if not crumb:
        raise RuntimeError("kein Yahoo-Crumb")
    kand = _kandidaten(dt.date.today())
    preise = {}
    for i in range(0, len(kand), 50):
        teil = ",".join(s for _, s, _ in kand[i:i + 50])
        url = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={urllib.parse.quote(teil)}&crumb={urllib.parse.quote(crumb)}"
        for q in hole(url)["quoteResponse"]["result"]:
            if q.get("regularMarketPrice"):
                preise[q["symbol"]] = q["regularMarketPrice"]
    kurven = []
    for basis, boerse, name, _ in KURVEN:
        punkte = sorted((monat.isoformat()[:7], preise[s]) for b, s, monat in kand if b == basis and s in preise)
        if len(punkte) < 3:
            continue
        front = punkte[0]

        def nach(monate):
            ziel = dt.date.fromisoformat(front[0] + "-01")
            ziel = (ziel.replace(day=1) + dt.timedelta(days=round(30.44 * monate))).isoformat()[:7]
            # nächster Kontrakt innerhalb von zwei Monaten um das Ziel, sonst keiner
            ziel_d = dt.date.fromisoformat(ziel + "-01")
            nah = [p for p in punkte if abs((dt.date.fromisoformat(p[0] + "-01") - ziel_d).days) <= 62 and p != front]
            return min(nah, key=lambda p: abs((dt.date.fromisoformat(p[0] + "-01") - ziel_d).days)) if nah else None

        m6, m12 = nach(6), nach(12)
        kurven.append({"key": basis, "name": name, "front": front, "m6": m6, "m12": m12,
                       "spread6": round((m6[1] / front[1] - 1) * 100, 2) if m6 else None,
                       "spread12": round((m12[1] / front[1] - 1) * 100, 2) if m12 else None, "punkte": punkte})
    if not kurven:
        raise RuntimeError("keine Terminkontrakte erhalten")
    return {"teil": "terminkurven", "kurven": kurven, "stand": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")}


def verhaeltnisse(daten):
    zeilen = []
    for key, name, a, b, faktor, text in VERHAELTNISSE:
        ra, rb = dict(daten[a]["reihe"]), dict(daten[b]["reihe"])
        verh = [(d, ra[d] / rb[d] * faktor) for d in sorted(set(ra) & set(rb)) if rb[d] > 0]
        werte = [w for _, w in verh]
        wochen = am._wochen(verh, jahre=20, normiert=False)
        tief, hoch = min(verh, key=lambda x: x[1]), max(verh, key=lambda x: x[1])
        zeilen.append({"key": key, "name": name, "text": text, "wert": round(verh[-1][1], 2), "mittel": round(sum(werte) / len(werte), 2),
                       "hoch": (hoch[0].isoformat(), round(hoch[1], 2)), "tief": (tief[0].isoformat(), round(tief[1], 2)),
                       "j1": am._rendite(verh, 365), "reihe": wochen})
    return {"teil": "verhaeltnisse", "zeilen": zeilen}


def rohstoffseite(hole, crumb_fn, sicher):
    symbole = sorted({s for *_, sym, _, _, _ in PRODUKTION for s in (sym if isinstance(sym, tuple) else (sym,))}
                     | {x for *_, a, b, _, _ in VERHAELTNISSE for x in (a, b)} | {"EURUSD=X"})
    daten = {}

    def eins(s):
        return s, sicher(lambda _: am._reihe(hole, s), f"Rohstoffseite {s}")

    with ThreadPoolExecutor(4) as ex:
        for s, r in ex.map(eins, symbole):
            if r and r["reihe"]:
                daten[s] = r
    teile = [sicher(lambda _: produktion(daten), "Rohstoffseite produktion"),
             sicher(lambda _: terminkurven(hole, crumb_fn()), "Rohstoffseite terminkurven"),
             sicher(lambda _: verhaeltnisse(daten), "Rohstoffseite verhaeltnisse")]
    return [t for t in teile if t]


if __name__ == "__main__":
    import json
    import sys
    import abruf

    teile = rohstoffseite(abruf.hole, abruf.yahoo_crumb, abruf.sicher)
    with open(sys.argv[1] if len(sys.argv) > 1 else "/dev/null", "w", encoding="utf-8") as f:
        json.dump({"rows": teile}, f, ensure_ascii=False, separators=(",", ":"))
    print([t["teil"] for t in teile], abruf.FEHLER)
