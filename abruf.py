#!/usr/bin/env python3
"""Holt Kurse, Renditen und Nachrichten für das Dashboard „Marktübersicht“.

Schreibt fünf JSON-Dateien in das Zielverzeichnis (erstes Argument):
  werte.json     Indizes und Rohstoffe mit Veränderungen 1T / YTD / 1J / 5J
  aktien.json    die grössten Titel je Index
  zinsen.json    Staatsanleihen (1J, 5J, 10J, 30J, soweit verfügbar), Veränderungen in Basispunkten
  verlauf.json   Wochenschlusskurse der letzten 12 Monate für die Kacheln (auch 10-jährige Renditen, id "zins-<Land>")
  news.json      aktuelle Schlagzeilen

Quellen: Yahoo Finance (Kurse), US-Finanzministerium, Bundesbank, Bank of England, japanisches
Finanzministerium, Bank of Canada, RBA, SNB und CFETS (Renditen), CoinMarketCap (Krypto gesamt), CNBC- und Yahoo-RSS (Nachrichten).
Nur Standardbibliothek, damit es in jeder frischen Sitzung ohne Installation läuft.
"""
import datetime as dt
import email.utils
import http.cookiejar
import json
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0"
JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(JAR))
FEHLER = []

# ---------------------------------------------------------------- Stammdaten

INDIZES = [
    # id, Name, Region, Yahoo-Symbol
    ("spx", "S&P 500", "USA", "^GSPC"),
    ("rut", "Russell 2000", "USA", "^RUT"),
    ("ixic", "Nasdaq Composite", "USA", "^IXIC"),
    ("dax", "DAX", "Deutschland", "^GDAXI"),
    ("ibex", "IBEX 35", "Spanien", "^IBEX"),
    ("mib", "FTSE MIB", "Italien", "FTSEMIB.MI"),
    ("smi", "SMI", "Schweiz", "^SSMI"),
    ("n225", "Nikkei 225", "Japan", "^N225"),
    ("shcomp", "Shanghai Composite", "China", "000001.SS"),
    ("kospi", "KOSPI", "Südkorea", "^KS11"),
]

ROHSTOFFE = [
    # id, Name, Gruppe, Einheit, Yahoo-Symbol (mehrere = Ausweichsymbole)
    ("brent", "Rohöl Brent", "Energie", "USD/Fass", ["BZ=F"]),
    ("rbob", "Benzin RBOB", "Energie", "USD/Gallone", ["RB=F"]),
    ("ttf", "Erdgas TTF", "Energie", "EUR/MWh", ["TTF=F"]),
    ("ho", "Heizöl / Diesel (HO)", "Energie", "USD/Gallone", ["HO=F"]),
    ("gold", "Gold", "Edelmetalle", "USD/Unze", ["GC=F"]),
    ("silber", "Silber", "Edelmetalle", "USD/Unze", ["SI=F"]),
    ("platin", "Platin", "Edelmetalle", "USD/Unze", ["PL=F"]),
    ("palladium", "Palladium", "Edelmetalle", "USD/Unze", ["PA=F"]),
    ("uran", "Uran (Sprott Physical Uranium Trust)", "Energie", "USD/Anteil", ["SRUUF"]),
    ("kupfer", "Kupfer", "Industriemetalle", "USD/lb", ["HG=F"]),
    ("alu", "Aluminium", "Industriemetalle", "USD/t", ["ALI=F"]),
    ("weizen", "Weizen", "Agrar", "US-Cent/Bushel", ["ZW=F"]),
    ("mais", "Mais", "Agrar", "US-Cent/Bushel", ["ZC=F"]),
    ("soja", "Sojabohnen", "Agrar", "US-Cent/Bushel", ["ZS=F"]),
    ("kaffee", "Kaffee", "Agrar", "US-Cent/lb", ["KC=F"]),
    ("zucker", "Zucker", "Agrar", "US-Cent/lb", ["SB=F"]),
]

# Vollständige Mitgliederlisten (Stand 2025/26), um den Anteil der fünf grössten Titel am Börsenwert des Index
# zu berechnen. Für die grossen Indizes mit Hunderten bis Tausenden Titeln gibt es keine freie Liste.
MITGLIEDER = {
    "smi": ["NESN.SW", "RO.SW", "NOVN.SW", "UBSG.SW", "ZURN.SW", "ABBN.SW", "CFR.SW", "HOLN.SW", "SIKA.SW", "LONN.SW",
            "ALC.SW", "GIVN.SW", "SREN.SW", "PGHN.SW", "SCMN.SW", "GEBN.SW", "KNIN.SW", "LOGN.SW", "SOON.SW", "SLHN.SW"],
    "dax": ["ADS.DE", "AIR.DE", "ALV.DE", "BAS.DE", "BAYN.DE", "BEI.DE", "BMW.DE", "BNR.DE", "CBK.DE", "CON.DE",
            "DB1.DE", "DBK.DE", "DHL.DE", "DTE.DE", "DTG.DE", "ENR.DE", "EOAN.DE", "FRE.DE", "G1A.DE", "G24.DE",
            "HEI.DE", "HEN3.DE", "HNR1.DE", "IFX.DE", "MBG.DE", "MRK.DE", "MTX.DE", "MUV2.DE", "P911.DE", "QIA.DE",
            "RHM.DE", "RWE.DE", "SAP.DE", "SHL.DE", "SIE.DE", "SRT3.DE", "SY1.DE", "VNA.DE", "VOW3.DE", "ZAL.DE"],
    "ibex": ["ACS.MC", "ACX.MC", "AENA.MC", "AMS.MC", "ANA.MC", "ANE.MC", "BBVA.MC", "BKT.MC", "CABK.MC", "CLNX.MC",
             "COL.MC", "ELE.MC", "ENG.MC", "FDR.MC", "FER.MC", "GRF.MC", "IAG.MC", "IBE.MC", "IDR.MC", "ITX.MC",
             "LOG.MC", "MAP.MC", "MRL.MC", "MTS.MC", "NTGY.MC", "PUIG.MC", "RED.MC", "REP.MC", "ROVI.MC", "SAB.MC",
             "SAN.MC", "SCYR.MC", "SLR.MC", "TEF.MC", "UNI.MC"],
    "mib": ["A2A.MI", "AMP.MI", "AZM.MI", "BAMI.MI", "BMED.MI", "BMPS.MI", "BPE.MI", "BZU.MI", "CPR.MI", "DIA.MI",
            "ENEL.MI", "ENI.MI", "ERG.MI", "FBK.MI", "G.MI", "HER.MI", "IG.MI", "INW.MI", "IP.MI", "ISP.MI",
            "IVG.MI", "LDO.MI", "MB.MI", "MONC.MI", "NEXI.MI", "PIRC.MI", "PRY.MI", "PST.MI", "RACE.MI", "REC.MI",
            "SPM.MI", "SRG.MI", "STLAM.MI", "STMMI.MI", "TEN.MI", "TIT.MI", "TRN.MI", "UCG.MI", "UNI.MI", "AVIO.MI"],
}

