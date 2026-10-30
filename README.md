# Marktübersicht

Öffentliches Finanz-Dashboard: Nachrichten, Anlageklassen, Aktienindizes mit ihren grössten Titeln, Rohstoffe, Staatsanleihen und Krypto.

- `abruf.py` holt alle Daten (nur Python-Standardbibliothek) und schreibt sie nach `daten/`.
- `index.html` ist die Seite, `baue_seite.py` baut daraus die eigenständige Website für GitHub Pages.
- `.github/workflows/aktualisieren.yml` aktualisiert jeden Werktag morgens und abends und veröffentlicht die Seite.

Quellen: Yahoo Finance, CNBC, CoinMarketCap, US-Finanzministerium, Bundesbank, Bank of England, japanisches Finanzministerium, Bank of Canada, Reserve Bank of Australia, SNB, CFETS, State Street Global Market Portfolio 2026, S&P GSCI. Keine Anlageberatung.
