#!/usr/bin/env python3
"""Übernimmt frisch abgerufene Dateien aus neu/ nach daten/, wenn sie genug Zeilen haben; sonst bleibt der letzte Stand."""
import json
import pathlib
import shutil

MINDEST = {"werte.json": 25, "aktien.json": 30, "zinsen.json": 10, "verlauf.json": 100, "news.json": 5,
           "umsatz.json": 5, "kryptogewinner.json": 5, "makro.json": 10}

for name in sorted(p.name for p in pathlib.Path("neu").glob("*.json")):
    p = pathlib.Path("neu") / name
    if len(json.loads(p.read_text())["rows"]) >= MINDEST.get(name, 1):
        shutil.copy(p, pathlib.Path("daten") / name)
    else:
        print("Behalte alten Stand:", name)
