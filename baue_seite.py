#!/usr/bin/env python3
"""Baut aus index.html (der Dashboard-Seite) eine eigenständige Website für GitHub Pages.

Die Dashboard-Seite erwartet die Umgebung von claude.ai: das Objekt `dash`, d3 und die Farb- und Abstandstoken.
Dieses Skript legt einen kleinen Ersatz dafür um die Seite, der die Daten aus daten/*.json liest.
Aufruf: python3 baue_seite.py <zielordner>
"""
import pathlib
import shutil
import sys

KOPF = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Marktübersicht</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' rx='3' fill='%230c1117'/%3E%3Cpath d='M3 11l3-3 2 2 5-5' stroke='%233fbf7f' stroke-width='2' fill='none'/%3E%3C/svg%3E">
<script src="d3.min.js"></script>
<style>
  /* Ersatz für die Token der claude.ai-Dashboards */
  :root {
    color-scheme: dark;
    --font-anthropic-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    --font-anthropic-serif: Georgia, "Times New Roman", serif;
    --cds-font-size-caption: 0.75rem; --cds-font-size-body: 0.875rem; --cds-font-size-heading: 1.0625rem; --cds-font-size-title: 1.5rem;
    --cds-font-weight-medium: 550;
    --cds-gap-xs: 4px; --cds-gap-sm: 8px; --cds-gap-md: 12px; --cds-gap-lg: 20px; --cds-gap-xl: 32px;
    --cds-pad-xs: 4px; --cds-pad-sm: 8px; --cds-pad-md: 14px; --cds-pad-lg: 20px; --cds-pad-xl: 28px;
    --cds-radius: 8px; --cds-dur-slow: 240ms;
    --cds-shadow-popover: 0 6px 24px rgba(0, 0, 0, .45);
    --color-bg: #0f151d; --color-panel: #131a23; --color-border-line: #232e3c; --color-fg: #e4e9f0; --color-fg-muted: #8794a6;
    --color-ok: #3fbf7f; --color-bad: #f0605d;
  }
  html, body { margin: 0; background: #0c1117; color: #e4e9f0; font: 14px/1.45 var(--font-anthropic-sans); }
  [hidden] { display: none !important; }
  #dash-root { max-width: 1400px; margin: 0 auto; }
  .dash-skeleton { position: relative; color: transparent !important; }
  .dash-skeleton::after { content: ""; position: absolute; inset: 0; border-radius: 8px; background: linear-gradient(90deg, #131a23, #1a2330, #131a23); background-size: 200% 100%; animation: mu-laden 1.4s infinite; }
  @keyframes mu-laden { to { background-position: -200% 0; } }
  .mu-fuss { max-width: 1400px; margin: 0 auto; padding: 0 max(16px, 3vw) 32px; color: #8794a6; font-size: 12px; }
</style>
<script>
  // Ersatz für das dash-Objekt der claude.ai-Dashboards: liest daten/<id>.json und zeichnet bei Daten- oder Breitenänderung neu.
  (function () {
    const QUELLEN = ["werte", "aktien", "zinsen", "verlauf", "news"];
    const daten = {};
    QUELLEN.forEach((id) => { daten[id] = {status: "loading", data: []}; });
    const zeichner = [];
    const beobachter = [];
    function allesZeichnen() {
      beobachter.forEach((fn) => { try { fn(); } catch (e) { console.error(e); } });
      zeichner.forEach(([name, fn]) => document.querySelectorAll('[data-draw="' + name + '"]').forEach((el) => {
        if (el.closest("[hidden]")) return;
        try { fn(el); } catch (e) { console.error(name, e); }
      }));
    }
    window.dash = {
      data: (id) => daten[id] || {status: "missing", data: []},
      draw: (name, fn) => { zeichner.push([name, fn]); },
      onData: (fn) => { beobachter.push(fn); },
      setLink: (name) => { try { history.replaceState(null, "", "#" + name); } catch (e) {} },
      colors: ["#5b9cf6", "#3fbf7f", "#e8a33d", "#c678dd", "#56b6c2", "#f0605d", "#d19a66", "#98c379"],
      refresh: () => {}, params: () => ({}), setParams: () => {}, resetParams: () => {},
      calc: () => {}, loader: () => {},
    };
    window.addEventListener("DOMContentLoaded", () => {
      allesZeichnen();
      QUELLEN.forEach((id) => fetch("daten/" + id + ".json", {cache: "no-cache"})
        .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then((j) => { daten[id] = {status: "ok", data: j.rows || []}; })
        .catch(() => { daten[id] = {status: "error", data: []}; })
        .finally(allesZeichnen));
      let breite = window.innerWidth;
      window.addEventListener("resize", () => { if (Math.abs(window.innerWidth - breite) > 40) { breite = window.innerWidth; allesZeichnen(); } });
      const ziel = document.getElementById(location.hash.slice(1));
      if (ziel) setTimeout(() => ziel.scrollIntoView(), 600);
    });
  })();
</script>
</head>
<body>
<div id="dash-root">
"""

FUSS = """
</div>
<p class="mu-fuss">Daten: Yahoo Finance, CNBC, CoinMarketCap, US-Finanzministerium, Bundesbank, Bank of England, japanisches Finanzministerium, Bank of Canada, Reserve Bank of Australia, SNB, CFETS, State Street Global Market Portfolio 2026, S&amp;P GSCI. Aktualisierung jeden Werktag morgens und abends. Keine Anlageberatung.</p>
</body>
</html>
"""


def main(ziel):
    quelle = pathlib.Path(__file__).with_name("index.html").read_text(encoding="utf-8")
    quelle = quelle.replace('<meta name="dash-one-writer">\n', "")
    ziel = pathlib.Path(ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / "index.html").write_text(KOPF + quelle + FUSS, encoding="utf-8")
    shutil.copy(pathlib.Path(__file__).with_name("d3.min.js"), ziel / "d3.min.js")  # d3 7.9.0, lokal statt über ein CDN


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "site")
