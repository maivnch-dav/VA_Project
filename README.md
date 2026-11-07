# SwissFlow VA – Demo

Visual-Analytics-Werkzeug (FHGR, Visual Analytics): öffentlicher Verkehr (Ist-Daten), Tourismus (BFS HESTA) und Wetter (MeteoSchweiz) in der Schweiz.

## 1. Prototypen ansehen (ohne Installation)

`prototypes/index.html` im Browser öffnen. Von dort führen Links zu allen Seiten:

- **Start · Datenüberblick** (`00-daten.html`)
- **Hypothesen** (`00-hypothesen.html`)
- **H1–H5** (`01-h1.html` … `05-h5.html`)

Internetverbindung nötig (Tailwind, Plotly und Schriften kommen von CDNs). Daten mit dem Etikett «Beispiel» sind simuliert, bis alle Ist-Daten geladen sind.

## 2. Startseite der App starten (Dash)

Voraussetzung: Python 3.12, am einfachsten mit [uv](https://docs.astral.sh/uv/).

```bash
uv venv --python 3.12 .venv
uv pip install -e .
.venv/bin/python -m va_project.app.dash_app
```

Dann im Browser: <http://127.0.0.1:8050>

Die Startseite «Datenüberblick» zeigt:
- sechs Kennzahlen (Verspätung, Pünktlichkeit, Ausfälle, Logiernächte, Neuschneetage, Datenabdeckung)
- eine Kantonskarte: Fläche = Logiernächte, Blase = Verspätungen + Ausfälle, Farbe = Schnee

Klick auf einen Kanton oder Lasso über mehrere Blasen → Monatsverläufe rechts im Detailbereich. Die Karte braucht Internet (Kartenkacheln von CARTO).

**Demo-Daten:** `data/curated/` enthält nur die vorbereiteten Daten, die die Startseite liest (Ist-Daten 01/2025 und 09/2026, Wetter pro Tag, HESTA, Stationen, Kantonsgrenzen). Die Seite «Datenqualität» zeigt mit DuckDB 2.0 derzeit eine Fehlermeldung; die übrigen Seiten sind noch nicht umgesetzt.

## Quellen

- Ist-Daten: opentransportdata.swiss
- Logiernächte: BFS HESTA
- Wetter: MeteoSchweiz SwissMetNet (Open Government Data)
- Kantonsgrenzen: swisstopo swissBOUNDARIES3D
- Kartenkacheln: © OpenStreetMap, © CARTO

UI-Spezifikation: `docs/UI-SPEC.md`.
