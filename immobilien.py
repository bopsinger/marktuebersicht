"""Immobilienseite: Weltwert nach Art und Region (Savills), Wohnpreise und Gewerbepreise (BIZ), REITs (Yahoo).

Savills veröffentlicht einmal im Jahr; die Zahlen stehen deshalb fest unten und werden nach dem nächsten Bericht
von Hand nachgetragen. Wohn- und Gewerbepreise kommen vierteljährlich von der BIZ, REITs täglich von Yahoo.
Liefert eine Liste eigenständiger Teile ({"teil": ...}).
"""
import csv
import datetime as dt
import io
import time
import urllib.request

import aktien_markt as am

TEILE = ("welt", "wohnpreise", "gewerbepreise", "reits")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
BIS = "https://stats.bis.org/api/v2/data/dataflow/BIS/{fluss}/1.0/{schluessel}?format=csv&startPeriod=2000-Q1"

# Savills, „Total value of global real estate“, Bericht 2025, Stand Ende 2024 (Mrd. USD)
SAVILLS = {
    "stand": "Ende 2024",
    "gesamt": 393300,
    "arten": [("Wohnimmobilien", 286900, -2.7), ("Gewerbeimmobilien", 58500, 4.1), ("Agrarland", 47900, 7.9)],
    # Anteile am Wert der Wohnimmobilien; Nordamerika 22 %, davon USA 18 %
    "regionen": [("China", 26.0), ("Europa", 25.0), ("USA", 18.0), ("Übriges Nordamerika", 4.0), ("Übrige Welt", 27.0)],
}

WOHNEN = [("XW", "Welt"), ("5R", "Industrieländer"), ("4T", "Schwellenländer"), ("XM", "Eurozone"), ("US", "USA"),
          ("CN", "China"), ("JP", "Japan"), ("DE", "Deutschland"), ("GB", "Grossbritannien"), ("FR", "Frankreich"),
          ("IT", "Italien"), ("ES", "Spanien"), ("NL", "Niederlande"), ("CH", "Schweiz"), ("SE", "Schweden"),
          ("CA", "Kanada"), ("AU", "Australien"), ("KR", "Südkorea"), ("HK", "Hongkong"), ("IN", "Indien")]

# Gewerbe: je Land die breiteste vierteljährliche oder monatliche Reihe (Gebiet 0 = ganzes Land)
GEWERBE = [("US", "USA", "Q", "A", "alle Gewerbeimmobilien"), ("XM", "Eurozone", "Q", "A", "alle Gewerbeimmobilien"),
           ("DE", "Deutschland", "Q", "A", "alle Gewerbeimmobilien"), ("JP", "Japan", "Q", "A", "alle Gewerbeimmobilien"),
           ("ES", "Spanien", "Q", "A", "alle Gewerbeimmobilien"), ("NL", "Niederlande", "Q", "B", "Büros"),
           ("DK", "Dänemark", "Q", "A", "alle Gewerbeimmobilien"), ("HK", "Hongkong", "M", "B", "Büros"),
           ("SG", "Singapur", "Q", "B", "Büros")]

REITS = [("welt", "Welt", "REET", "iShares Global REIT", "US-10J"),
         ("usa", "USA", "VNQ", "Vanguard Real Estate", "US-10J"),
         ("international", "International ohne USA", "RWX", "SPDR DJ International Real Estate", "US-10J"),
         ("europa", "Europa", "EXI5.DE", "iShares STOXX Europe 600 Real Estate", "DE-10J"),
         ("japan", "Japan", "1343.T", "NEXT FUNDS J-REIT Index", "JP-10J"),
         ("schweiz", "Schweiz", "SRECHA.SW", "UBS SXI Real Estate Funds", "CH-10J")]


def _bis(fluss, schluessel):
    letzter = None
    for i in range(3):
        try:
            req = urllib.request.Request(BIS.format(fluss=fluss, schluessel=schluessel), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))
        except Exception as e:  # noqa: BLE001
            letzter = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"BIZ {fluss}: {letzter}")


