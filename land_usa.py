"""Länderübersicht USA in drei Bausteinen: Geld und Schulden, Vermögen der Haushalte, Schulden und Zinslast.

Quellen (alle frei, ohne Schlüssel):
  Federal Reserve: Finanzierungsrechnung Z.1 (vierteljährlich) und Geldmenge H.6 (monatlich)
  BIZ (Bank für Internationalen Zahlungsausgleich): Schuldendienstquoten (vierteljährlich)
  US-Finanzministerium: Monthly Treasury Statement (Zinsausgaben, Einnahmen) und Debt to the Penny (täglich)

Beträge in Milliarden US-Dollar, Daten als ISO-Datum (Monats- bzw. Quartalsende), Verläufe über zehn Jahre.
Liefert eine Liste von Teilen ({"teil": ...}); jeder Teil ist eigenständig, damit ein Ausfall die anderen nicht mitreisst.
"""
import csv
import datetime as dt
import io
import json
import re
import time
import urllib.request
import zipfile

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
Z1_ZIP = "https://www.federalreserve.gov/releases/z1/current/z1_csv_files.zip"
H6_ZIP = "https://www.federalreserve.gov/datadownload/Output.aspx?rel=H6&filetype=zip"
BIS_DSR = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_DSR/1.0/Q.US.{sektor}?format=csv&startPeriod={ab}"
FISCAL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
SCHULD_TAG = (FISCAL + "/v2/accounting/od/debt_to_penny?fields=record_date,tot_pub_debt_out_amt,debt_held_public_amt,"
              "intragov_hold_amt&filter=record_date:gte:{ab}&sort=-record_date&page%5Bsize%5D=10000")
MTS9 = (FISCAL + "/v1/accounting/mts/mts_table_9?fields=record_date,classification_id,parent_id,classification_desc,"
        "current_month_rcpt_outly_amt&filter=record_date:gte:{ab},classification_desc:in:(Receipts,Total,Net%20Interest)"
        "&page%5Bsize%5D=10000")
JAHRE = 10
AB = dt.date(dt.date.today().year - JAHRE, 1, 1).isoformat()
TEILE = ("gesamt", "haushalte", "schulden", "ausland", "dsr", "zinslast", "staatsschuld_tag")


def _hole(url, versuche=3):
    letzter = None
    for i in range(versuche):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.build_opener().open(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            letzter = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url}: {letzter}")


