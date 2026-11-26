# Bausteine auf anderen Websites einbinden

Jede Seite und jede Sektion der Marktübersicht lässt sich auf einer fremden Website einbinden.

## Schnell: Platzhalter und Ladeskript

```html
<div data-marktuebersicht data-seite="aktien" data-abschnitte="weltmarkt,bewertung"></div>
<script src="https://bopsinger.github.io/marktuebersicht/einbetten.js" async></script>
```

| Attribut | Bedeutung |
|---|---|
| `data-seite` | Seite wie in der Adresse nach `#/`, z. B. `aktien`, `aktien/usa`, `immobilien`, `rohstoffe`; leer = Startseite |
| `data-abschnitte` | Kennungen der Sektionen, kommagetrennt; leer = alle Sektionen der Seite |
| `data-hintergrund` | `transparent` übernimmt den Hintergrund der einbettenden Seite |
| `data-titel` | Titel des Rahmens für Screenreader |

Das Skript erzeugt einen Rahmen (iframe), der seine Höhe automatisch dem Inhalt anpasst. Mehrere Platzhalter auf einer Seite sind möglich. Ein Beispiel liegt unter `beispiel-einbettung.html`.

## Direkt als Adresse

```
https://bopsinger.github.io/marktuebersicht/?einbetten=1&abschnitte=weltmarkt#/aktien
```

Im Einbettungsmodus fehlen Kopfzeile und Navigation, gespeicherte Einstellungen des Browsers (Reihenfolge, eingeklappte Sektionen) werden nicht angewendet, und die Seite meldet ihre Höhe per `postMessage` (`{typ: "marktuebersicht-hoehe", id, hoehe}`) an die einbettende Seite.

## Seiten

`aktien`, `aktien/usa`, `aktien/eurozone`, `aktien/japan`, `aktien/grossbritannien`, `aktien/kanada`, `aktien/taiwan`, `aktien/china`, `aktien/schweiz`, `aktien/suedkorea`, `aktien/indien`, `aktien/australien`, `anleihen`, `immobilien`, `rohstoffe`, `gold`, `silber`, `krypto`.
Auf Marktseiten (z. B. `aktien/schweiz`) zeigen Indizes, Titel und Bewertung nur den betreffenden Markt.

## Sektionen

| Kennung | Titel | erscheint auf |
|---|---|---|
| `news` | Nachrichten | Startseite |
| `anlageklassen` | Anlageklassen | Startseite |
| `weltmarkt` | Weltaktienmarkt | Unterseite |
| `sektoren` | Sektoren | Unterseite |
| `breite` | Marktbreite (USA) | Unterseite |
| `bewertung` | Bewertung | Unterseite |
| `indizes` | Aktienindizes | Startseite |
| `titel` | Grösste Titel je Index | Startseite |
| `umsatz` | Meistgehandelte US-Aktien | Startseite |
| `stress` | Risiko und Stimmung | Unterseite |
| `immowelt` | Weltimmobilienmarkt | Unterseite |
| `wohnpreise` | Wohnimmobilien: Preise | Unterseite |
| `gewerbepreise` | Gewerbeimmobilien: Preise | Unterseite |
| `reits` | Börsenkotierte Immobilien (REITs) | Unterseite |
| `rohwelt` | Wert der Weltproduktion | Unterseite |
| `terminkurven` | Terminkurven | Unterseite |
| `verhaeltnisse` | Preisverhältnisse | Unterseite |
| `rohstoffe` | Rohstoffe | Startseite |
| `zinsen` | Zinsen: Staatsanleihen | Startseite |
| `makro` | Makro | Startseite |
| `laender` | Länderübersicht | Startseite |
| `krypto` | Krypto | Startseite |

## Anderes Hosting

Die Seite ist statisch und läuft bei jedem Webhoster. Gebaut wird sie mit `python3 baue_seite.py <zielordner>`; danach den Ordner `daten/` danebenlegen.
Die laufend aktualisierten Daten kommen standardmässig aus dem GitHub-Zweig `live`. Eine andere Adresse setzt die Umgebungsvariable `DATEN_URL` beim Bauen (mit abschliessendem `/`); leer bedeutet, dass nur die Dateien im Ordner `daten/` neben der Seite gelesen werden.

Hinweis: GitHub Pages ist laut GitHub nicht für kommerzielle Angebote gedacht. Für einen bezahlten Dienst die Seite bei einem kommerziellen Hoster betreiben. Lizenzstatus der Datenquellen siehe `QUELLEN.md`.