# Anlageklassen von oben. Ausgangswerte (Mrd. USD) aus den breitesten frei verfügbaren Schätzungen,
# seit ihrem Stichtag mit einem Stellvertreter fortgeschrieben (Wert heute = Ausgangswert × Kursveränderung seither).
#   Aktien, Anleihen: SIFMA Capital Markets Fact Book 2026 (Stand Ende 2025)
#   Immobilien: Savills, Total value of global real estate (Stand Anfang 2025; nur jährlich, deshalb nicht fortgeschrieben)
#   Gold: World Gold Council, oberirdischer Bestand Ende 2025 (220 700 t) × aktueller Goldpreis
#   Silber: CPM Group, oberirdischer Bestand rund 1,6 Mio. t (Stand 2018; Schätzungen reichen von 0,6 bis 2,5 Mio. t)
#   Krypto: CoinMarketCap, gesamte Marktkapitalisierung
UNZEN_JE_TONNE = 32150.7466
# Savills-Jahreswerte in Bio. USD (Berichte 2021 bis 2025); 2023 aus dem Rückgang 2024 (−0,5 %) zurückgerechnet.
IMMO_JAHRE = [("2020-12-31", 326.5), ("2021-12-31", 390.5), ("2022-12-31", 379.7), ("2023-12-31", 395.3), ("2024-12-31", 393.3)]
IMMO_J1, IMMO_J5 = -0.5, 21.3  # Savills: 2024 gegenüber 2023 und gegenüber 2019
ANLAGEKLASSEN = [
    # id, Name, Ausgangswert Mrd. USD, Stichtag, Stellvertreter, Beschreibung, Art
    ("ak-immobilien", "Immobilien", 393300, dt.date(2024, 12, 31), [], "Savills, Stand Anfang 2025", "statisch"),
    ("ak-anleihen", "Anleihen", 160700, dt.date(2025, 12, 31), ["AGG", "BNDX"], "SIFMA Ende 2025; Ø AGG und BNDX", "fort"),
    ("ak-aktien", "Aktien", 157800, dt.date(2025, 12, 31), ["ACWI"], "SIFMA Ende 2025; MSCI ACWI", "fort"),
    ("ak-gold", "Gold", 220700, None, ["GC=F"], "WGC 220 700 t × Goldpreis", "bestand"),
    ("ak-silber", "Silber", 1600000, None, ["SI=F"], "CPM Group rund 1,6 Mio. t × Silberpreis", "bestand"),
    ("ak-krypto", "Krypto", None, None, ["CMC"], "CoinMarketCap", "cmc"),
]

# Sektorgewichte des S&P GSCI 2026 (Anteil am weltweiten Produktionswert, gültig ab der Januar-Umstellung 2026)
GSCI_2026 = [
    # id, Sektor, Gewicht in %, Kacheln (bzw. Yahoo-Symbole) mit ihrem ungefähren Gewicht innerhalb des Sektors
    ("energie", "Energie", 51.78, {"brent": 0.8, "rbob": 0.1, "ho": 0.1}),
    ("agrar", "Agrar", 17.01, {"weizen": 0.25, "mais": 0.3, "soja": 0.25, "kaffee": 0.1, "zucker": 0.1}),
    ("industrie", "Industriemetalle", 12.13, {"kupfer": 0.6, "alu": 0.4}),
    ("vieh", "Vieh", 11.19, {"LE=F": 0.7, "HE=F": 0.3}),
    ("edel", "Edelmetalle", 7.89, {"gold": 0.9, "silber": 0.1}),
]

# Yahoo-Wechselkurse zur Umrechnung der Börsenwerte in US-Dollar
FX = {"EUR": "EURUSD=X", "CHF": "CHFUSD=X", "JPY": "JPYUSD=X", "CNY": "CNYUSD=X", "KRW": "KRWUSD=X"}

KRYPTO = [
    # id, Name, Yahoo-Symbol
    ("btc", "Bitcoin", "BTC-USD"),
    ("eth", "Ethereum", "ETH-USD"),
    ("sol", "Solana", "SOL-USD"),
    ("zec", "Zcash", "ZEC-USD"),
    ("hype", "Hyperliquid", "HYPE32196-USD"),
    ("near", "NEAR Protocol", "NEAR-USD"),
    ("tao", "Bittensor", "TAO22974-USD"),
]

# Kandidaten je Index; gezeigt werden die fünf mit der höchsten Börsenkapitalisierung.
# Die Reihenfolge entspricht dem Stand vom 29.10.2026 und gilt, falls Yahoo keine Börsenwerte liefert.
US_GROSS = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "BRK-B", "JPM", "LLY", "WMT", "ORCL", "V"]
NASDAQ = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "NFLX", "COST", "PLTR", "AMD", "ASML"]
KANDIDATEN = {
    "spx": [s for s in US_GROSS if s != "V"] + ["V"],
    # Russell 2000: grösste Positionen der Russell-2000-ETFs (iShares, Vanguard, Xtrackers; Stand Februar bis Mai 2026)
    # plus weitere grosse Nebenwerte. Nach der jährlichen Neuzusammensetzung im Juni prüfen.
    "rut": ["BE", "CRDO", "FN", "GH", "CDE", "IONQ", "HIMS", "KTOS", "ASTS", "OKLO", "HL", "AEIS", "SATS", "RGTI"],
    "ixic": NASDAQ,
    "dax": ["SAP.DE", "SIE.DE", "AIR.DE", "DTE.DE", "ENR.DE", "ALV.DE", "RHM.DE", "MUV2.DE", "DBK.DE", "MBG.DE", "IFX.DE"],
    "ibex": ["ITX.MC", "SAN.MC", "IBE.MC", "BBVA.MC", "CABK.MC", "TEF.MC", "AMS.MC", "FER.MC", "AENA.MC"],
    "mib": ["UCG.MI", "ISP.MI", "ENEL.MI", "ENI.MI", "G.MI", "RACE.MI", "STLAM.MI", "PRY.MI", "LDO.MI"],
    "smi": ["RO.SW", "NOVN.SW", "NESN.SW", "ABBN.SW", "UBSG.SW", "ZURN.SW", "CFR.SW", "HOLN.SW"],
    "n225": ["8306.T", "7203.T", "9984.T", "8316.T", "6758.T", "6501.T", "9983.T", "8035.T", "6861.T", "7974.T"],
    "shcomp": ["601939.SS", "601398.SS", "601857.SS", "601988.SS", "600941.SS", "601288.SS", "600519.SS", "600036.SS"],
    "kospi": ["005930.KS", "000660.KS", "373220.KS", "005380.KS", "207940.KS", "012450.KS", "105560.KS", "068270.KS"],
}
TOP_N = 5

LAENDER = [
    # Kürzel, Name, Abfragefunktion (weiter unten definiert)
    ("US", "USA", "renditen_us"),
    ("DE", "Deutschland", "renditen_de"),
    ("GB", "Grossbritannien", "renditen_gb"),
    ("JP", "Japan", "renditen_jp"),
    ("CA", "Kanada", "renditen_ca"),
    ("AU", "Australien", "renditen_au"),
    ("CH", "Schweiz", "renditen_ch"),
    ("CN", "China", "renditen_cn"),
]

# Top News zuerst, in der Reihenfolge der Redaktion; die Märkte-Meldungen füllen nur auf, wenn der erste Feed zu wenig liefert.
NEWS_FEEDS = [
    # Quelle, Adressen. CNBC: Top News (USA und Weltmärkte, Reihenfolge der Redaktion).
    # Investing.com: Wirtschaft und Konjunkturdaten (globale Makro-Meldungen, viele von Reuters), frei lesbar,
    # beide Feeds zusammengeführt und nach Zeit sortiert. Die zwei Quellen werden abwechselnd gemischt.
    ("CNBC", ["https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"]),
    ("Investing.com", ["https://www.investing.com/rss/news_14.rss", "https://www.investing.com/rss/news_95.rss"]),
]
NEWS_ANZAHL = 20

# ---------------------------------------------------------------- Netz


def hole(url, versuche=3, text=False):
    letzter = None
    for i in range(versuche):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            # Cookies nur für Yahoo (Crumb); andere Quellen antworten mit Cookies teils anders.
            oeffner = OPENER if "yahoo.com" in url else urllib.request.build_opener()
            with oeffner.open(req, timeout=40) as r:
                daten = r.read()
            return daten.decode("utf-8", "replace") if text else json.loads(daten)
        except Exception as e:  # noqa: BLE001
            letzter = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{url}: {letzter}")


# ---------------------------------------------------------------- Rechnen


def schluss_vor(reihe, stichtag):
    """Letzter Schlusskurs am oder vor dem Stichtag (reihe: Liste (datum, wert), aufsteigend)."""
    kandidat = None
    for d, w in reihe:
        if d <= stichtag:
            kandidat = w
        else:
            break
    return kandidat