def _quartalsende(q):
    """'2026:Q2' oder '2026-Q2' -> '2026-06-30'"""
    j, n = re.split(r"[:-]Q", q)
    monat = int(n) * 3
    return (dt.date(int(j) + (monat == 12), monat % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()


def _ab(reihe, faktor=1 / 1000, stellen=1):
    return [(d, round(w * faktor, stellen)) for d, w in reihe if d >= AB]


def _wert_am(reihe, datum):
    vorher = [w for d, w in reihe if d <= datum]
    return vorher[-1] if vorher else None


def _vor(reihe, jahre):
    d = reihe[-1][0]
    return _wert_am(reihe, (dt.date.fromisoformat(d) - dt.timedelta(days=round(365.25 * jahre) - 5)).isoformat())


def _kennzahl(reihe, prozent=True):
    """Letzter Wert, Veränderung über 1, 5, 10 Jahre (Prozent oder Differenz), Hoch und Tief im Zeitraum."""
    w = reihe[-1][1]
    aus = {"wert": w, "stand": reihe[-1][0]}
    for k, j in (("j1", 1), ("j5", 5), ("j10", JAHRE)):
        alt = _vor(reihe, j)
        aus[k] = None if alt in (None, 0) else round((w / alt - 1) * 100, 2) if prozent else round(w - alt, 3)
    sicht = [x for x in reihe if x[0] >= AB]
    hoch, tief = max(sicht, key=lambda x: x[1]), min(sicht, key=lambda x: x[1])
    aus.update(hoch=hoch[1], hoch_datum=hoch[0], tief=tief[1], tief_datum=tief[0])
    return aus


class Z1:
    """Tabellen der Finanzierungsrechnung; Reihen in Mio. USD, Abruf nach Code (z. B. 'FL152090005.Q')."""

    TABELLEN = ("S1M_b", "S1M_r", "D3_s", "F3_2_s", "S1_1_i_q")

    def __init__(self, roh):
        self.reihen = {}
        with zipfile.ZipFile(io.BytesIO(roh)) as z:
            for name in self.TABELLEN:
                with z.open(f"csv/{name}.csv") as f:
                    zeilen = list(csv.reader(io.TextIOWrapper(f, "utf-8")))
                for i, code in enumerate(zeilen[0][1:], 1):
                    reihe = []
                    for zl in zeilen[1:]:
                        try:
                            reihe.append((_quartalsende(zl[0]), float(zl[i])))
                        except (ValueError, IndexError):
                            pass
                    self.reihen.setdefault(code, reihe)

    def __call__(self, code):
        return self.reihen[code]

    def summe(self, *codes):
        teile = [dict(self.reihen[c]) for c in codes]
        daten = sorted(set.intersection(*(set(t) for t in teile)))
        return [(d, sum(t[d] for t in teile)) for d in daten]

    def bip(self):
        """BIP der letzten vier Quartale, Mio. USD."""
        q = self("FU086902005.Q")
        return [(q[i][0], sum(w for _, w in q[i - 3:i + 1])) for i in range(3, len(q))]


def _h6_m2():
    with zipfile.ZipFile(io.BytesIO(_hole(H6_ZIP))) as z:
        name = next(n for n in z.namelist() if n.lower().endswith("_data.xml"))
        xml = z.read(name).decode("utf-8")
    m = re.search(r'<kf:Series [^>]*SERIES_NAME="M2\.M"[^>]*>(.*?)</kf:Series>', xml, re.S)
    obs = []
    for o in re.finditer(r'<frb:Obs ([^>]*)/?>', m.group(1)):
        w, d = re.search(r'OBS_VALUE="([^"]+)"', o.group(1)), re.search(r'TIME_PERIOD="([^"]+)"', o.group(1))
        try:
            obs.append((d.group(1), float(w.group(1))))  # Mrd. USD
        except (AttributeError, ValueError):
            pass
    return sorted(obs)


# ---------------------------------------------------------------- A: Geld und Schulden


def gesamt(z1):
    m2 = _h6_m2()
    bip = dict(z1.bip())
    hh, unt = dict(z1("LA154104005.Q")), dict(z1("LA144104005.Q"))
    staat = dict(z1.summe("LA314104005.Q", "LA214104005.Q"))
    punkte, quote_m2, quote_bip, schuld = [], [], [], []
    for d in sorted(set(hh) & set(unt) & set(staat) & set(bip)):
        if d < AB:
            continue
        geld = _wert_am(m2, d)
        summe = (hh[d] + unt[d] + staat[d]) / 1000
        punkte.append({"datum": d, "haushalte": round(hh[d] / 1000, 1), "unternehmen": round(unt[d] / 1000, 1),
                       "staat": round(staat[d] / 1000, 1), "m2": geld, "bip": round(bip[d] / 1000, 1)})
        schuld.append((d, round(summe, 1)))
        quote_m2.append((d, round(summe / geld, 3)))
        quote_bip.append((d, round(summe / (bip[d] / 1000) * 100, 1)))
    return {"teil": "gesamt", "punkte": punkte,
            "kennzahlen": [
                {"key": "schulden", "name": "Schulden gesamt", **_kennzahl(schuld), "reihe": schuld},
                {"key": "m2", "name": "Geldmenge M2", **_kennzahl(m2), "reihe": [x for x in m2 if x[0] >= AB]},
                {"key": "quote_m2", "name": "Schulden je Dollar M2", **_kennzahl(quote_m2, False), "reihe": quote_m2},
                {"key": "quote_bip", "name": "Schulden in % des BIP", **_kennzahl(quote_bip, False), "reihe": quote_bip},
            ]}


# ---------------------------------------------------------------- B: Vermögen der Haushalte


ZERLEGUNG = [
    # key, Name, Codes (Mio. USD je Quartal; Summe = Veränderung des Nettovermögens)
    ("ersparnis", "Ersparnis (neu angelegt minus neue Schulden)", ["FU152090005.Q"]),
    ("immobilien", "Wertänderung Immobilien", ["FR155035005.Q"]),
    ("aktien", "Wertänderung Aktien", ["FR153064105.Q"]),
    ("fonds", "Wertänderung Fonds", ["FR153064205.Q", "FR153064705.Q", "FR153064505.Q"]),
    ("vorsorge", "Wertänderung Pensionen und Lebensversicherungen", ["FR153050005.Q", "FR153040005.Q"]),
]


def haushalte(z1):
    gesamt_r = dict(z1("FC152090005.Q"))
    teile = {k: dict(z1.summe(*cs)) for k, _, cs in ZERLEGUNG}
    reval, sonst = dict(z1("FR152090005.Q")), dict(z1("FV152090005.Q"))
    jahre = {}
    for d in sorted(gesamt_r):
        if d < AB:
            continue
        j = jahre.setdefault(d[:4], {"jahr": d[:4], "quartale": 0, **{k: 0.0 for k, _, _ in ZERLEGUNG}, "uebrige": 0.0, "gesamt": 0.0})
        j["quartale"] += 1
        bekannt = 0.0
        for k, _, _ in ZERLEGUNG:
            j[k] += teile[k].get(d, 0.0)
            if k != "ersparnis":
                bekannt += teile[k].get(d, 0.0)
        # übrige Wertänderungen (Gebrauchsgüter, Firmenbeteiligungen, Anleihen) und sonstige Änderungen (Statistikbrüche)
        j["uebrige"] += reval.get(d, 0.0) - bekannt + sonst.get(d, 0.0)
        j["gesamt"] += gesamt_r[d]
    for j in jahre.values():
        for k in list(j):
            if isinstance(j[k], float):
                j[k] = round(j[k] / 1000, 1)
    netto = z1("FL152090005.Q")
    quote = z1("FL152090006.Q")  # Nettovermögen in % des verfügbaren Einkommens
    vermoegen, schulden = z1("FL152000005.Q"), z1("FL154190005.Q")
    einkommen = dict(z1("FA156012005.Q"))
    schuldquote = [(d, round(w / einkommen[d] * 100, 1)) for d, w in schulden if d in einkommen]
    return {"teil": "haushalte", "namen": {k: n for k, n, _ in ZERLEGUNG} | {"uebrige": "Übrige Wert- und Bestandsänderungen"},
            "jahre": list(jahre.values()),
            "kennzahlen": [
                {"key": "netto", "name": "Nettovermögen", **_kennzahl(_ab(netto)), "reihe": _ab(netto)},
                {"key": "vermoegen", "name": "Vermögen", **_kennzahl(_ab(vermoegen)), "reihe": _ab(vermoegen)},
                {"key": "schulden", "name": "Schulden", **_kennzahl(_ab(schulden)), "reihe": _ab(schulden)},
                {"key": "netto_einkommen", "name": "Nettovermögen in % des Einkommens", "einheit": "%",
                 **_kennzahl(_ab(quote, 1, 0), False), "reihe": _ab(quote, 1, 0)},
                {"key": "schulden_einkommen", "name": "Schulden in % des Einkommens", "einheit": "%",
                 **_kennzahl([x for x in schuldquote if x[0] >= AB], False), "reihe": [x for x in schuldquote if x[0] >= AB]},
            ]}


# ---------------------------------------------------------------- C: Schulden und Zinslast


SCHULDNER = [("haushalte", "Haushalte", "LA154104005.Q"), ("unternehmen", "Unternehmen", "LA144104005.Q"),
             ("bund", "Bund", "LA314104005.Q"), ("laender", "Bundesstaaten und Gemeinden", "LA214104005.Q")]


def schulden(z1):
    bip = dict(z1.bip())
    zeilen = []
    for key, name, code in SCHULDNER:
        r = z1(code)
        quote = [(d, round(w / bip[d] * 100, 1)) for d, w in r if d in bip and d >= AB]
        zeilen.append({"key": key, "name": name, "wert": round(r[-1][1] / 1000, 1), "stand": r[-1][0],
                       "j1": _kennzahl(r)["j1"], **{"quote_" + k: v for k, v in _kennzahl(quote, False).items()}, "reihe": quote})
    return {"teil": "schulden", "schuldner": zeilen, "bip": round(bip[max(bip)] / 1000, 1)}


def ausland(z1):
    """Bestand und Anteil ausländischer Halter an den handelbaren US-Staatsanleihen."""
    alle = dict(z1("FL893061105.Q"))
    bestand = z1("LM263061105.Q")
    anteil = [(d, round(w / alle[d] * 100, 1)) for d, w in bestand if d in alle and d >= AB]
    fed = [(d, round(w / alle[d] * 100, 1)) for d, w in z1("LM713061103.Q") if d in alle and d >= AB]
    return {"teil": "ausland", "bestand": _kennzahl(_ab(bestand)), "anteil": _kennzahl(anteil, False),
            "reihe_bestand": _ab(bestand), "reihe_anteil": anteil, "reihe_fed": fed}


def dsr():
    """Schuldendienstquoten der BIZ: Zins und Tilgung in % des verfügbaren Einkommens."""
    aus = {"teil": "dsr"}
    for key, sektor in (("haushalte", "H"), ("unternehmen", "N")):
        roh = _hole(BIS_DSR.format(sektor=sektor, ab=AB[:4] + "-Q1")).decode("utf-8")
        reihe = sorted((_quartalsende(r["TIME_PERIOD"]), float(r["OBS_VALUE"]))
                       for r in csv.DictReader(io.StringIO(roh)) if r.get("OBS_VALUE") not in (None, "", "NaN"))
        aus[key] = {**_kennzahl(reihe, False), "reihe": reihe}
    return aus


def zinslast():
    """Nettozinsausgaben des Bundes in % der Einnahmen, jeweils über die letzten zwölf Monate."""
    ab = (dt.date.fromisoformat(AB) - dt.timedelta(days=370)).isoformat()
    daten = json.loads(_hole(MTS9.format(ab=ab)))["data"]
    monate = {}
    for d in {r["record_date"] for r in daten}:
        zeilen = [r for r in daten if r["record_date"] == d]
        einnahmen_id = next((r["classification_id"] for r in zeilen if r["classification_desc"] == "Receipts"), None)
        einnahmen = next((r for r in zeilen if r["classification_desc"] == "Total" and r["parent_id"] == einnahmen_id), None)
        zins = next((r for r in zeilen if r["classification_desc"] == "Net Interest"), None)
        try:
            monate[d] = (float(zins["current_month_rcpt_outly_amt"]) / 1e9, float(einnahmen["current_month_rcpt_outly_amt"]) / 1e9)
        except (TypeError, ValueError):
            pass
    reihe, z12 = [], []
    folge = sorted(monate)
    for i in range(11, len(folge)):
        fenster = folge[i - 11:i + 1]
        z, e = sum(monate[d][0] for d in fenster), sum(monate[d][1] for d in fenster)
        reihe.append((folge[i], round(z / e * 100, 1)))
        z12.append((folge[i], round(z, 1)))
    reihe = [x for x in reihe if x[0] >= AB]
    return {"teil": "zinslast", **_kennzahl(reihe, False), "reihe": reihe,
            "zinsen_12m": z12[-1][1], "zinsen_reihe": [x for x in z12 if x[0] >= AB]}


def staatsschuld_tag():
    j = json.loads(_hole(SCHULD_TAG.format(ab=AB)))

    def zahl(s):
        try:
            return float(s) / 1e9
        except (TypeError, ValueError):
            return None

    rs = sorted((r["record_date"], zahl(r["tot_pub_debt_out_amt"]), zahl(r["debt_held_public_amt"]),
                 zahl(r["intragov_hold_amt"])) for r in j["data"])
    rs = [r for r in rs if r[1] is not None]
    reihe = [(d, round(g, 1)) for d, g, _, _ in rs]
    d, g, p, i = rs[-1]
    monat = {}
    for x in reihe:
        monat[x[0][:7]] = x
    k = _kennzahl(reihe)
    vor30 = _wert_am(reihe, (dt.date.fromisoformat(d) - dt.timedelta(days=30)).isoformat())
    return {"teil": "staatsschuld_tag", **k, "publikum": round(p or 0, 1), "intern": round(i or 0, 1),
            "t30": round((g / vor30 - 1) * 100, 2) if vor30 else None, "reihe": list(monat.values())}


# ---------------------------------------------------------------- Gesamt


def usa(sicher):
    """sicher: Fehlerfänger aus abruf.py (fn, *args) -> Ergebnis oder None."""
    z1 = sicher(lambda _: Z1(_hole(Z1_ZIP)), "Fed Z.1")
    teile = []
    if z1:
        for fn in (gesamt, haushalte, schulden, ausland):
            teile.append(sicher(lambda _, fn=fn: fn(z1), f"USA {fn.__name__}"))
    for fn in (dsr, zinslast, staatsschuld_tag):
        teile.append(sicher(lambda _, fn=fn: fn(), f"USA {fn.__name__}"))
    return [t for t in teile if t]


if __name__ == "__main__":
    import sys

    def _sicher(fn, *args):
        try:
            return fn(*args)
        except Exception as e:  # noqa: BLE001
            print("FEHLER", args, repr(e), file=sys.stderr)
            return None

    ergebnis = usa(_sicher)
    with open(sys.argv[1] if len(sys.argv) > 1 else "/dev/null", "w", encoding="utf-8") as f:
        json.dump({"rows": ergebnis}, f, ensure_ascii=False, separators=(",", ":"))
    print(len(json.dumps(ergebnis, separators=(",", ":"))), "Bytes", [t["teil"] for t in ergebnis])
