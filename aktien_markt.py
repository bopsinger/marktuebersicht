"""Aktienseite: Regionen in USD, Sektoren, Marktbreite, Stress (VIX) und Bewertung.

Quelle: Yahoo Finance. Regionen und Sektoren über grosse Index-ETF; Renditen aus den um Dividenden
bereinigten Schlusskursen (Gesamtrendite). Liefert eine Liste eigenständiger Teile ({"teil": ...}).
Die Netzfunktionen kommen aus abruf.py (hole, yahoo_crumb), damit Cookies und Wiederholungen gleich bleiben.
"""
import datetime as dt
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

TEILE = ("regionen", "sektoren", "breite", "stress", "bewertung")

REGIONEN = [
    # key, Name, ETF, Beschreibung
    ("welt", "Welt", "ACWI", "iShares MSCI ACWI (Industrie- und Schwellenländer)"),
    ("usa", "USA", "SPY", "SPDR S&P 500"),
    ("europa", "Europa", "VGK", "Vanguard FTSE Europe"),
    ("japan", "Japan", "EWJ", "iShares MSCI Japan"),
    ("schwellen", "Schwellenländer", "EEM", "iShares MSCI Emerging Markets"),
]

SEKTOREN = {
    "welt": [("Technologie", "IXN"), ("Finanzen", "IXG"), ("Gesundheit", "IXJ"), ("Zyklischer Konsum", "RXI"),
             ("Basiskonsum", "KXI"), ("Energie", "IXC"), ("Industrie", "EXI"), ("Grundstoffe", "MXI"),
             ("Versorger", "JXI"), ("Kommunikation", "IXP"), ("Immobilien", "REET")],
    "usa": [("Technologie", "XLK"), ("Finanzen", "XLF"), ("Gesundheit", "XLV"), ("Zyklischer Konsum", "XLY"),
            ("Basiskonsum", "XLP"), ("Energie", "XLE"), ("Industrie", "XLI"), ("Grundstoffe", "XLB"),
            ("Versorger", "XLU"), ("Kommunikation", "XLC"), ("Immobilien", "XLRE")],
    # STOXX Europe 600 kennt eigene Supersektoren; hier die zwölf grössten, nach GICS-Nähe benannt
    "europa": [("Technologie", "EXV3.DE"), ("Banken", "EXV1.DE"), ("Versicherungen", "EXH5.DE"),
               ("Gesundheit", "EXV4.DE"), ("Industrie", "EXH4.DE"), ("Konsumgüter", "EXH7.DE"),
               ("Nahrungsmittel", "EXH3.DE"), ("Energie", "EXH1.DE"), ("Grundstoffe", "EXV6.DE"),
               ("Versorger", "EXH9.DE"), ("Autos", "EXV5.DE"), ("Telekom", "EXV2.DE")],
}

BREITE = [
    ("gleich", "Gleich gewichtet gegen Börsenwert", "^SPXEW", "^GSPC",
     "S&P 500 gleich gewichtet geteilt durch S&P 500. Fällt die Linie, tragen wenige Grosskonzerne den Markt."),
    ("klein", "Klein gegen gross", "^RUT", "^GSPC",
     "Russell 2000 geteilt durch S&P 500. Steigt die Linie, laufen kleinere Firmen besser."),
    ("stil", "Wachstum gegen Substanz", "IWF", "IWD",
     "Russell 1000 Growth geteilt durch Russell 1000 Value. Steigt die Linie, sind Wachstumswerte gefragt."),
]

BEWERTUNG = [("welt", "Welt", "ACWI"), ("usa", "USA (S&P 500)", "SPY"), ("nasdaq", "USA (Nasdaq 100)", "QQQ"),
             ("europa", "Europa", "VGK"), ("japan", "Japan", "EWJ"), ("schwellen", "Schwellenländer", "EEM")]