def _periode(p):
    """'2026-Q2' -> Quartalsende, '2026-08' -> Monatsende, '2025' -> Jahresende (ISO)."""
    if "-Q" in p:
        j, q = p.split("-Q")
        m = int(q) * 3
    elif len(p) == 7:
        j, m = p.split("-")
        m = int(m)
    else:
        j, m = p, 12
    return (dt.date(int(j) + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()


def _aenderungen(reihe):
    """Veränderung in % über 1, 5, 10, 20 Jahre und Abstand zum Höchststand."""
    d, w = reihe[-1]
    letzt = dt.date.fromisoformat(d)
    aus = {"stand": d}
    for k, j in (("j1", 1), ("j5", 5), ("j10", 10), ("j20", 20)):
        ziel = (letzt - dt.timedelta(days=round(365.25 * j) - 20)).isoformat()
        vorher = [x for x in reihe if x[0] <= ziel]
        aus[k] = round((w / vorher[-1][1] - 1) * 100, 1) if vorher and reihe[0][0] <= ziel else None
    hoch = max(reihe, key=lambda x: x[1])
    aus.update(hoch=hoch[0], vom_hoch=round((w / hoch[1] - 1) * 100, 1))
    return aus


def welt():
    return {"teil": "welt", **SAVILLS}


def wohnpreise():
    gebiete = "+".join(c for c, _ in WOHNEN)
    zeilen = []
    roh = {}
    for art in ("N", "R"):
        for r in _bis("WS_SPP", f"Q.{gebiete}.{art}.628"):
            try:
                roh.setdefault((r["REF_AREA"], art), []).append((_periode(r["TIME_PERIOD"]), float(r["OBS_VALUE"])))
            except (ValueError, KeyError):
                pass
    for code, name in WOHNEN:
        aus = {"key": code, "name": name}
        for art, praefix in (("N", "nom"), ("R", "real")):
            reihe = sorted(roh.get((code, art), []))
            if not reihe:
                continue
            aus[praefix] = _aenderungen(reihe)
            aus[praefix + "_reihe"] = [(d, round(w, 1)) for d, w in reihe if d >= "2006-01-01"]
        if "nom" in aus:
            zeilen.append(aus)
    return {"teil": "wohnpreise", "zeilen": zeilen}


def gewerbepreise():
    alle = _bis("WS_CPP", "")
    zeilen = []
    for code, name, freq, typ, text in GEWERBE:
        reihe = sorted((_periode(r["TIME_PERIOD"]), float(r["OBS_VALUE"])) for r in alle
                       if r["REF_AREA"] == code and r["FREQ"] == freq and r["COVERED_AREA"] == "0" and r["RE_TYPE"] == typ
                       and r["OBS_VALUE"] not in ("", "NaN"))
        if len(reihe) < 8:
            continue
        zeilen.append({"key": code, "name": name, "art": text, **_aenderungen(reihe),
                       "reihe": [(d, round(w, 1)) for d, w in reihe if d >= "2006-01-01"]})
    return {"teil": "gewerbepreise", "zeilen": zeilen}


def reits(hole):
    zeilen = []
    for key, name, sym, text, anleihe in REITS:
        r = am._reihe(hole, sym)
        # Fehlerhafte Frühdaten (etwa beim Schweizer ETF 2010/11): erst nach dem letzten Tagessprung über 40 % beginnen
        reihe = r["reihe"]
        spruenge = [i for i in range(1, len(reihe)) if reihe[i - 1][1] and abs(reihe[i][1] / reihe[i - 1][1] - 1) > 0.4]
        if spruenge:
            r["reihe"] = reihe[spruenge[-1]:]
        k = am._kennzahlen(r["reihe"])
        rendite = r["dividende12"] / r["kurs"] * 100 if r.get("dividende12") and r.get("kurs") else None
        zeilen.append({"key": key, "name": name, "symbol": sym, "text": text, "waehrung": r["waehrung"], "anleihe": anleihe,
                       "ausschuettung": round(rendite, 2) if rendite else None, **k,
                       "reihe": am._wochen(r["reihe"], jahre=20)})
    return {"teil": "reits", "zeilen": zeilen}


def immobilien(hole, sicher):
    teile = [welt(), sicher(lambda _: wohnpreise(), "Immobilien Wohnpreise"),
             sicher(lambda _: gewerbepreise(), "Immobilien Gewerbepreise"), sicher(lambda _: reits(hole), "Immobilien REITs")]
    return [t for t in teile if t]


if __name__ == "__main__":
    import json
    import sys
    import abruf

    teile = immobilien(abruf.hole, abruf.sicher)
    with open(sys.argv[1] if len(sys.argv) > 1 else "/dev/null", "w", encoding="utf-8") as f:
        json.dump({"rows": teile}, f, ensure_ascii=False, separators=(",", ":"))
    print([t["teil"] for t in teile], abruf.FEHLER)
