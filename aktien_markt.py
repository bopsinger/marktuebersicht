"""Aktienseite: Weltmarkt nach Märkten und Sektoren, Bewertung, Risiko, dazu Sektoren und Marktbreite für die USA.

Quellen: State Street (Bestandsliste des SPDR Portfolio MSCI Global Stock Market ETF, für die Anteile der Märkte)
und Yahoo Finance (Kurse, Sektorgewichte des iShares MSCI ACWI, KGV). Renditen aus den um Dividenden bereinigten
Schlusskursen (Gesamtrendite). Liefert eine Liste eigenständiger Teile ({"teil": ...}).
Die Yahoo-Netzfunktionen kommen aus abruf.py (hole, yahoo_crumb), damit Cookies und Wiederholungen gleich bleiben.
"""
import datetime as dt
import io
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor

TEILE = ("maerkte", "sektorgewichte", "sektoren", "breite", "stress", "bewertung")
SSGA = "https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spgm.xlsx"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

MAERKTE = [
    # key, Name, Handelswährungen in der Bestandsliste, Länder-ETF für Rendite und Bewertung, Bezeichnung des ETF
    ("usa", "USA", ("USD",), "SPY", "SPDR S&P 500"),
    ("eurozone", "Eurozone", ("EUR",), "EZU", "iShares MSCI Eurozone"),
    ("japan", "Japan", ("JPY",), "EWJ", "iShares MSCI Japan"),
    ("kanada", "Kanada", ("CAD",), "EWC", "iShares MSCI Canada"),
    ("grossbritannien", "Grossbritannien", ("GBP",), "EWU", "iShares MSCI United Kingdom"),
    ("china", "China", ("HKD", "CNY"), "MCHI", "iShares MSCI China"),
    ("schweiz", "Schweiz", ("CHF",), "EWL", "iShares MSCI Switzerland"),
    ("taiwan", "Taiwan", ("TWD",), "EWT", "iShares MSCI Taiwan"),
    ("indien", "Indien", ("INR",), "INDA", "iShares MSCI India"),
    ("suedkorea", "Südkorea", ("KRW",), "EWY", "iShares MSCI South Korea"),
    ("australien", "Australien", ("AUD",), "EWA", "iShares MSCI Australia"),
]
# In US-Dollar gehandelte Auslandstitel (hinterlegte Aktien) dem Heimatmarkt zuordnen
AUSLAND_IN_USD = [
    ("taiwan", r"TAIWAN SEMI|HON HAI|CHUNGHWA|UNITED MICROELECTRON|AUO CORP|ASE TECH"),
    ("suedkorea", r"SAMSUNG|POSCO|KB FINANCIAL|SHINHAN|WOORI|KOREA ELEC|\bLG\b|SK HYNIX"),
    ("indien", r"ICICI|STATE BANK OF INDI|DR\. REDDY|RELIANCE|LARSEN|INFOSYS|MAHINDRA|WIPRO|HDFC|TATA|AXIS BANK"),
    ("china", r"ALIBABA|PDD HOLDINGS|BAIDU|JD\.COM|NETEASE|TRIP\.COM|TAL EDUCATION|VIPSHOP|KE HOLDINGS|\bNIO\b|LI AUTO|XPENG|YUM CHINA|BEIGENE|BEONE|ZTO|FUTU|BILIBILI|TENCENT MUSIC|H WORLD|NEW ORIENTAL"),
    ("grossbritannien", r"ASTRAZENECA|COMPASS GROUP"),
]

SEKTORNAMEN = {"technology": ("Technologie", "IXN"), "financial_services": ("Finanzen", "IXG"),
               "healthcare": ("Gesundheit", "IXJ"), "industrials": ("Industrie", "EXI"),
               "consumer_cyclical": ("Zyklischer Konsum", "RXI"), "communication_services": ("Kommunikation", "IXP"),
               "consumer_defensive": ("Basiskonsum", "KXI"), "energy": ("Energie", "IXC"),
               "basic_materials": ("Grundstoffe", "MXI"), "utilities": ("Versorger", "JXI"), "realestate": ("Immobilien", "REET")}

