# Payne & Amber — Markdown → PDF

## Skill-Metadaten

```yaml
name: md2pdf
version: 0.1.0
description: >
  Konvertiert Markdown-Dateien in CI-konforme PDFs im Payne & Amber Design System.
  Unterstützt Deckblatt, Header-Bar, Footer, Blockquotes mit Amber-Linie,
  nummerierte und ungeordnete Listen, Code-Blöcke, H1–H4.
trigger_phrases:
  - "erstelle ein PDF"
  - "konvertiere Markdown zu PDF"
  - "mach ein PDF daraus"
  - "CI-konformes PDF"
  - "Payne & Amber PDF"
  - "Recherchebericht als PDF"
  - "Konzeptpapier als PDF"
dependencies:
  - reportlab
  - pypdf
```

## Anleitung

Wenn der User ein Markdown-Dokument als PDF im Payne & Amber CI haben möchte:

### 1. Abhängigkeiten sicherstellen

```bash
pip install reportlab pypdf --break-system-packages -q
```

### 2. Markdown vorbereiten

Die Markdown-Datei kann optional YAML-Frontmatter enthalten:

```markdown
---
title: "Dokumenttitel"
subtitle: "Untertitel"
author: "Constantin Ehrenstein"
date: "Februar 2026"
type: "Recherchebericht"
---
```

Falls kein Frontmatter vorhanden ist, wird der erste `# H1`-Heading als Titel verwendet.

### 3. PDF generieren

```bash
python3 {SKILL_DIR}/scripts/md2pdf.py INPUT.md OUTPUT.pdf \
  --type "Recherchebericht" \
  --mode print
```

**Parameter:**

| Parameter | Pflicht | Beschreibung |
|-----------|---------|-------------|
| `input` | ja | Pfad zur Markdown-Datei |
| `output` | nein | Pfad zur PDF-Datei (Default: `input.pdf`) |
| `--title` | nein | Titel (überschreibt Frontmatter/H1) |
| `--subtitle` | nein | Untertitel |
| `--author` | nein | Autor (Default: "Constantin Ehrenstein") |
| `--date` | nein | Datum (Default: aktueller Monat) |
| `--type` | nein | Dokumenttyp: Recherche, Konzept, Show Notes, etc. |
| `--mode` | nein | `print` (Default) oder `light` |

### 4. Ergebnis prüfen

Das generierte PDF enthält:

- **Deckblatt**: Payne-Deep-Balken mit Titel, Subtitle und Meta-Zeile in Amber
- **Content-Seiten**: 12mm Header-Bar, Amber-Fußlinie mit Seitenzahlen
- **H2-Überschriften**: mit Amber-Unterstreichung
- **Blockquotes**: Paper-Accent-Hintergrund mit Amber-Linksborder
- **Aufzählungen**: Amber-farbene Bullets/Nummern
- **Code-Blöcke**: Mono-Font auf Paper-Accent-Hintergrund
- **Inline-Formatierung**: Bold, Italic, Inline-Code, Links

## Unterstützte Markdown-Elemente

- `# H1` bis `#### H4`
- `**bold**`, `*italic*`, `` `inline code` ``
- `[Link-Text](URL)` → wird als Amber-farbiger Pfeil dargestellt
- Blockquotes mit `>`
- Ungeordnete Listen mit `- `, `* `, `+ `
- Nummerierte Listen mit `1. `
- Code-Blöcke mit ` ``` `
- Horizontale Linien mit `---`
- YAML-Frontmatter mit `---`

## Farbmodi

| Modus | Hintergrund | Einsatz |
|-------|-------------|---------|
| `print` | Weiß (#FFFFFF) | PDF-Export, Druck — tonersparend |
| `light` | Warmes Papier (#F6F2EC) | Bildschirmoptimiert |

## Fonts

Das Script nutzt ein 3-stufiges Font-Fallback-System:

| Rolle | Primär | Fallback System | Fallback Built-in |
|-------|--------|----------------|-------------------|
| Headings | Nunito Sans | Lato | Helvetica |
| Body | Lora | — | Times-Roman |
| Mono | JetBrains Mono | Noto Sans Mono | Courier |

Eigene Fonts können im Verzeichnis `assets/fonts/{Family}/{Family}-{Variant}.ttf` bereitgestellt werden.

## Dateistruktur

```
skill-md2pdf/
├── SKILL.md              ← Diese Datei
├── scripts/
│   └── md2pdf.py         ← Hauptscript
├── assets/
│   └── fonts/            ← Optionale Custom-Fonts
└── test/
    ├── test-recherche.md ← Beispiel-Markdown
    └── output-recherche.pdf ← Beispiel-Output
```

## Design-Tokens

Alle Farben, Typografie-Werte und Spacing-Skalen stammen aus dem Payne & Amber Design System (`tokens/`). Die Token-Werte sind im Script als Python-Konstanten eingebettet — bei Änderungen am Token-System müssen die `COLORS`-, `SIZES`- und `LINE_HEIGHTS`-Dicts im Script aktualisiert werden.

Langfristig: Automatische Token-Synchronisation über Style Dictionary JSON-Export → Python-Import.
