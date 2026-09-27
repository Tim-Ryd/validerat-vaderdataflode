# Väderflöde: API → validering → Parquet → DuckDB

En avgränsad Pythonfördjupning för Data Science. Hämtar historiska dygnsvärden för Malmö från Open-Meteo, kontrollerar struktur, enheter och rimliga värden, skriver Parquet och sammanfattar med SQL. `--demo` använder **påhittade** värden i `data/demo.json` och kräver ingen nätanslutning.

## Starta

Python 3.10+ krävs. Kör från projektmappen:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m weather_pipeline --demo
python -m weather_pipeline --live --start-date 2025-01-01 --end-date 2025-12-31
python -m unittest discover -s tests -v
```

Resultat skrivs i `output/`: `weather.parquet`, `monthly_summary.csv` och `run_summary.txt`. Projektet levereras med sparat liveutfall för Malmö under 2025. En ny körning ersätter filerna. Live-läget kräver åtkomst till `archive-api.open-meteo.com`; nätfel ger ett tydligt fel utan att ersätta tidigare resultat. Datumintervallet anges med `--start-date` och `--end-date`; det sparade exemplet använder 2025-01-01–2025-12-31, lokala dygn i tidszonen Europe/Stockholm. Värdena är historiska modell-/återanalysdata, inte mätningar vid en viss väderstation.

## Upplägg

- `weather_pipeline/__main__.py`: CLI, API-anrop, orkestrering och publicering av resultatfiler en i taget.
- `weather_pipeline/core.py`: Pydantic-modeller, semantiska kontroller, Parquet-schema och SQL.
- `data/demo.json`: liten pedagogisk, syntetisk fixture i samma format som API-svaret.
- `tests/test_pipeline.py`: kontrollerar normalfall, saknat värde, fel enhet, fel datum och dubblerade dagar.
- `presentation.md`: fem minuters körschema och förslag på svar vid frågor.
- `visa_parquet.py`: skriver ut kolumnnamn och de första tio raderna ur senaste Parquet-filen (`python visa_parquet.py`).

API-parametrar: latitud 55.6059, longitud 13.0007, `daily=temperature_2m_max,precipitation_sum`, `timezone=Europe/Stockholm`, `temperature_unit=celsius`, `precipitation_unit=mm`. Inga nycklar behövs för denna icke-kommersiella demonstrationsanvändning; kontrollera tjänstens villkor för annan användning. 

Svaret hämtas med timeout och ett fel i HTTP, JSON, schema eller dagserie avbryter körningen. All output skrivs först i en tillfällig katalog och ersätter tidigare output först efter en lyckad körning. Datumargumenten krävs i live-läge; demo använder alltid 1–4 januari 2023. Ingen automatisk schemaläggning eller inkrementell laddning ingår.

## Källor

- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)
- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/) och [validators](https://docs.pydantic.dev/latest/concepts/validators/)
- [Apache Arrow: Parquet](https://arrow.apache.org/docs/python/parquet.html)
- [DuckDB: Parquet](https://duckdb.org/docs/stable/data/parquet/overview)
