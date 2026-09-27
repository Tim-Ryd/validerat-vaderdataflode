"""Starta dataflödet med ``python -m weather_pipeline --demo`` eller ``--live``.

Demoläget använder påhittade värden och fungerar utan internet. Liveläget
hämtar historiska väderdata för Malmö. Båda lägena använder samma steg
för validering, lagring och analys, så att resultaten kan jämföras tydligt.
"""
import argparse
import csv
import json
import os
from datetime import date
from pathlib import Path
import tempfile

import requests

from .core import analyze, validate_response, write_parquet

# Sökvägar utgår från projektet även om kommandot startas från en annan mapp.
ROOT = Path(__file__).resolve().parent.parent
API = "https://archive-api.open-meteo.com/v1/archive"


def fetch_live(start: date, end: date) -> dict:
    """Hämta historiska dygnsvärden för valt datumintervall från Open-Meteos API.

    Begäran anger plats, period, variabler, tidszon och enheter. Ett lyckat
    anrop betyder bara att vi fick ett svar; innehållet kontrolleras sedan
    av ``validate_response``. Nätfel och timeout stoppar körningen.
    """
    response = requests.get(API, params={
        "latitude": 55.6059,
        "longitude": 13.0007,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": "temperature_2m_max,precipitation_sum",
        "timezone": "Europe/Stockholm",
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
    }, timeout=30)
    response.raise_for_status()
    return response.json()


def run(mode: str, destination: Path, start: date, end: date) -> None:
    """Läs data, kontrollera den, spara Parquet och beräkna månadsresultat.

    ``mode`` ska vara ``demo`` eller ``live``. Filer i ``destination`` ersätts
    när de nya resultaten har skapats. ``run_summary.txt`` anger vilken källa
    som användes; ett nytt demoresultat ersätter tidigare liveresultat.
    """
    if mode == "demo":
        raw = json.loads(
            (ROOT / "data/demo.json").read_text(encoding="utf-8")
        )
    else:
        raw = fetch_live(start, end)

    days = validate_response(raw, start, end)
    destination.mkdir(parents=True, exist_ok=True)
    # Skapa och analysera nya filer före publicering. Varje fil byts separat;
    # de tre filbytena är inte en enda atomisk transaktion.
    with tempfile.TemporaryDirectory(dir=destination) as temp_dir:
        temporary = Path(temp_dir)
        parquet = temporary / "weather.parquet"
        write_parquet(days, parquet)
        rows = analyze(parquet)
        summary = temporary / "monthly_summary.csv"
        with summary.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["month", "days", "mean_daily_max_c", "precipitation_mm"])
            writer.writerows(rows)
            place = (
                "syntetiskt exempel"
                if mode == "demo"
                else "Malmö (55.6059, 13.0007)"
            )
        (temporary / "run_summary.txt").write_text(
            f"Läge: {mode}\nAntal validerade dagar: {len(days)}\n"
            f"Period: {start}–{end}\nPlats: {place}\nKälla: "
            f"{'syntetisk demo.json' if mode == 'demo' else API}\n",
            encoding="utf-8")
        for filename in ("weather.parquet", "monthly_summary.csv", "run_summary.txt"):
            os.replace(temporary / filename, destination / filename)
    print(f"{len(days)} validerade dagar; {len(rows)} månadsrader i {destination}")
    for row in rows:
        print(f"{row[0]}: {row[1]} dagar, medel dygnsmax {row[2]} °C, nederbörd {row[3]} mm")


def main() -> None:
    """Läs ``--demo`` eller ``--live`` och visa begripliga fel i terminalen."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true", help="syntetisk data, offline")
    mode.add_argument("--live", action="store_true", help="historisk data från API")
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    args = parser.parse_args()

    if args.demo:
        if args.start_date or args.end_date:
            parser.error("Ange datum endast med --live")
        start, end = date(2023, 1, 1), date(2023, 1, 4)
    else:
        if args.start_date is None or args.end_date is None:
            parser.error("--live kräver både --start-date och --end-date")
        if args.start_date > args.end_date:
            parser.error("Startdatum får inte vara efter slutdatum")
        start, end = args.start_date, args.end_date

    try:
        run("demo" if args.demo else "live", ROOT / "output", start, end)
    except (ValueError, requests.RequestException, KeyError, TypeError) as exc:
        parser.exit(1, f"Dataflödet avbröts: {exc}\n")


if __name__ == "__main__":
    main()