SEKTOREN = {
    "usa": [("Technologie", "XLK"), ("Finanzen", "XLF"), ("Gesundheit", "XLV"), ("Zyklischer Konsum", "XLY"),
            ("Basiskonsum", "XLP"), ("Energie", "XLE"), ("Industrie", "XLI"), ("Grundstoffe", "XLB"),
            ("Versorger", "XLU"), ("Kommunikation", "XLC"), ("Immobilien", "XLRE")],
}

BREITE = [
    ("gleich", "Gleich gewichtet gegen Börsenwert", "^SPXEW", "^GSPC",
     "S&P 500 gleich gewichtet geteilt durch S&P 500. Fällt die Linie, tragen wenige Grosskonzerne den Markt."),
    ("klein", "Klein gegen gross", "^RUT", "^GSPC",
     "Russell 2000 geteilt durch S&P 500. Steigt die Linie, laufen kleinere Firmen besser."),
    ("stil", "Wachstum gegen Substanz", "IWF", "IWD",
     "Russell 1000 Growth geteilt durch Russell 1000 Value. Steigt die Linie, sind Wachstumswerte gefragt."),
]

BEWERTUNG = [("welt", "Welt", "ACWI"), ("usa", "USA (S&P 500)", "SPY"), ("nasdaq", "USA (Nasdaq 100)", "QQQ")] + \
    [(k, n, e) for k, n, _, e, _ in MAERKTE if k != "usa"]


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


