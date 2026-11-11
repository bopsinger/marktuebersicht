#!/usr/bin/env bash
# Schreibt alle Dateien aus daten/ als einzigen Stand in den Zweig "live".
# Die Seite liest ihre Daten von dort; so muss sie für neue Daten nicht neu veröffentlicht werden.
# Aufruf: bash zweig_schreiben.sh <token> <owner/repo>
set -euo pipefail
tmp=$(mktemp -d)
cp daten/*.json "$tmp"/
cd "$tmp"
git init -q -b live
git config user.name "marktuebersicht-bot"
git config user.email "actions@users.noreply.github.com"
git add . && git commit -q -m "Live-Daten $(date -u +%Y-%m-%dT%H:%MZ)"
git push -q -f "https://x-access-token:$1@github.com/$2.git" live
