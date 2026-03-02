# Claude Skills — Qubity

Monorepo für Claude-Skills von [Qubity.dev](https://qubity.dev).

## Struktur

```
claude-skills/
├── shared/          Gemeinsam genutzte Ressourcen (Fonts, Templates …)
│   └── fonts/
├── skills/          Ein Verzeichnis pro Skill
│   └── md2pdf/      Markdown → CI-konforme PDF (Payne & Amber Design System)
└── README.md
```

## Skills

| Skill | Beschreibung |
|-------|-------------|
| **md2pdf** | Erzeugt CI-konforme PDFs aus Markdown – mit Deckblatt, Inhaltsverzeichnis, Pullquotes, Randnotizen u. v. m. Unterstützt Simplex- und Duplex-Druck sowie die Varianten *Classic* und *Editorial*. |

## Shared Assets

Das Verzeichnis `shared/` enthält Ressourcen, die von mehreren Skills genutzt werden können, z. B. Brand-Fonts oder Templates. Skills verweisen auf diese über relative Pfade.

## Lizenz

Proprietär – © Qubity.dev. Alle Rechte vorbehalten.