def _ssga_bestand():
    """Bestandsliste als [(Name, Gewicht in %, Handelswährung)] und Stichtag."""
    req = urllib.request.Request(SSGA, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as r:
        roh = r.read()
    z = zipfile.ZipFile(io.BytesIO(roh))
    m = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    texte = ["".join(t.text or "" for t in si.iter(m + "t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(m + "si")]
    zeilen = []
    for row in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(m + "row"):
        zellen = []
        for c in row.findall(m + "c"):
            v = c.find(m + "v")
            zellen.append(texte[int(v.text)] if c.get("t") == "s" and v is not None else (v.text if v is not None else ""))
        zeilen.append(zellen)
    stand = next((z[1] for z in zeilen if z and z[0].startswith("Holdings")), "")
    i = next(k for k, z in enumerate(zeilen) if z and z[0] == "Name")
    kopf = zeilen[i]
    bestand = []
    for z in zeilen[i + 1:]:
        d = dict(zip(kopf, z))
        try:
            bestand.append((d["Name"], float(d["Weight"]), d["Local Currency"]))
        except (KeyError, ValueError):
            pass
    return bestand, stand.replace("As of ", "")


def maerkte(daten):
    bestand, stand = _ssga_bestand()
    anteil = {k: 0.0 for k, *_ in MAERKTE}
    anteil["uebrige"] = 0.0
    nach_waehrung = {w: k for k, _, ws, _, _ in MAERKTE for w in ws}
    for name, gewicht, waehrung in bestand:
        markt = nach_waehrung.get(waehrung, "uebrige")
        if waehrung == "USD":
            for ziel, muster in AUSLAND_IN_USD:
                if re.search(muster, name):
                    markt = ziel
                    break
            else:
                if re.search(r"\b(ADR|GDR|ADS)\b", name):
                    markt = "uebrige"
        anteil[markt] += gewicht
    summe = sum(anteil.values())
    zeilen = []
    for key, name, _, etf, text in MAERKTE:
        r = daten.get(etf)
        k = _kennzahlen(r["reihe"]) if r else {}
        zeilen.append({"key": key, "name": name, "anteil": round(anteil[key] / summe * 100, 2), "symbol": etf, "text": text,
                       **{f: k.get(f) for f in ("t1", "ytd", "j1", "j5", "j10", "pa10")}})
    zeilen.sort(key=lambda z: -z["anteil"])
    welt = _kennzahlen(daten["ACWI"]["reihe"]) if "ACWI" in daten else {}
    return {"teil": "maerkte", "stand": stand, "titel": len(bestand), "uebrige": round(anteil["uebrige"] / summe * 100, 2),
            "zeilen": zeilen, "welt": {f: welt.get(f) for f in ("t1", "ytd", "j1", "j5", "j10", "pa10")}}


def sektorgewichte(hole, crumb, daten):
    if not crumb:
        raise RuntimeError("kein Yahoo-Crumb")
    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/ACWI?modules=topHoldings&crumb={urllib.parse.quote(crumb)}"
    th = hole(url)["quoteSummary"]["result"][0]["topHoldings"]
    zeilen = []
    for eintrag in th.get("sectorWeightings", []):
        for schluessel, wert in eintrag.items():
            name, etf = SEKTORNAMEN.get(schluessel, (schluessel, None))
            k = _kennzahlen(daten[etf]["reihe"]) if etf in daten else {}
            zeilen.append({"name": name, "anteil": round((wert.get("raw") or 0) * 100, 2), "symbol": etf,
                           **{f: k.get(f) for f in ("t1", "ytd", "j1", "j5")}})
    if not zeilen:
        raise RuntimeError("Yahoo liefert keine Sektorgewichte")
    zeilen.sort(key=lambda z: -z["anteil"])
    return {"teil": "sektorgewichte", "zeilen": zeilen}


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


def _wochenreihe20(hole, symbol):
    j = hole(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=20y&interval=1wk")["chart"]["result"][0]
    reihe = [(dt.date.fromtimestamp(t).isoformat(), round(w, 2)) for t, w in zip(j.get("timestamp") or [], j["indicators"]["quote"][0].get("close") or []) if w is not None]
    letzt = j["meta"].get("regularMarketPrice")
    return reihe, letzt


def stress(hole):
    vix, vix_jetzt = _wochenreihe20(hole, "^VIX")
    move, move_jetzt = _wochenreihe20(hole, "^MOVE")
    werte = lambda r: [w for _, w in r]
    return {"teil": "stress", "stand": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
            "vix": vix_jetzt or vix[-1][1], "move": move_jetzt or move[-1][1],
            "vix_mittel": round(sum(werte(vix)) / len(vix), 1), "move_mittel": round(sum(werte(move)) / len(move), 1),
            "vix_hoch": max(vix, key=lambda x: x[1]), "move_hoch": max(move, key=lambda x: x[1]),
            "vix_reihe": vix, "move_reihe": move}


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
    symbole = sorted({e for _, _, _, e, _ in MAERKTE} | {"ACWI"} | {e for _, e in SEKTORNAMEN.values()}
                     | {s for l in SEKTOREN.values() for _, s in l} | {x for _, _, a, b, _ in BREITE for x in (a, b)}
                     | {s for _, _, s in BEWERTUNG})
    daten = {}

    def eins(s):
        return s, sicher(lambda _: _reihe(hole, s), f"Aktienseite {s}")

    with ThreadPoolExecutor(4) as ex:
        for s, r in ex.map(eins, symbole):
            if r and r["reihe"]:
                daten[s] = r
    crumb = crumb_fn()
    teile = [sicher(lambda _, fn=fn: fn(daten), f"Aktienseite {fn.__name__}") for fn in (maerkte, sektoren, breite)]
    teile.append(sicher(lambda _: sektorgewichte(hole, crumb, daten), "Aktienseite sektorgewichte"))
    teile.append(sicher(lambda _: stress(hole), "Aktienseite stress"))
    teile.append(sicher(lambda _: bewertung(hole, crumb, daten), "Aktienseite bewertung"))
    return [t for t in teile if t]


if __name__ == "__main__":
    import json
    import sys
    import abruf

    teile = aktienmarkt(abruf.hole, abruf.yahoo_crumb, abruf.sicher)
    with open(sys.argv[1] if len(sys.argv) > 1 else "/dev/null", "w", encoding="utf-8") as f:
        json.dump({"rows": teile}, f, ensure_ascii=False, separators=(",", ":"))
    print([t["teil"] for t in teile], abruf.FEHLER)