def veraenderungen(reihe, letzt, vortag, als_differenz=False):
    """Veränderung 1T, YTD, 1J, 5J, 10J; relativ in Prozent oder (Zinsen) als Differenz."""
    if not reihe or letzt is None:
        return {"t1": None, "ytd": None, "j1": None, "j5": None, "j10": None}
    heute = reihe[-1][0]
    erster = reihe[0][0]
    basis = {
        "t1": vortag,
        "ytd": schluss_vor(reihe, dt.date(heute.year - 1, 12, 31)),
        "j1": schluss_vor(reihe, heute - dt.timedelta(days=365)),
        "j5": schluss_vor(reihe, heute - dt.timedelta(days=365 * 5 + 1)),
        "j10": schluss_vor(reihe, heute - dt.timedelta(days=3652)),
    }
    # Eine zu kurze Historie darf keine Langfristwerte vortäuschen.
    if erster > heute - dt.timedelta(days=3652 - 10):
        basis["j10"] = None
    if erster > heute - dt.timedelta(days=365 * 5 - 10):
        basis["j5"] = None
    if erster > heute - dt.timedelta(days=360):
        basis["j1"] = None
    aus = {}
    for k, b in basis.items():
        if b is None or (not als_differenz and b == 0):
            aus[k] = None
        elif als_differenz:
            aus[k] = round((letzt - b) * 100, 1) + 0.0  # Basispunkte; + 0.0 vermeidet „−0“
        else:
            aus[k] = round((letzt / b - 1) * 100, 2)
    return aus


def wochenreihe(reihe, tage=372):
    """Ein Wert je Kalenderwoche (jeweils der letzte), für die Kleingrafik."""
    if not reihe:
        return []
    grenze = reihe[-1][0] - dt.timedelta(days=tage)
    wochen = {}
    for d, w in reihe:
        if d >= grenze:
            wochen[d.isocalendar()[:2]] = (d, w)
    punkte = sorted(wochen.values())
    if punkte[-1][0] != reihe[-1][0]:
        punkte.append(reihe[-1])
    return punkte


# ---------------------------------------------------------------- Yahoo


def yahoo_reihe(symbol):
    start = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3652 + 40)).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
           f"?period1={start}&period2={int(time.time()) + 86400}&interval=1d")
    j = hole(url)["chart"]["result"][0]
    meta = j["meta"]
    tz = dt.timezone(dt.timedelta(seconds=meta.get("gmtoffset", 0)))
    zeiten = j.get("timestamp") or []
    werte = j["indicators"]["quote"][0].get("close") or []
    reihe = []
    for t, w in zip(zeiten, werte):
        if w is not None:
            reihe.append((dt.datetime.fromtimestamp(t, tz).date(), float(w)))
    letzt = meta.get("regularMarketPrice")
    if letzt is None and reihe:
        letzt = reihe[-1][1]
    marktzeit = meta.get("regularMarketTime")
    if reihe and letzt is not None and marktzeit:
        tag = dt.datetime.fromtimestamp(marktzeit, tz).date()
        if reihe[-1][0] == tag:
            reihe[-1] = (tag, float(letzt))
        elif reihe[-1][0] < tag:
            reihe.append((tag, float(letzt)))
    vortag = reihe[-2][1] if len(reihe) >= 2 else None
    stand = dt.datetime.fromtimestamp(marktzeit, dt.timezone.utc).isoformat() if marktzeit else None
    return {
        "reihe": reihe,
        "letzt": letzt,
        "vortag": vortag,
        "waehrung": meta.get("currency"),
        "stand": stand,
        "name": meta.get("longName") or meta.get("shortName"),
    }


def yahoo_crumb():
    try:
        try:
            OPENER.open(urllib.request.Request("https://fc.yahoo.com", headers={"User-Agent": UA}), timeout=15)
        except Exception:  # noqa: BLE001  (antwortet mit 404, setzt aber das Cookie)
            pass
        for warte in (0, 10, 30, 60):
            time.sleep(warte)
            try:
                return hole("https://query2.finance.yahoo.com/v1/test/getcrumb", versuche=1, text=True).strip()
            except Exception as e:  # noqa: BLE001
                letzter = e
        raise letzter
    except Exception as e:  # noqa: BLE001
        FEHLER.append(f"Crumb: {e}")
        return None


def yahoo_kapitalisierung(symbole):
    """Börsenwert und Name je Symbol; leer, wenn Yahoo die Abfrage verweigert."""
    crumb = yahoo_crumb()
    if not crumb:
        return {}
    aus = {}
    liste = sorted(set(symbole))
    for i in range(0, len(liste), 40):
        teil = ",".join(liste[i:i + 40])
        url = (f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={urllib.parse.quote(teil)}"
               f"&crumb={urllib.parse.quote(crumb)}")
        try:
            for q in hole(url)["quoteResponse"]["result"]:
                aus[q["symbol"]] = {"cap": q.get("marketCap"), "name": q.get("longName") or q.get("shortName")}
        except Exception as e:  # noqa: BLE001
            FEHLER.append(f"Kapitalisierung: {e}")
    return aus


def sicher(fn, *args):
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001
        FEHLER.append(f"{args[0] if args else fn.__name__}: {e}")
        return None


# ---------------------------------------------------------------- Renditen (amtliche Quellen)
# Jede Funktion liefert {laufzeit_in_jahren: [(datum, prozent), ...]} aufsteigend sortiert.


def _ab():
    return dt.date.today() - dt.timedelta(days=3652 + 75)  # 10 Jahre plus Vorlauf für monatlich veröffentlichte Reihen (SNB)


def renditen_us():
    """USA: US-Finanzministerium (Daily Treasury Par Yield Curve); Rückfall Yahoo (5, 10, 30 Jahre)."""
    spalten = {1: "1 Yr", 5: "5 Yr", 10: "10 Yr", 30: "30 Yr"}
    aus = {lz: [] for lz in spalten}
    try:
        for jahr in range(_ab().year, dt.date.today().year + 1):
            url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
                   f"daily-treasury-rates.csv/{jahr}/all?type=daily_treasury_yield_curve"
                   f"&field_tdr_date_value={jahr}&page&_format=csv")
            zeilen = hole(url, text=True).splitlines()
            kopf = [k.strip().strip('"') for k in zeilen[0].split(",")]
            for z in zeilen[1:]:
                t = [x.strip().strip('"') for x in z.split(",")]
                try:
                    d = dt.datetime.strptime(t[0], "%m/%d/%Y").date()
                except ValueError:
                    continue
                for lz, sp in spalten.items():
                    try:
                        aus[lz].append((d, float(t[kopf.index(sp)])))
                    except (ValueError, IndexError):
                        pass
        aus = {lz: sorted(r) for lz, r in aus.items() if r}
        if len(aus) == len(spalten):
            return aus
        raise RuntimeError("Treasury: unvollständige Antwort")
    except Exception as e:  # noqa: BLE001
        FEHLER.append(f"US-Treasury, Rückfall auf Yahoo: {e}")
    aus = {}
    for lz, sym in ((5, "^FVX"), (10, "^TNX"), (30, "^TYX")):
        d = sicher(yahoo_reihe, sym)
        if d and d["reihe"]:
            aus[lz] = d["reihe"]
    return aus


def renditen_de():
    """Deutschland: Bundesbank, aus der Zinsstruktur abgeleitete Renditen für Bundeswertpapiere."""
    aus = {}
    for lz in (1, 5, 10, 30):
        url = (f"https://api.statistiken.bundesbank.de/rest/data/BBSIS/"
               f"D.I.ZAR.ZI.EUR.S1311.B.A604.R{lz:02d}XX.R.A.A._Z._Z.A?format=csv&startPeriod={_ab().isoformat()}")
        reihe = []
        for z in hole(url, text=True).splitlines():
            t = z.split(";")
            if len(t) >= 2 and len(t[0]) == 10 and t[0][4] == "-" and t[1].strip():
                try:
                    reihe.append((dt.date.fromisoformat(t[0]), float(t[1].replace(",", "."))))
                except ValueError:
                    pass
        if reihe:
            aus[lz] = sorted(reihe)
    return aus


