"""Länderübersicht USA: Geldmenge, Vermögen und Schulden je Sektor, Verteilung.

Quellen (alle frei, ohne Schlüssel):
  Federal Reserve, Finanzierungsrechnung Z.1 (Tabellenpaket, vierteljährlich)
  Federal Reserve, H.6 Geldmengen (monatlich)
  Federal Reserve, Distributional Financial Accounts (vierteljährlich)
  US-Finanzministerium, Debt to the Penny (täglich)

Beträge in Milliarden US-Dollar, Daten als ISO-Datum (Monats- bzw. Quartalsende).
Liefert eine Liste von Bausteinen ({"teil": ...}), je Baustein eigenständig, damit ein Ausfall die anderen nicht mitreisst.
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
DFA_ZIP = "https://www.federalreserve.gov/releases/z1/dataviz/download/zips/dfa.zip"
SCHULD_TAG = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
              "?fields=record_date,tot_pub_debt_out_amt,debt_held_public_amt,intragov_hold_amt"
              "&filter=record_date:gte:{ab}&sort=-record_date&page%5Bsize%5D=10000")
AB = "2000-01-01"


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
    """'2026:Q2' -> '2026-06-30'"""
    j, n = q.split(":Q")
    monat = int(n) * 3
    ende = dt.date(int(j) + (monat == 12), monat % 12 + 1, 1) - dt.timedelta(days=1)
    return ende.isoformat()


class Z1:
    """Tabellen der Finanzierungsrechnung; Reihen in Mio. USD, Abruf nach Code (z. B. 'FL152090005.Q')."""

    def __init__(self, roh):
        self.zip = zipfile.ZipFile(io.BytesIO(roh))
        self.reihen = {}

    def tabelle(self, name):
        with self.zip.open(f"csv/{name}.csv") as f:
            zeilen = list(csv.reader(io.TextIOWrapper(f, "utf-8")))
        kopf = zeilen[0]
        for i, code in enumerate(kopf[1:], 1):
            reihe = []
            for z in zeilen[1:]:
                if ":Q" not in z[0]:
                    continue
                try:
                    reihe.append((_quartalsende(z[0]), float(z[i])))
                except (ValueError, IndexError):
                    pass
            self.reihen.setdefault(code, reihe)

    def __call__(self, code):
        return self.reihen[code]

    def letzt(self, code):
        return self.reihen[code][-1][1] / 1000  # Mrd.


def _ab(reihe, ab=AB):
    return [(d, round(w / 1000, 1)) for d, w in reihe if d >= ab]


def _summe(*reihen):
    """Summiert Reihen mit gleichen Daten (nur gemeinsame Daten)."""
    gemeinsam = set(d for d, _ in reihen[0])
    for r in reihen[1:]:
        gemeinsam &= set(d for d, _ in r)
    return sorted((d, sum(dict(r)[d] for r in reihen)) for d in gemeinsam)


def _veraenderung(reihe, jahre):
    """Prozentuale Veränderung gegenüber dem Wert vor n Jahren (Reihe aufsteigend, ISO-Daten)."""
    d, w = reihe[-1]
    ziel = (dt.date.fromisoformat(d) - dt.timedelta(days=round(365.25 * jahre))).isoformat()
    vorher = [x for x in reihe if x[0] <= ziel]
    if not vorher or not vorher[-1][1]:
        return None
    return round((w / vorher[-1][1] - 1) * 100, 2)


def _bip_jahr(z1):
    """BIP der letzten vier Quartale (Summe), als Reihe in Mio. USD."""
    q = z1("FU086902005.Q")
    return [(q[i][0], sum(w for _, w in q[i - 3:i + 1])) for i in range(3, len(q))]


# ---------------------------------------------------------------- Baustein 1: Geldmenge


def _h6():
    roh = _hole(H6_ZIP)
    with zipfile.ZipFile(io.BytesIO(roh)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith("_data.xml"))
        xml = z.read(name).decode("utf-8")
    reihen = {}
    for m in re.finditer(r'<kf:Series ([^>]*)>(.*?)</kf:Series>', xml, re.S):
        sn = re.search(r'SERIES_NAME="([^"]+)"', m.group(1)).group(1)
        if sn not in ("M1.M", "M2.M", "RESMO14A_N.M", "RESMOC14A_N.M", "RESMOB14A_N.M") or sn in reihen:
            continue
        obs = []
        for o in re.finditer(r'<frb:Obs ([^>]*)/?>', m.group(2)):
            a = o.group(1)
            w = re.search(r'OBS_VALUE="([^"]+)"', a)
            d = re.search(r'TIME_PERIOD="([^"]+)"', a)
            try:
                obs.append((d.group(1), float(w.group(1))))  # Mrd. USD
            except (AttributeError, ValueError):
                pass
        reihen[sn] = sorted(obs)
    return reihen


def geld(z1):
    h6 = _h6()
    namen = [("basis", "Notenbankgeld", "RESMO14A_N.M"), ("bargeld", "Bargeld", "RESMOC14A_N.M"),
             ("reserven", "Bankreserven bei der Fed", "RESMOB14A_N.M"), ("m1", "M1", "M1.M"), ("m2", "M2", "M2.M")]
    bip = _bip_jahr(z1)[-1][1] / 1000
    werte, reihen = [], {}
    for key, name, sn in namen:
        r = h6[sn]
        hoch = max(r, key=lambda x: x[1])
        werte.append({"key": key, "name": name, "wert": r[-1][1], "stand": r[-1][0],
                      "j1": _veraenderung(r, 1), "j5": _veraenderung(r, 5),
                      "hoch": hoch[1], "hoch_datum": hoch[0], "bip_anteil": round(r[-1][1] / bip * 100, 1)})
        reihen[key] = [(d, w) for d, w in r if d >= AB]
    fed = z1("FL714194005.Q")  # Bilanzsumme der Fed (Passiva inkl. Eigenkapital)
    werte.append({"key": "fed", "name": "Bilanzsumme der Fed", "wert": round(fed[-1][1] / 1000, 1), "stand": fed[-1][0],
                  "j1": _veraenderung(fed, 1), "j5": _veraenderung(fed, 5),
                  "hoch": round(max(w for _, w in fed) / 1000, 1),
                  "hoch_datum": max(fed, key=lambda x: x[1])[0], "bip_anteil": round(fed[-1][1] / 1000 / bip * 100, 1)})
    reihen["fed"] = _ab(fed)
    # Grössenordnungen: vom Notenbankgeld bis zum Geldvermögen aller Sektoren
    stufen = [
        ("Notenbankgeld", h6["RESMO14A_N.M"][-1][1], "Bargeld und Reserven der Banken"),
        ("M1", h6["M1.M"][-1][1], "Bargeld, Sicht- und Spareinlagen"),
        ("M2", h6["M2.M"][-1][1], "M1 plus kleine Termineinlagen und Geldmarktfonds"),
        ("BIP (12 Monate)", round(bip, 1), "Wirtschaftsleistung eines Jahres"),
        ("Kredite und Anleihen im Inland", round(z1.letzt("LA384104005.Q") + z1.letzt("LA794104005.Q"), 1),
         "Schulden aller inländischen Sektoren"),
        ("Geldvermögen der Haushalte", round(z1.letzt("FL154090005.Q"), 1), "Einlagen, Wertpapiere, Pensionen"),
        ("Nettovermögen der Haushalte", round(z1.letzt("FL152090005.Q"), 1), "Vermögen minus Schulden"),
    ]
    return {"teil": "geld", "werte": werte, "reihen": reihen,
            "stufen": [{"name": n, "wert": w, "text": t} for n, w, t in stufen]}


# ---------------------------------------------------------------- Baustein 2: Bilanz je Sektor

SEKTOREN = [
    # key, Name, Sachvermögen, Geldvermögen, Schulden, Aktien (Marktwert, als Eigenkapital in fremder Hand)
    ("haushalte", "Haushalte", "LM152010005.Q", "FL154090005.Q", "FL154190005.Q", None),
    ("kapital", "Kapitalgesellschaften", "LM102010005.Q", "FL104090005.Q", "FL104190005.Q", "LM103164105.Q"),
    ("personen", "Personenunternehmen", "LM112010005.Q", "FL114090005.Q", "FL114190005.Q", None),
    ("finanz", "Finanzsektor", None, "FL794090005.Q", "FL794190005.Q", "LM793164105.Q"),
    ("bund", "Bund", "LM315015005.Q", "FL314090005.Q", "FL314190005.Q", None),
    ("laender", "Bundesstaaten und Gemeinden", "LM212010095.Q", "FL214090005.Q", "FL214190005.Q", None),
]


def sektoren(z1):
    zeilen, verlauf = [], {}
    for key, name, sach, fin, schuld, aktien in SEKTOREN:
        s = z1.letzt(sach) if sach else 0.0
        f, l = z1.letzt(fin), z1.letzt(schuld)
        zeilen.append({"key": key, "name": name, "sach": round(s, 1), "fin": round(f, 1), "schulden": round(l, 1),
                       "netto": round(s + f - l, 1), "aktien": round(z1.letzt(aktien), 1) if aktien else None})
        teile = [z1(fin)] + ([z1(sach)] if sach else [])
        verm = _summe(*teile)
        sch = dict(z1(schuld))
        verlauf[key] = [(d, round((w - sch[d]) / 1000, 1)) for d, w in verm if d in sch and d >= AB]
    ausland = {"forderungen": round(z1.letzt("FL264090005.Q"), 1),      # Ansprüche des Auslands an die USA
               "verbindlichkeiten": round(z1.letzt("FL264194005.Q"), 1),  # Ansprüche der USA an das Ausland
               "netto": round(z1.letzt("FL882090265.Q"), 1)}
    verlauf["ausland"] = _ab(z1("FL882090265.Q"))
    return {"teil": "sektoren", "stand": z1("FL152090005.Q")[-1][0], "sektoren": zeilen, "ausland": ausland,
            "verlauf": verlauf}


# ---------------------------------------------------------------- Baustein 2b: Volksvermögen (Tabelle S1.b)


def volksvermoegen(z1):
    teile = [
        ("Sachvermögen der Haushalte", ["LM152010005.Q"], "Immobilien, Gebrauchsgüter"),
        ("Sachvermögen der Personenunternehmen", ["LM112010005.Q", "LM662090003.Q"], "Immobilien, Anlagen, Vorräte"),
        ("Kapitalgesellschaften (Marktwert)", ["LM882010405.Q"], "Sachvermögen, geschätzt über den Börsenwert"),
        ("Sachvermögen des Bundes", ["LM315015005.Q"], "Gebäude, Ausrüstung, ohne Land"),
        ("Sachvermögen der Bundesstaaten und Gemeinden", ["LM212010095.Q"], "Strassen, Schulen, Gebäude, ohne Land"),
        ("Nettoposition gegenüber dem Ausland", ["FL882090265.Q"], "Forderungen minus Verbindlichkeiten"),
    ]
    posten = [{"name": n, "wert": round(sum(z1.letzt(c) for c in cs), 1), "text": t} for n, cs, t in teile]
    gesamt = z1("FL892090005.Q")
    bip = dict(_bip_jahr(z1))
    return {"teil": "volksvermoegen", "stand": gesamt[-1][0], "gesamt": round(gesamt[-1][1] / 1000, 1),
            "j1": _veraenderung(gesamt, 1), "posten": posten,
            "bip_anteil": round(gesamt[-1][1] / bip[gesamt[-1][0]] * 100) if gesamt[-1][0] in bip else None,
            "reihe": _ab(gesamt), "reihe_bip": [(d, round(w / bip[d] * 100, 1)) for d, w in gesamt if d in bip and d >= AB]}


# ---------------------------------------------------------------- Baustein 3: Schulden


SCHULDNER = [
    ("haushalte", "Haushalte", "LA154104005.Q"),
    ("unternehmen", "Unternehmen", "LA144104005.Q"),
    ("bund", "Bund", "LA314104005.Q"),
    ("laender", "Bundesstaaten und Gemeinden", "LA214104005.Q"),
    ("finanz", "Finanzsektor", "LA794104005.Q"),
]


def schulden(z1):
    bip = dict(_bip_jahr(z1))
    zeilen, reihen = [], {}
    for key, name, code in SCHULDNER:
        r = z1(code)
        d, w = r[-1]
        zeilen.append({"key": key, "name": name, "wert": round(w / 1000, 1), "j1": _veraenderung(r, 1),
                       "j5": _veraenderung(r, 5), "bip_anteil": round(w / bip[d] * 100, 1) if d in bip else None})
        reihen[key] = [(d, round(w / 1000, 1), round(w / bip[d] * 100, 1) if d in bip else None) for d, w in r if d >= AB]
    haushalt = [
        ("Hypotheken", "FL153165105.Q"), ("Studienkredite", "FL153166220.Q"), ("Autokredite", "FL153166400.Q"),
        ("Kreditkarten", "FL153166100.Q"), ("Übrige Konsumkredite", "FL153166205.Q"),
    ]
    teile = [{"name": n, "wert": round(z1.letzt(c), 1)} for n, c in haushalt]
    rest = z1.letzt("FL154190005.Q") - sum(t["wert"] for t in teile)
    teile.append({"name": "Übrige Schulden", "wert": round(rest, 1)})
    return {"teil": "schulden", "stand": z1("LA384104005.Q")[-1][0], "schuldner": zeilen, "reihen": reihen,
            "haushalt": teile, "bip": round(bip[max(bip)] / 1000, 1)}


def staatsschuld_tag():
    j = json.loads(_hole(SCHULD_TAG.format(ab=AB)))
    rs = sorted(((r["record_date"], float(r["tot_pub_debt_out_amt"]) / 1e9,
                  float(r["debt_held_public_amt"]) / 1e9, float(r["intragov_hold_amt"]) / 1e9) for r in j["data"]))
    reihe = [(d, g) for d, g, _, _ in rs]
    d, g, p, i = rs[-1]
    # Monatswerte (letzter Tag je Monat) für die Linie
    monat = {}
    for x in reihe:
        monat[x[0][:7]] = x
    return {"teil": "staatsschuld_tag", "stand": d, "gesamt": round(g, 1), "publikum": round(p, 1),
            "intern": round(i, 1), "j1": _veraenderung(reihe, 1), "j5": _veraenderung(reihe, 5),
            "tage30": round(g - [w for t, w in reihe if t <= (dt.date.fromisoformat(d) - dt.timedelta(days=30)).isoformat()][-1], 1),
            "reihe": [(x[0], round(x[1], 1)) for x in monat.values()]}


# ---------------------------------------------------------------- Baustein 4: Wer hält die Staatsanleihen?


HALTER = [
    ("Ausland", ["LM263061105.Q"]),
    ("Federal Reserve", ["LM713061103.Q"]),
    ("Geldmarktfonds", ["FL633061105.Q"]),
    ("Investmentfonds und ETF", ["LM653061105.Q", "LM563061103.Q", "LM553061103.Q"]),
    ("Haushalte", ["LM153061105.Q"]),
    ("Banken", ["LM763061100.Q", "LM753061103.Q", "LM743061103.Q", "LM473061105.Q"]),
    ("Pensionskassen", ["LM573061105.Q", "LM343061105.Q", "LM223061143.Q"]),
    ("Bundesstaaten und Gemeinden", ["LM213061103.Q"]),
    ("Versicherungen", ["LM513061105.Q", "LM543061105.Q"]),
]


def staatsanleihen(z1):
    gesamt = z1.letzt("FL893061105.Q")
    halter = [{"name": n, "wert": round(sum(z1.letzt(c) for c in cs), 1)} for n, cs in HALTER]
    halter.append({"name": "Übrige", "wert": round(gesamt - sum(h["wert"] for h in halter), 1)})
    alle = dict(z1("FL893061105.Q"))
    anteile = {}
    for name, codes in HALTER[:3]:
        r = _summe(*[z1(c) for c in codes])
        anteile[name] = [(d, round(w / alle[d] * 100, 1)) for d, w in r if d in alle and d >= AB]
    return {"teil": "staatsanleihen", "stand": z1("FL893061105.Q")[-1][0], "gesamt": round(gesamt, 1),
            "handelbar": round(z1.letzt("FL313161105.Q"), 1), "halter": halter, "anteile": anteile}


# ---------------------------------------------------------------- Baustein 5: Vermögen der Haushalte


def haushalte(z1):
    gruppen = [
        ("Sachwerte", [
            ("Immobilien", ["LM155035005.Q"]),
            ("Gebrauchsgüter (Autos, Möbel)", ["LM155111005.Q"]),
            ("Übrige Sachwerte", ["LM165015205.Q", "LM165013765.Q"]),
        ]),
        ("Geld und Einlagen", [
            ("Bargeld und Sichteinlagen", ["FL153020005.Q"]),
            ("Spar- und Termineinlagen", ["FL153030005.Q", "LM153030505.Q"]),
            ("Geldmarktfonds", ["FL153034005.Q"]),
        ]),
        ("Wertpapiere und Beteiligungen", [
            ("Aktien", ["LM153064105.Q"]),
            ("Investmentfonds", ["LM153064205.Q"]),
            ("Hedgefonds und Kreditfonds", ["LM153064705.Q", "LM153064505.Q"]),
            ("Anleihen", ["LM154022005.Q"]),
            ("Beteiligungen an Personenunternehmen", ["LM153081115.Q"]),
        ]),
        ("Vorsorge", [
            ("Pensionsansprüche", ["FL153050005.Q"]),
            ("Lebensversicherungen", ["FL153040005.Q"]),
        ]),
        ("Übriges", [
            ("Ausgeliehene Kredite und Sonstiges", ["FL154035005.Q", "FL153090005.Q", "FL163070005.Q"]),
        ]),
    ]
    posten = []
    for gruppe, teile in gruppen:
        for name, codes in teile:
            posten.append({"gruppe": gruppe, "name": name, "wert": round(sum(z1.letzt(c) for c in codes), 1)})
    gesamt = z1.letzt("FL152000005.Q")
    return {"teil": "haushalte", "stand": z1("FL152000005.Q")[-1][0], "gesamt": round(gesamt, 1),
            "schulden": round(z1.letzt("FL154190005.Q"), 1), "netto": round(z1.letzt("FL152090005.Q"), 1),
            "abweichung": round(gesamt - sum(p["wert"] for p in posten), 1), "posten": posten}


# ---------------------------------------------------------------- Baustein 6: Verteilung (DFA)


GRUPPEN = [("top1", "Oberste 1 %", ("TopPt1", "RemainingTop1")), ("next9", "Nächste 9 %", ("Next9",)),
           ("next40", "Nächste 40 %", ("Next40",)), ("bottom50", "Untere 50 %", ("Bottom50",))]


def verteilung():
    with zipfile.ZipFile(io.BytesIO(_hole(DFA_ZIP))) as z:
        name = next(n for n in z.namelist() if n.endswith("dfa-networth-levels.csv"))
        zeilen = list(csv.DictReader(io.TextIOWrapper(z.open(name), "utf-8")))
    nach = {}
    for r in zeilen:
        nach.setdefault(_quartalsende(r["Date"]), {})[r["Category"]] = r
    letzt = max(nach)
    felder = {"immobilien": ["Real estate"], "aktien": ["Corporate equities and mutual fund shares"],
              "pensionen": ["DB pension entitlements", "DC pension entitlements"],
              "personen": ["Unincorporated businesses"], "gebrauch": ["Consumer durables"], "uebrige": ["Other assets"],
              "schulden": ["Liabilities"]}

    def wert(d, kats, spalten):
        return sum(float(nach[d][k][s]) for k in kats for s in spalten if k in nach[d]) / 1000  # Mrd.

    gesamt = {d: sum(wert(d, kats, ["Net worth"]) for _, _, kats in GRUPPEN) for d in nach}
    gruppen = []
    for key, name, kats in GRUPPEN:
        netto = wert(letzt, kats, ["Net worth"])
        teile = {k: round(wert(letzt, kats, s), 1) for k, s in felder.items()}
        gruppen.append({"key": key, "name": name, "netto": round(netto, 1), "anteil": round(netto / gesamt[letzt] * 100, 1),
                        **teile,
                        "reihe": [(d, round(wert(d, kats, ["Net worth"]) / gesamt[d] * 100, 1)) for d in sorted(nach) if d >= AB]})
    return {"teil": "verteilung", "stand": letzt, "gesamt": round(gesamt[letzt], 1), "gruppen": gruppen}


# ---------------------------------------------------------------- Gesamt


def usa(sicher):
    """sicher: Fehlerfänger aus abruf.py (fn, *args) -> Ergebnis oder None."""
    z1 = sicher(lambda _: _z1_laden(), "Fed Z.1")
    teile = []
    if z1:
        for fn in (geld, sektoren, volksvermoegen, schulden, staatsanleihen, haushalte):
            teile.append(sicher(lambda _, fn=fn: fn(z1), f"USA {fn.__name__}"))
    teile.append(sicher(lambda _: staatsschuld_tag(), "USA Staatsschuld tagesaktuell"))
    teile.append(sicher(lambda _: verteilung(), "USA Verteilung"))
    return [t for t in teile if t]


def _z1_laden():
    z1 = Z1(_hole(Z1_ZIP))
    for t in ("S1_b", "S1M_b", "S11_1_b", "S11_2_b", "S1311_s", "S13M_s", "S12_s", "S121_s", "S2_s", "D3_s",
              "F3_2_s", "F4_3_s", "S1_1_i_q"):
        z1.tabelle(t)
    return z1


if __name__ == "__main__":
    import sys

    def _sicher(fn, *args):
        try:
            return fn(*args)
        except Exception as e:  # noqa: BLE001
            print("FEHLER", args, repr(e), file=sys.stderr)
            return None

    ergebnis = usa(_sicher)
    print(json.dumps(ergebnis, ensure_ascii=False)[:3000])
    print(len(json.dumps(ergebnis, separators=(",", ":"))), "Bytes", [t["teil"] for t in ergebnis])