def _reihe(hole, symbol, tage=3652 + 40):
    """Tägliche Schlusskurse, um Dividenden bereinigt (adjclose), als [(date, wert)]."""
    start = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=tage)).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
           f"?period1={start}&period2={int(time.time()) + 86400}&interval=1d&events=div")
    j = hole(url)["chart"]["result"][0]
    meta = j["meta"]
    tz = dt.timezone(dt.timedelta(seconds=meta.get("gmtoffset", 0)))
    adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose")
    werte = adj or j["indicators"]["quote"][0].get("close") or []
    reihe = [(dt.datetime.fromtimestamp(t, tz).date(), float(w)) for t, w in zip(j.get("timestamp") or [], werte) if w is not None]
    # Laufender Kurs: Faktor zwischen bereinigtem und unbereinigtem Schluss bleibt am letzten Tag 1
    letzt, zeit = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
    if reihe and letzt and zeit:
        tag = dt.datetime.fromtimestamp(zeit, tz).date()
        if reihe[-1][0] == tag:
            reihe[-1] = (tag, float(letzt))
        elif reihe[-1][0] < tag:
            reihe.append((tag, float(letzt)))
    # Ausschüttungen der letzten zwölf Monate (für die selbst berechnete Dividendenrendite)
    grenze = time.time() - 365 * 86400
    div12 = sum(d.get("amount", 0) for d in ((j.get("events") or {}).get("dividends") or {}).values() if d.get("date", 0) >= grenze)
    return {"reihe": reihe, "name": meta.get("longName") or meta.get("shortName"), "waehrung": meta.get("currency"),
            "dividende12": div12, "kurs": letzt,
            "stand": dt.datetime.fromtimestamp(zeit, dt.timezone.utc).isoformat() if zeit else None}


def _vor(reihe, tage):
    ziel = reihe[-1][0] - dt.timedelta(days=tage)
    if reihe[0][0] > ziel + dt.timedelta(days=10):
        return None
    kandidat = None
    for d, w in reihe:
        if d <= ziel:
            kandidat = w
    return kandidat


def _rendite(reihe, tage=None, seit=None):
    if not reihe:
        return None
    basis = _vor(reihe, tage) if tage else None
    if seit:
        vorher = [w for d, w in reihe if d <= seit]
        basis = vorher[-1] if vorher else None
    if tage == 1:
        basis = reihe[-2][1] if len(reihe) > 1 else None
    return None if not basis else round((reihe[-1][1] / basis - 1) * 100, 2)


def _kennzahlen(reihe):
    heute = reihe[-1][0]
    aus = {"t1": _rendite(reihe, 1), "w1": _rendite(reihe, 7), "m1": _rendite(reihe, 30),
           "ytd": _rendite(reihe, seit=dt.date(heute.year - 1, 12, 31)), "j1": _rendite(reihe, 365),
           "j5": _rendite(reihe, 365 * 5 + 1), "j10": _rendite(reihe, 3652)}
    aus["pa10"] = None if aus["j10"] is None else round(((1 + aus["j10"] / 100) ** 0.1 - 1) * 100, 2)
    return aus


def _wochen(reihe, jahre=5, normiert=True):
    grenze = reihe[-1][0] - dt.timedelta(days=round(365.25 * jahre))
    wochen = {}
    for d, w in reihe:
        if d >= grenze:
            wochen[d.isocalendar()[:2]] = (d, w)
    punkte = sorted(wochen.values())
    if punkte and punkte[-1][0] != reihe[-1][0]:
        punkte.append(reihe[-1])
    if normiert and punkte:
        b = punkte[0][1]
        return [(d.isoformat(), round(w / b * 100, 2)) for d, w in punkte]
    return [(d.isoformat(), round(w, 2)) for d, w in punkte]


def regionen(daten):
    zeilen = []
    for key, name, etf, text in REGIONEN:
        r = daten[etf]["reihe"]
        zeilen.append({"key": key, "name": name, "symbol": etf, "text": text, "stand": daten[etf]["stand"],
                       **_kennzahlen(r), "reihe": _wochen(r)})
    return {"teil": "regionen", "zeilen": zeilen}


def sektoren(daten):
    aus = {"teil": "sektoren", "regionen": {}}
    for region, liste in SEKTOREN.items():
        zeilen = []
        for name, sym in liste:
            if sym in daten:
                k = _kennzahlen(daten[sym]["reihe"])
                zeilen.append({"name": name, "symbol": sym, **{f: k[f] for f in ("t1", "w1", "m1", "ytd", "j1", "j5")}})
        aus["regionen"][region] = zeilen
    return aus