def renditen_jp():
    """Japan: Finanzministerium (MOF), JGB-Renditen; Historie bis Vormonat plus laufender Monat."""
    basis = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/"
    reihen = {1: {}, 5: {}, 10: {}, 30: {}}
    for url in (basis + "historical/jgbcme_all.csv", basis + "jgbcme.csv"):
        zeilen = hole(url, text=True).splitlines()
        kopf = None
        for z in zeilen:
            t = [x.strip() for x in z.split(",")]
            if t and t[0] == "Date":
                kopf = t
                continue
            if not kopf or not t[0] or "/" not in t[0]:
                continue
            try:
                j, m, tg = (int(x) for x in t[0].split("/"))
                d = dt.date(j, m, tg)
            except ValueError:
                continue
            if d < _ab():
                continue
            for lz in reihen:
                i = kopf.index(f"{lz}Y")
                try:
                    reihen[lz][d] = float(t[i])
                except (ValueError, IndexError):
                    pass
    return {lz: sorted(r.items()) for lz, r in reihen.items() if r}


def renditen_ca():
    """Kanada: Bank of Canada (Valet); 1 Jahr = Schatzwechsel, 30 Jahre = langfristige Referenzanleihe."""
    serien = {1: "TB.CDN.1Y.MID", 5: "BD.CDN.5YR.DQ.YLD", 10: "BD.CDN.10YR.DQ.YLD", 30: "BD.CDN.LONG.DQ.YLD"}
    url = (f"https://www.bankofcanada.ca/valet/observations/{','.join(serien.values())}/json"
           f"?start_date={_ab().isoformat()}")
    aus = {lz: [] for lz in serien}
    for o in hole(url)["observations"]:
        d = dt.date.fromisoformat(o["d"])
        for lz, sid in serien.items():
            w = (o.get(sid) or {}).get("v")
            if w not in (None, ""):
                aus[lz].append((d, float(w)))
    return {lz: sorted(r) for lz, r in aus.items() if r}


def renditen_gb():
    """Grossbritannien: Bank of England, nominale Par-Renditen (5, 10 und 20 Jahre)."""
    serien = {5: "IUDSNPY", 10: "IUDMNPY", 20: "IUDLNPY"}
    aus = {}
    for lz, sid in serien.items():  # einzeln: mehrere Reihen über 5 Jahre lehnt die Datenbank ab
        url = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes"
               f"&Datefrom={_ab().strftime('%d/%b/%Y')}&Dateto=now&SeriesCodes={sid}"
               "&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")
        for warte in (3, 10, 30, 60):  # die Datenbank antwortet auf rasche Folgeabfragen mit einer HTML-Seite
            time.sleep(warte)
            zeilen = hole(url, text=True).splitlines()
            if zeilen and zeilen[0].startswith("DATE"):
                break
        else:
            raise RuntimeError(f"Bank of England {sid}: keine CSV-Antwort")
        reihe = []
        for z in zeilen[1:]:
            t = [x.strip() for x in z.split(",")]
            try:
                reihe.append((dt.datetime.strptime(t[0], "%d %b %Y").date(), float(t[1])))
            except (ValueError, IndexError):
                pass
        aus[lz] = reihe
    return {lz: sorted(r) for lz, r in aus.items() if r}


def renditen_au():
    """Australien: Reserve Bank of Australia, Tabelle F2 (interpolierte Renditen, 5 und 10 Jahre)."""
    zeilen = hole("https://www.rba.gov.au/statistics/tables/csv/f2-data.csv", text=True).lstrip("\ufeff").splitlines()
    kopf = next(z.split(",") for z in zeilen if z.startswith("Series ID"))
    spalten = {5: kopf.index("FCMYGBAG5D"), 10: kopf.index("FCMYGBAG10D")}
    aus = {lz: [] for lz in spalten}
    for z in zeilen:
        t = z.split(",")
        try:
            d = dt.datetime.strptime(t[0], "%d-%b-%Y").date()
        except ValueError:
            continue
        if d < _ab():
            continue
        for lz, i in spalten.items():
            try:
                aus[lz].append((d, float(t[i])))
            except (ValueError, IndexError):
                pass
    return {lz: sorted(r) for lz, r in aus.items() if r}


def renditen_ch():
    """Schweiz: SNB, Kassazinssätze der Eidgenossen (Tageswerte, monatlich veröffentlicht)."""
    url = (f"https://data.snb.ch/api/cube/rendeiduebd/data/csv/de?fromDate={_ab().isoformat()}"
           "&dimSel=D0(CHF),D1(1J,5J,10J,30J)")
    aus = {}
    for z in hole(url, text=True).splitlines():
        t = [x.strip().strip('"') for x in z.split(";")]
        if len(t) == 4 and t[1] == "CHF" and t[3]:
            try:
                aus.setdefault(int(t[2].rstrip("J")), []).append((dt.date.fromisoformat(t[0]), float(t[3])))
            except ValueError:
                pass
    return {lz: sorted(r) for lz, r in aus.items()}


def renditen_cn():
    """China: CFETS/ChinaMoney, Zinskurve der Staatsanleihen. Die Quelle gibt nur rund den letzten Monat heraus."""
    ende = dt.date.today()
    start = ende - dt.timedelta(days=28)
    aus = {1: {}, 5: {}, 10: {}, 30: {}}
    seite, seiten = 1, 1
    while seite <= seiten:
        url = ("https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/ClsYldCurvHis?lang=CN&reference=1"
               f"&bondType=CYCC000&startDate={start.isoformat()}&endDate={ende.isoformat()}&termId=10"
               f"&pageNum={seite}&pageSize=50")  # grössere Seiten lehnt die Quelle ab
        j = hole(url)
        seiten = j["data"].get("pageTotal") or 1
        for r in j.get("records") or []:
            try:
                lz = float(r["yearTermStr"])
                if lz in aus:
                    aus[int(lz)][dt.date.fromisoformat(r["newDateValueCN"])] = float(r["maturityYieldStr"])
            except (ValueError, KeyError):
                pass
        seite += 1
        time.sleep(1)
    return {lz: sorted(r.items()) for lz, r in aus.items() if r}


def krypto_gesamt():
    """Gesamte Krypto-Marktkapitalisierung von CoinMarketCap (Tageswerte; höchstens 2200 Punkte je Abfrage)."""
    jetzt = dt.datetime.now(dt.timezone.utc)
    grenzen = [jetzt - dt.timedelta(days=3652 + 40), jetzt - dt.timedelta(days=1800), jetzt]
    punkte, dominanz = {}, None
    for von, bis in zip(grenzen, grenzen[1:]):
        url = ("https://api.coinmarketcap.com/data-api/v3/global-metrics/quotes/historical?format=chart&interval=1d"
               f"&timeStart={int(von.timestamp())}&timeEnd={int(bis.timestamp())}")
        for q in hole(url)["data"]["quotes"]:
            usd = next((x for x in q["quote"] if x.get("name") == "USD"), None)
            if usd and usd.get("totalMarketCap"):
                punkte[dt.date.fromisoformat(q["timestamp"][:10])] = float(usd["totalMarketCap"])
                dominanz = q.get("btcDominance", dominanz)
    reihe = sorted(punkte.items())
    if len(reihe) < 2:
        raise RuntimeError("CoinMarketCap: zu wenige Werte")
    return {"reihe": reihe, "letzt": reihe[-1][1], "vortag": reihe[-2][1], "waehrung": "USD",
            "stand": dt.datetime.combine(reihe[-1][0], dt.time(), dt.timezone.utc).isoformat(), "dominanz": dominanz}


# ---------------------------------------------------------------- Nachrichten


