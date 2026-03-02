# md2pdf — Payne & Amber Design System

Claude-Skill zur Erzeugung CI-konformer PDFs aus Markdown.

## Features

- **Zwei Varianten:** Classic (kompakt, breiter Außenrand) und Editorial (großzügig, schmaler Außenrand)
- **Simplex & Duplex:** Einseitiger oder doppelseitiger Druck mit gespiegelten Rändern
- **Deckblatt** mit goldenem Schnitt und Farbblock
- **Inhaltsverzeichnis** mit automatischer Seitennummerierung
- **Pullquotes** (Blockzitate) mit Amber-Akzentlinie
- **Randnotizen** im Außenrand, vertikal am zugehörigen Absatz ausgerichtet
- **Fußnoten** mit Referenznummern im Text
- **Aufzählungen** (nummeriert und unnummeriert, verschachtelt)
- **Inline-Formatierung:** Fett, Kursiv, Links, Code

## Verwendung

```bash
python scripts/md2pdf.py input.md output.pdf \
    --variant editorial \
    --sides double
```

### Parameter

| Flag | Werte | Standard | Beschreibung |
|------|-------|----------|-------------|
| `--variant` | `classic`, `editorial` | `editorial` | Design-Variante |
| `--sides` | `single`, `double` | `single` | Simplex oder Duplex |

## Markdown-Syntax

Siehe `SKILL.md` für die vollständige Syntax-Dokumentation inkl. Metadaten-Block, Überschriften, Pullquotes (`>`), Randnotizen (`{>> … <<}`), Fußnoten (`[^1]`) und mehr.

## Abhängigkeiten

- Python 3.10+
- ReportLab (`pip install reportlab`)

## Fonts

Die benötigten NunitoSans-Schnitte liegen unter `assets/fonts/NunitoSans/`. Das Skript registriert sie automatisch.