def breite(daten):
    zeilen = []
    for key, name, a, b, text in BREITE:
        ra, rb = dict(daten[a]["reihe"]), dict(daten[b]["reihe"])
        verh = [(d, ra[d] / rb[d]) for d in sorted(set(ra) & set(rb)) if rb[d]]
        zeilen.append({"key": key, "name": name, "zaehler": a, "nenner": b, "text": text,
                       "j1": _rendite(verh, 365), "j5": _rendite(verh, 365 * 5 + 1), "reihe": _wochen(verh)})
    return {"teil": "breite", "zeilen": zeilen}


def stress(daten):
    vix, vix3 = daten["^VIX"]["reihe"], daten["^VIX3M"]["reihe"]
    d3 = dict(vix3)
    grenze = vix[-1][0] - dt.timedelta(days=365 * 2)
    reihe, letzt3 = [], None
    for d, w in vix:
        letzt3 = d3.get(d, letzt3)
        if d >= grenze:
            reihe.append((d.isoformat(), round(w, 2), round(letzt3, 2) if letzt3 else None))
    lang = [w for _, w in vix]
    return {"teil": "stress", "stand": daten["^VIX"]["stand"], "vix": round(vix[-1][1], 2), "vix3m": round(vix3[-1][1], 2),
            "verhaeltnis": round(vix[-1][1] / vix3[-1][1], 3), "mittel10": round(sum(lang) / len(lang), 1),
            "hoch10": round(max(lang), 1), "reihe": reihe}


def bewertung(hole, crumb, daten):
    if not crumb:
        raise RuntimeError("kein Yahoo-Crumb")
    syms = ",".join(s for _, _, s in BEWERTUNG)
    url = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={urllib.parse.quote(syms)}&crumb={urllib.parse.quote(crumb)}"
    roh = {q["symbol"]: q for q in hole(url)["quoteResponse"]["result"]}
    zeilen = []
    for key, name, sym in BEWERTUNG:
        q, r = roh.get(sym, {}), daten.get(sym, {})
        div = r.get("dividende12") / r["kurs"] * 100 if r.get("dividende12") and r.get("kurs") else None
        zeilen.append({"key": key, "name": name, "symbol": sym,
                       "kgv": round(q["trailingPE"], 1) if q.get("trailingPE") else None,
                       "dividende": round(div, 2) if div else None})
    if not any(z["kgv"] for z in zeilen):
        raise RuntimeError("Yahoo liefert kein KGV")
    return {"teil": "bewertung", "zeilen": zeilen}


def aktienmarkt(hole, crumb_fn, sicher):
    symbole = sorted({e for _, _, e, _ in REGIONEN} | {s for l in SEKTOREN.values() for _, s in l}
                     | {x for _, _, a, b, _ in BREITE for x in (a, b)} | {s for _, _, s in BEWERTUNG} | {"^VIX", "^VIX3M"})
    daten = {}

    def eins(s):
        return s, sicher(lambda _: _reihe(hole, s), f"Aktienseite {s}")

    with ThreadPoolExecutor(4) as ex:
        for s, r in ex.map(eins, symbole):
            if r and r["reihe"]:
                daten[s] = r
    teile = [sicher(lambda _, fn=fn: fn(daten), f"Aktienseite {fn.__name__}") for fn in (regionen, sektoren, breite, stress)]
    teile.append(sicher(lambda _: bewertung(hole, crumb_fn(), daten), "Aktienseite bewertung"))
    return [t for t in teile if t]


if __name__ == "__main__":
    import json
    import sys
    import abruf

    teile = aktienmarkt(abruf.hole, abruf.yahoo_crumb, abruf.sicher)
    with open(sys.argv[1] if len(sys.argv) > 1 else "/dev/null", "w", encoding="utf-8") as f:
        json.dump({"rows": teile}, f, ensure_ascii=False, separators=(",", ":"))
    print([t["teil"] for t in teile], abruf.FEHLER)