def _rss_zeit(text):
    """RSS-Zeit (RFC 822 oder „JJJJ-MM-TT hh:mm:ss“ in UTC) als ISO-Zeit."""
    if not text:
        return None
    try:
        return email.utils.parsedate_to_datetime(text).astimezone(dt.timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
    try:
        return dt.datetime.strptime(text.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).isoformat()
    except ValueError:
        return None


def nachrichten():
    listen, gesehen = [], set()
    for quelle, urls in NEWS_FEEDS:
        liste = []
        for url in urls:
            try:
                wurzel = ET.fromstring(hole(url, text=True))
            except Exception as e:  # noqa: BLE001
                FEHLER.append(f"News {quelle}: {e}")
                continue
            for item in wurzel.iter("item"):
                titel = " ".join((item.findtext("title") or "").split())
                link = (item.findtext("link") or "").strip()
                if not titel or not link.startswith("https://") or titel.lower() in gesehen:
                    continue
                gesehen.add(titel.lower())
                liste.append({"titel": titel, "quelle": quelle, "link": link, "zeit": _rss_zeit(item.findtext("pubDate"))})
        if len(urls) > 1:  # mehrere Feeds einer Quelle: neueste zuerst
            liste.sort(key=lambda n: n["zeit"] or "", reverse=True)
        listen.append(liste)
    # abwechselnd mischen: 1. CNBC, 1. Investing.com, 2. CNBC, ...
    aus = []
    for i in range(max((len(l) for l in listen), default=0)):
        for liste in listen:
            if i < len(liste):
                aus.append(liste[i])
    aus = aus[:NEWS_ANZAHL]
    for i, n in enumerate(aus):
        n["id"] = f"n{i + 1}"
    return aus


def meistgehandelt(n=10):
    """Meistgehandelte US-Aktien nach gehandeltem Wert (Kurs × Volumen) des letzten bzw. laufenden Handelstags.

    Kandidaten: Yahoos Liste der 100 umsatzstärksten Titel nach Stückzahl plus die grössten US-Werte,
    weil teure Aktien mit wenig Stücken viel Wert umsetzen können. Für die Spitzengruppe wird der
    Durchschnitt der letzten 30 abgeschlossenen Handelstage aus der Kurshistorie berechnet.
    """
    j = hole("https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=most_actives&count=100")
    kandidaten = {}
    for q in j["finance"]["result"][0]["quotes"]:
        if q.get("quoteType") not in (None, "EQUITY") or not q.get("regularMarketPrice") or not q.get("regularMarketVolume"):
            continue
        kandidaten[q["symbol"]] = {"name": q.get("longName") or q.get("shortName") or q["symbol"],
                                   "kurs": q["regularMarketPrice"], "volumen": q["regularMarketVolume"],
                                   "t1": q.get("regularMarketChangePercent")}

    def verlauf_volumen(symbol):
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=2y&interval=1d"
        r = hole(url)["chart"]["result"][0]
        meta = r["meta"]
        ind = r["indicators"]["quote"][0]
        tage = [(t, c, v) for t, c, v in zip(r.get("timestamp") or [], ind.get("close") or [], ind.get("volume") or [])
                if c is not None and v]
        return meta, tage

    # grösste US-Werte ergänzen, falls sie nicht schon in der Liste stehen
    for s in US_GROSS:
        if s in kandidaten:
            continue
        try:
            meta, tage = verlauf_volumen(s)
            if tage:
                vortag = tage[-2][1] if len(tage) > 1 else None
                kandidaten[s] = {"name": meta.get("longName") or meta.get("shortName") or s,
                                 "kurs": meta.get("regularMarketPrice") or tage[-1][1], "volumen": tage[-1][2],
                                 "t1": (tage[-1][1] / vortag - 1) * 100 if vortag else None}
        except Exception as e:  # noqa: BLE001
            FEHLER.append(f"Meistgehandelt {s}: {e}")
    spitze = sorted(kandidaten.items(), key=lambda kv: -kv[1]["kurs"] * kv[1]["volumen"])[:n]
    aus = []
    for rang, (s, k) in enumerate(spitze, 1):
        schnitt, perioden = None, {}
        try:
            _, tage = verlauf_volumen(s)
            abgeschlossen = tage[:-1]  # der letzte Tag kann noch laufen
            letzte = [v for _, _, v in abgeschlossen[-30:]]
            schnitt = sum(letzte) / len(letzte) if letzte else None
            # Renditen über 1 Woche bis 1 Jahr, gemessen am letzten Schlusskurs
            reihe = [(dt.datetime.fromtimestamp(t, dt.timezone.utc).date(), c) for t, c, _ in tage]
            heute, letzt = reihe[-1]
            for feld, tage_zurueck in (("w1", 7), ("m1", 30), ("m3", 91), ("m6", 182), ("j1", 365)):
                alt = schluss_vor(reihe, heute - dt.timedelta(days=tage_zurueck))
                perioden[feld] = round((letzt / alt - 1) * 100, 2) if alt and reihe[0][0] <= heute - dt.timedelta(days=tage_zurueck - 4) else None
        except Exception as e:  # noqa: BLE001
            FEHLER.append(f"Meistgehandelt {s} Verlauf: {e}")
        aus.append({"key": s, "rang": rang, "symbol": s, "name": " ".join(k["name"].split()),
                    "kurs": round(k["kurs"], 2), "t1": round(k["t1"], 2) if k["t1"] is not None else None,
                    "volumen": int(k["volumen"]), "umsatz": round(k["kurs"] * k["volumen"]),
                    "schnitt30": round(schnitt) if schnitt else None,
                    "vol_rel": round((k["volumen"] / schnitt - 1) * 100, 1) if schnitt else None, **perioden})
    return aus


def krypto_gewinner(n=10, aus_top=50):
    """Die n Kryptowährungen mit der besten 12-Monats-Entwicklung unter den grössten nach Marktkapitalisierung.

    Quelle: CoinMarketCap-Rangliste. Berücksichtigt werden nur Coins, die seit mindestens einem Jahr
    gelistet sind (jüngere haben keine echte 12-Monats-Rendite); Stablecoins, tokenisiertes Gold und
    verpackte Coins sind ausgenommen.
    """
    url = ("https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listing?start=1"
           f"&limit={aus_top}&sortBy=market_cap&sortType=desc&convert=USD&cryptoType=all&tagType=all")
    grenze = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365)).isoformat()
    liste = []
    for c in hole(url)["data"]["cryptoCurrencyList"]:
        q = next((x for x in c.get("quotes", []) if x.get("name") == "USD"), (c.get("quotes") or [{}])[0])
        if q.get("percentChange1y") is None or (c.get("dateAdded") or "9999") > grenze:
            continue
        # Stablecoins, tokenisiertes Gold und verpackte Coins bilden nur einen anderen Wert nach
        tags = c.get("tags") or []
        if any(t == "stablecoin" or t.startswith("tokenized-") or "wrapped" in t for t in tags):
            continue
        liste.append({"key": c["symbol"] + "-" + str(c["id"]), "rang_mc": c.get("cmcRank"), "symbol": c["symbol"],
                      "link": f"https://coinmarketcap.com/currencies/{c['slug']}/" if c.get("slug") else None,
                      "name": c["name"], "kurs": q.get("price"), "marktkap": q.get("marketCap"),
                      "j1": round(q["percentChange1y"], 2),
                      "ytd": round(q["ytdPriceChangePercentage"], 2) if q.get("ytdPriceChangePercentage") is not None else None,
                      "m1": round(q["percentChange30d"], 2) if q.get("percentChange30d") is not None else None,
                      "w1": round(q["percentChange7d"], 2) if q.get("percentChange7d") is not None else None,
                      "t1": round(q["percentChange24h"], 2) if q.get("percentChange24h") is not None else None})
    liste.sort(key=lambda r: -r["j1"])
    for i, r in enumerate(liste[:n], 1):
        r["rang"] = i
    return liste[:n]


# Makro: IWF World Economic Outlook (neue SDMX-Schnittstelle; die alte DataMapper-Adresse sperrt Rechenzentren).
MAKRO_LAENDER = [
    # Region, IWF-Code, Name
    ("Nordamerika", "USA", "USA"), ("Nordamerika", "CAN", "Kanada"), ("Nordamerika", "MEX", "Mexiko"),
    ("Europa", "DEU", "Deutschland"), ("Europa", "GBR", "Grossbritannien"), ("Europa", "FRA", "Frankreich"),
    ("Europa", "ITA", "Italien"), ("Europa", "ESP", "Spanien"), ("Europa", "NLD", "Niederlande"),
    ("Europa", "CHE", "Schweiz"), ("Europa", "POL", "Polen"),
    ("Asien", "CHN", "China"), ("Asien", "JPN", "Japan"), ("Asien", "IND", "Indien"), ("Asien", "KOR", "Südkorea"),
    ("Asien", "IDN", "Indonesien"), ("Asien", "TWN", "Taiwan"),
    # übrige G20-Staaten, damit alle G20-Länder vertreten sind
    ("Weitere G20", "RUS", "Russland"), ("Weitere G20", "BRA", "Brasilien"), ("Weitere G20", "AUS", "Australien"),
    ("Weitere G20", "TUR", "Türkei"), ("Weitere G20", "SAU", "Saudi-Arabien"), ("Weitere G20", "ARG", "Argentinien"),
    ("Weitere G20", "ZAF", "Südafrika"),
]
# IWF-Gesamtwert, der in der Region Europa zuoberst steht (G001 Welt, G110/G200 nur für die Weltschuldenquote)
MAKRO_GRUPPEN = [("G163", "Eurozone")]
MAKRO_INDIKATOREN = ["NGDPD", "NGDP_RPCH", "PCPIPCH", "GGXWDG_NGDP", "NGDPDPC", "LUR", "LP"]
# Zeitreihen für den Chart: Kennzahl -> Bezeichnung; ab dem Jahr MAKRO_VERLAUF_AB bis zum letzten Prognosejahr
MAKRO_VERLAUF = {"GGXWDG_NGDP": "Schulden / BIP", "PCPIPCH": "Inflation", "NGDP_RPCH": "Reales Wachstum", "LUR": "Arbeitslosigkeit"}
MAKRO_VERLAUF_AB = 2000


def makro():
    """BIP, Wachstum, Inflation und Staatsschulden der grössten Volkswirtschaften (IWF WEO, laufendes Jahr = Schätzung).

    Gibt (Tabelle, Zeitreihen) zurück; die Zeitreihen speisen den Makro-Chart."""
    laender = "+".join([c for _, c, _ in MAKRO_LAENDER] + ["G001", "G110", "G200"] + [c for c, _ in MAKRO_GRUPPEN])
    url = (f"https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/+/{laender}."
           f"{'+'.join(MAKRO_INDIKATOREN)}.A?dimensionAtObservation=TIME_PERIOD")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.build_opener().open(req, timeout=60) as r:
        d = json.load(r)
    dims = d["data"]["structures"][0]["dimensions"]
    werte_dim = {x["id"]: [v.get("id") or v.get("value") for v in x["values"]] for x in dims["series"]}
    jahre = [v["value"] for v in [x for x in dims["observation"] if x["id"] == "TIME_PERIOD"][0]["values"]]
    daten = {}  # (land, indikator) -> {jahr: wert}
    for schluessel, serie in d["data"]["dataSets"][0]["series"].items():
        i_land, i_ind, _ = (int(x) for x in schluessel.split(":"))
        land, ind = werte_dim["COUNTRY"][i_land], werte_dim["INDICATOR"][i_ind]
        daten[(land, ind)] = {jahre[int(t)]: float(o[0]) for t, o in serie.get("observations", {}).items()
                              if o and o[0] not in (None, "")}
    jahr = str(dt.date.today().year)
    vor5 = str(dt.date.today().year - 5)

    def weltquote(j):
        """Schuldenquote der Welt: BIP-gewichtetes Mittel aus Industrie- und Schwellenländern (der IWF weist sie hier nicht aus)."""
        teile = [(daten.get((g, "NGDPD"), {}).get(j), daten.get((g, "GGXWDG_NGDP"), {}).get(j)) for g in ("G110", "G200")]
        if any(b is None or q is None for b, q in teile):
            return None
        return sum(b * q for b, q in teile) / sum(b for b, _ in teile)

    welt_bip = daten.get(("G001", "NGDPD"), {}).get(jahr)

    def weltbevoelkerung():
        """Summe der Bevölkerung (LP, in Personen) aller Länder im laufenden Jahr; der IWF weist sie für die Welt nicht aus."""
        u = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/+/*.LP.A"
             "?dimensionAtObservation=TIME_PERIOD")
        rq = urllib.request.Request(u, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.build_opener().open(rq, timeout=90) as antwort:
            dd = json.load(antwort)
        dm = dd["data"]["structures"][0]["dimensions"]
        laender = [v.get("id") for v in [x for x in dm["series"] if x["id"] == "COUNTRY"][0]["values"]]
        js = [v["value"] for v in [x for x in dm["observation"] if x["id"] == "TIME_PERIOD"][0]["values"]]
        summe = 0.0
        for k, serie in dd["data"]["dataSets"][0]["series"].items():
            land = laender[int(k.split(":")[0])]
            if land.startswith("G") and land[1:].isdigit() or land.startswith("GX"):
                continue  # Ländergruppen nicht doppelt zählen
            for t, o in serie.get("observations", {}).items():
                if js[int(t)] == jahr and o and o[0] not in (None, ""):
                    summe += float(o[0])
        return summe or None
    aus = []
    if welt_bip:
        wq, wq5 = weltquote(jahr), weltquote(vor5)
        g = lambda ind, j=jahr: daten.get(("G001", ind), {}).get(j)  # noqa: E731
        aus.append({"key": "WELT", "region": "Welt", "land": "Welt", "jahr": jahr, "bip": round(welt_bip),
                    "anteil_welt": 100.0,
                    "wachstum": round(g("NGDP_RPCH"), 2) if g("NGDP_RPCH") is not None else None,
                    "inflation": round(g("PCPIPCH"), 2) if g("PCPIPCH") is not None else None,
                    "inflation_vj": round(g("PCPIPCH", str(int(jahr) - 1)), 2) if g("PCPIPCH", str(int(jahr) - 1)) is not None else None,
                    "schuldenquote": round(wq, 1) if wq else None,
                    "schulden": round(welt_bip * wq / 100) if wq else None,
                    "schuldenquote_d5": round(wq - wq5, 1) if wq and wq5 else None,
                    "bip_kopf": None})
        bevoelkerung = sicher(weltbevoelkerung)
        if bevoelkerung:  # BIP pro Kopf der Welt = Welt-BIP / Summe der Bevölkerung aller Länder
            aus[-1]["bip_kopf"] = round(welt_bip / bevoelkerung)
            aus[-1]["bevoelkerung"] = round(bevoelkerung)
    zeilen = []
    for region, code, name in MAKRO_LAENDER:
        if code == "DEU":  # Eurozone vor den europäischen Ländern
            zeilen += [("Europa", c, n, True) for c, n in MAKRO_GRUPPEN]
        zeilen.append((region, code, name, False))
    for region, code, name, gruppe in zeilen:
        w = lambda ind, j=jahr: daten.get((code, ind), {}).get(j)  # noqa: E731
        bip, quote = w("NGDPD"), w("GGXWDG_NGDP")
        aus.append({"key": code, "region": region, "land": name, "jahr": jahr, "gruppe": gruppe,
                    "bip": round(bip) if bip else None,
                    "anteil_welt": round(bip / welt_bip * 100, 2) if bip and welt_bip else None,
                    "wachstum": round(w("NGDP_RPCH"), 2) if w("NGDP_RPCH") is not None else None,
                    "inflation": round(w("PCPIPCH"), 2) if w("PCPIPCH") is not None else None,
                    "inflation_vj": round(w("PCPIPCH", str(int(jahr) - 1)), 2) if w("PCPIPCH", str(int(jahr) - 1)) is not None else None,
                    "schuldenquote": round(quote, 1) if quote is not None else None,
                    "schulden": round(bip * quote / 100) if bip and quote is not None else None,
                    "schuldenquote_d5": round(quote - w("GGXWDG_NGDP", vor5), 1)
                    if quote is not None and w("GGXWDG_NGDP", vor5) is not None else None,
                    "bip_kopf": round(w("NGDPDPC")) if w("NGDPDPC") else None})
    verlauf = []
    for code, name in [(c, n) for _, c, n in MAKRO_LAENDER] + MAKRO_GRUPPEN:
        for ind in MAKRO_VERLAUF:
            for j, wert in sorted(daten.get((code, ind), {}).items()):
                if int(j) >= MAKRO_VERLAUF_AB:
                    verlauf.append({"key": f"{code}-{ind}-{j}", "code": code, "land": name, "kennzahl": ind,
                                    "jahr": int(j), "wert": round(wert, 2), "prognose": int(j) >= int(jahr)})
    return aus, verlauf


# ---------------------------------------------------------------- Hauptteil


def zeile(basis, daten):
    v = veraenderungen(daten["reihe"], daten["letzt"], daten["vortag"])
    v["pa10"] = round(((1 + v["j10"] / 100) ** 0.1 - 1) * 100, 2) if v["j10"] is not None and v["j10"] > -100 else None
    v["pa5"] = round(((1 + v["j5"] / 100) ** 0.2 - 1) * 100, 2) if v["j5"] is not None and v["j5"] > -100 else None
    return {**basis, "kurs": round(daten["letzt"], 4) if daten["letzt"] is not None else None,
            "waehrung": daten["waehrung"], "stand": daten["stand"], **v}


def vorherige_aktienzahl(pfad):
    """Aktienanzahl je Symbol aus dem letzten Lauf, um Börsenwerte zu schätzen, wenn Yahoo keine liefert."""
    try:
        with open(pfad, encoding="utf-8") as f:
            zeilen = json.load(f)["rows"]
        return ({r["symbol"]: r["aktienzahl"] for r in zeilen if r.get("aktienzahl")},
                {r["index"]: r["anteil_top5"] for r in zeilen if r.get("anteil_top5")})
    except Exception as e:  # noqa: BLE001
        FEHLER.append(f"Vorheriger Stand {pfad}: {e}")
        return {}, {}


def main(ziel, vorher=None):
    jetzt = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    werte, verlauf, aktien, zinsen = [], [], [], []

    with ThreadPoolExecutor(max_workers=3) as pool:
        idx_daten = list(pool.map(lambda r: sicher(yahoo_reihe, r[3]), INDIZES))

        def rohstoff(r):
            for s in r[4]:
                d = sicher(yahoo_reihe, s)
                if d and d["reihe"]:
                    return s, d
            return r[4][0], None
        roh_daten = list(pool.map(rohstoff, ROHSTOFFE))
        krypto_daten = list(pool.map(lambda r: sicher(yahoo_reihe, r[2]), KRYPTO))

    # Durchschnitt aller Indizes, gleich gewichtet: je Zeitraum das Mittel der Veränderungen in Lokalwährung,
    # als Linie das Mittel der auf 100 normierten Wochenschlusskurse.
    gueltig = [d for d in idx_daten if d and d["reihe"]]
    if gueltig:
        einzel = [veraenderungen(d["reihe"], d["letzt"], d["vortag"]) for d in gueltig]
        mittel = {}
        for k in ("t1", "ytd", "j1", "j5", "j10"):
            w = [e[k] for e in einzel if e[k] is not None]
            mittel[k] = round(sum(w) / len(w), 2) if len(w) == len(einzel) else None
        # annualisierte Rendite über 10 Jahre aus der mittleren 10-Jahres-Veränderung
        mittel["pa10"] = round(((1 + mittel["j10"] / 100) ** 0.1 - 1) * 100, 2) if mittel["j10"] is not None else None
        werte.append({"id": "alle", "klasse": "Aktien", "gruppe": "Indizes", "name": "Alle Indizes",
                      "region": f"Ø {len(gueltig)}, gleich gewichtet", "symbol": "", "einheit": "seit Jahresbeginn",
                      "format": "prozent", "kurs": mittel["ytd"], "waehrung": None,
                      "stand": max(d["stand"] for d in gueltig if d["stand"]), **mittel})
        wochen = [{p[0].isocalendar()[:2]: p[1] for p in wochenreihe(d["reihe"])} for d in gueltig]
        gemeinsam = sorted(set.intersection(*(set(w) for w in wochen)))
        if gemeinsam:
            erste = gemeinsam[0]
            for kw in gemeinsam:
                wert = sum(w[kw] / w[erste] * 100 for w in wochen) / len(wochen)
                montag = dt.date.fromisocalendar(kw[0], kw[1], 5)
                verlauf.append({"id": "alle", "datum": montag.isoformat(), "wert": round(wert, 2)})

    for (rid, name, region, sym), d in zip(INDIZES, idx_daten):
        if not d:
            continue
        werte.append(zeile({"id": rid, "klasse": "Aktien", "gruppe": "Indizes", "name": name,
                            "region": region, "symbol": sym, "einheit": "Punkte"}, d))
        verlauf += [{"id": rid, "datum": p[0].isoformat(), "wert": round(p[1], 4)} for p in wochenreihe(d["reihe"])]

    for (rid, name, gruppe, einheit, _), (sym, d) in zip(ROHSTOFFE, roh_daten):
        if not d:
            continue
        werte.append(zeile({"id": rid, "klasse": "Rohstoffe", "gruppe": gruppe, "name": name,
                            "region": "", "symbol": sym, "einheit": einheit}, d))
        verlauf += [{"id": rid, "datum": p[0].isoformat(), "wert": round(p[1], 4)} for p in wochenreihe(d["reihe"])]

    gesamt = sicher(krypto_gesamt)
    if gesamt:
        werte.append(zeile({"id": "gesamt", "klasse": "Krypto", "gruppe": "Krypto", "name": "Krypto gesamt",
                            "region": f"BTC-Dominanz {gesamt['dominanz']:.0f} %" if gesamt["dominanz"] else "",
                            "symbol": "TOTAL", "einheit": "USD", "format": "kompakt"}, gesamt))
        verlauf += [{"id": "gesamt", "datum": p[0].isoformat(), "wert": round(p[1])} for p in wochenreihe(gesamt["reihe"])]
    for (rid, name, sym), d in zip(KRYPTO, krypto_daten):
        if not d:
            continue
        werte.append(zeile({"id": rid, "klasse": "Krypto", "gruppe": "Krypto", "name": name,
                            "region": sym.split("-")[0].rstrip("0123456789"), "symbol": sym, "einheit": "USD"}, d))
        verlauf += [{"id": rid, "datum": p[0].isoformat(), "wert": round(p[1], 4)} for p in wochenreihe(d["reihe"])]

    # Anlageklassen von oben
    def mittelreihe(symbole):
        """Gleich gewichtete Mischung mehrerer Kursreihen, auf die gemeinsamen Handelstage normiert."""
        reihen = [dict(r["reihe"]) for r in (sicher(yahoo_reihe, x) for x in symbole) if r and r["reihe"]]
        if not reihen:
            return None
        tage = sorted(set.intersection(*(set(r) for r in reihen)))
        if not tage:
            return None
        reihe = [(t, sum(r[t] / r[tage[0]] for r in reihen) / len(reihen) * 100) for t in tage]
        return {"reihe": reihe, "letzt": reihe[-1][1], "vortag": reihe[-2][1] if len(reihe) > 1 else None,
                "waehrung": "USD", "stand": dt.datetime.combine(reihe[-1][0], dt.time(), dt.timezone.utc).isoformat()}
    klassen = []
    for kid, name, basis, stichtag, symbole, beschreibung, art in ANLAGEKLASSEN:
        if art == "cmc":
            d = gesamt
        elif art == "bestand":
            d = sicher(yahoo_reihe, symbole[0])  # echter Metallpreis, nicht normiert
        else:
            d = mittelreihe(symbole) if symbole else None
        if art == "statisch":
            z = {"id": kid, "klasse": "Anlageklasse", "gruppe": "Anlageklasse", "name": name, "region": "",
                 "symbol": beschreibung, "einheit": "USD, Schätzung", "format": "kompakt", "kurs": basis * 1e9,
                 "waehrung": "USD", "stand": stichtag.isoformat(), "t1": None, "ytd": None,
                 "j1": IMMO_J1, "j5": IMMO_J5, "j10": None}
            klassen.append(z)
            verlauf += [{"id": kid, "datum": tag, "wert": wert * 1e12} for tag, wert in IMMO_JAHRE]
            continue
        if not d:
            continue
        if art == "cmc":
            wert = d["letzt"]
        elif art == "bestand":
            wert = basis * UNZEN_JE_TONNE * d["letzt"]  # oberirdischer Bestand in Tonnen × Preis je Unze
        else:
            alt = schluss_vor(d["reihe"], stichtag)
            wert = basis * 1e9 * d["letzt"] / alt if alt else None
        z = zeile({"id": kid, "klasse": "Anlageklasse", "gruppe": "Anlageklasse", "name": name, "region": "",
                   "symbol": beschreibung, "einheit": "USD pro Jahr, Schätzung" if art == "fluss" else "USD, Schätzung",
                   "format": "kompakt"}, d)
        z["kurs"] = round(wert) if wert else None
        z["fluss"] = art == "fluss"
        klassen.append(z)
        verlauf += [{"id": kid, "datum": p[0].isoformat(), "wert": round(p[1], 4)} for p in wochenreihe(d["reihe"])]
    summe = sum(z["kurs"] for z in klassen if z["kurs"] and not z.get("fluss"))
    for z in klassen:
        z["anteil"] = round(z["kurs"] / summe * 100, 1) if z["kurs"] and summe and not z.get("fluss") else None
        z["region"] = (f"{z['anteil']:.1f} % des Gesamtmarkts" if z["anteil"]
                       else ("nicht im Anteil" if z.get("fluss") else ""))
    werte[:0] = klassen

    # Rohstoffstruktur: GSCI-Gewichte 2026, mit der Kursentwicklung seit Jahresbeginn fortgeschrieben
    roh = {r["id"]: r for r in werte if r["klasse"] == "Rohstoffe"}
    roh_ytd = {}
    for sid, name, gewicht, teile in GSCI_2026:
        summe_g, summe_w = 0.0, 0.0
        for teil, g in teile.items():
            if teil in roh:
                ytd = roh[teil]["ytd"]
            else:
                d = sicher(yahoo_reihe, teil)
                ytd = veraenderungen(d["reihe"], d["letzt"], d["vortag"])["ytd"] if d else None
            if ytd is not None:
                summe_g += g
                summe_w += g * ytd
        roh_ytd[sid] = summe_w / summe_g if summe_g else 0.0
    roh_summe = sum(g * (1 + roh_ytd[sid] / 100) for sid, _, g, _ in GSCI_2026)
    for sid, name, gewicht, _ in GSCI_2026:
        werte.append({"id": "struktur-" + sid, "klasse": "Rohstoffstruktur", "gruppe": "Rohstoffstruktur", "name": name,
                      "gewicht_2026": gewicht, "ytd": round(roh_ytd[sid], 2),
                      "gewicht": round(gewicht * (1 + roh_ytd[sid] / 100) / roh_summe * 100, 2),
                      "region": "", "symbol": "", "einheit": "%", "kurs": None, "waehrung": None, "stand": jetzt,
                      "t1": None, "j1": None, "j5": None, "j10": None})

    # Grösste Titel je Index
    alle = sorted({s for liste in KANDIDATEN.values() for s in liste})
    kap = yahoo_kapitalisierung(alle + [s for liste in MITGLIEDER.values() for s in liste])
    stueck, anteil_vorher = vorherige_aktienzahl(vorher) if vorher else ({}, {})
    fx = {"USD": 1.0}
    for whg, sym in FX.items():
        d = sicher(yahoo_reihe, sym)
        if d and d["letzt"]:
            fx[whg] = d["letzt"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        titel_daten = dict(zip(alle, pool.map(lambda s: sicher(yahoo_reihe, s), alle)))
    idx_name = {r[0]: r[1] for r in INDIZES}
    for rid, liste in KANDIDATEN.items():
        def wert(s):
            d = titel_daten.get(s)
            if kap.get(s, {}).get("cap"):
                return kap[s]["cap"]
            if s in stueck and d and d["letzt"]:
                return stueck[s] * d["letzt"]  # Schätzung aus der Aktienzahl des letzten Laufs
            return None
        if any(wert(s) for s in liste):
            reihenfolge = sorted(liste, key=lambda s: -(wert(s) or 0))
        else:
            reihenfolge = liste  # Rückfall: feste Reihenfolge der Kandidatenliste
        # Anteil der fünf grössten am Börsenwert aller Mitglieder; ohne frische Werte der Stand des letzten Laufs
        anteil = None
        if rid in MITGLIEDER:
            caps = [kap.get(m, {}).get("cap") or 0 for m in MITGLIEDER[rid]]
            fehlend = sum(1 for c in caps if not c)
            if sum(caps) and fehlend <= len(caps) // 10:
                top = sorted(caps, reverse=True)[:TOP_N]
                anteil = round(sum(top) / sum(caps) * 100, 1)
            else:
                anteil = anteil_vorher.get(rid)
        rang = 0
        for s in reihenfolge:
            d = titel_daten.get(s)
            if not d or d["letzt"] is None:
                continue
            rang += 1
            name = " ".join((kap.get(s, {}).get("name") or d["name"] or s).split())
            bw = wert(s)
            kurs_usd = fx.get(d["waehrung"])
            aktien.append(zeile({"key": f"{rid}:{s}", "index": rid, "indexname": idx_name[rid], "rang": rang,
                                 "name": name, "symbol": s, "boersenwert": round(bw) if bw else None,
                                 "boersenwert_usd": round(bw * kurs_usd) if bw and kurs_usd else None,
                                 "anteil_top5": anteil,
                                 "aktienzahl": round(bw / d["letzt"]) if bw else None}, d))
            if rang == TOP_N:
                break

    # Zinsen
    for k, land, fn in LAENDER:
        reihen = sicher(globals()[fn]) or {}
        for lz, reihe in sorted(reihen.items()):
            if not reihe:
                continue
            letzt = reihe[-1][1]
            vortag = reihe[-2][1] if len(reihe) >= 2 else None
            zinsen.append({"key": f"{k}-{lz}J", "land": land, "kuerzel": k, "laufzeit": f"{lz}J",
                           "rendite": round(letzt, 3), "stand": reihe[-1][0].isoformat(),
                           **veraenderungen(reihe, letzt, vortag, als_differenz=True)})
            if lz == 10 and (reihe[-1][0] - reihe[0][0]).days > 300:  # nur mit Jahreshistorie eine Linie
                verlauf += [{"id": f"zins-{k}", "datum": p[0].isoformat(), "wert": round(p[1], 3)}
                            for p in wochenreihe(reihe)]

    news = nachrichten()

    stempel = {"at": jetzt, "by": "Geplante Aktualisierung (abruf.py)"}
    umsatz = sicher(meistgehandelt) or []
    gewinner = sicher(krypto_gewinner) or []
    makrodaten, makroverlauf = sicher(makro) or ([], [])
    dateien = {"werte.json": werte, "aktien.json": aktien, "zinsen.json": zinsen,
               "verlauf.json": verlauf, "news.json": news, "umsatz.json": umsatz,
               "kryptogewinner.json": gewinner, "makro.json": makrodaten,
               "makroverlauf.json": makroverlauf}
    for name, zeilen in dateien.items():
        with open(f"{ziel}/{name}", "w", encoding="utf-8") as f:
            json.dump({"rows": zeilen}, f, ensure_ascii=False, separators=(",", ":"))
    bericht = {"stand": jetzt, "anzahl": {k: len(v) for k, v in dateien.items()}, "fehler": FEHLER, "updated": stempel}
    print(json.dumps(bericht, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    # Aufruf: python3 abruf.py <ausgabeordner> [<aktien.json des letzten Laufs>]
    #         python3 abruf.py --nachrichten <ausgabeordner>   (nur news.json, für die 5-Minuten-Aktualisierung)
    if len(sys.argv) > 1 and sys.argv[1] == "--nachrichten":
        ziel = sys.argv[2] if len(sys.argv) > 2 else "."
        news = nachrichten()
        with open(f"{ziel}/news.json", "w", encoding="utf-8") as f:
            json.dump({"rows": news, "stand": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
                      f, ensure_ascii=False, separators=(",", ":"))
        print(json.dumps({"anzahl": len(news), "fehler": FEHLER}, ensure_ascii=False))
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else ".", sys.argv[2] if len(sys.argv) > 2 else None)
