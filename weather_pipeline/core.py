"""Kontrollera API-data, spara den i Parquet och analysera den med SQL.

För Data Science är det viktigt att veta vilka antaganden som görs innan data
analyseras. Därför ligger regler för enheter, datum och värden samlade här.
Modulen gör inga API-anrop, så reglerna kan testas utan nätverk.
"""
from datetime import date
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DailySeries(BaseModel):
    """API:ts tre listor; värden på samma position hör till samma dygn."""

    model_config = ConfigDict(strict=True)
    time: list[date]
    temperature_2m_max: list[float | None]
    precipitation_sum: list[float | None]

    @field_validator("time", mode="before")
    @classmethod
    def parse_dates(cls, values: list[str]) -> list[date]:
        """Tolka JSON-datum uttryckligen; behåll strikt kontroll av talen."""
        return [date.fromisoformat(value) for value in values]


class Units(BaseModel):
    """Beskrivning av API:ts enheter, till exempel °C och mm."""

    time: str
    temperature_2m_max: str
    precipitation_sum: str


class ApiResponse(BaseModel):
    """De fält i Open-Meteos JSON-svar som detta dataflöde använder."""

    latitude: float
    longitude: float
    timezone: str
    daily_units: Units
    daily: DailySeries


class WeatherDay(BaseModel):
    """En analyserbar rad med datum, maxtemperatur och nederbörd.

    Gränserna fångar grova fel. Ett rimligt tal kan ändå vara felaktigt.
    """

    model_config = ConfigDict(strict=True)
    day: date
    max_temp_c: float = Field(ge=-90, le=60)
    precipitation_mm: float = Field(ge=0, le=2000)

    @field_validator("max_temp_c", "precipitation_mm")
    @classmethod
    def finite(cls, value: float) -> float:
        """Avvisa NaN (ogiltigt tal) och oändlighet före analys."""
        import math
        if not math.isfinite(value):
            raise ValueError("värdet måste vara ändligt")
        return value


# Bestäm kolumnernas typer uttryckligen i stället för att låta dem gissas.
SCHEMA = pa.schema([
    ("day", pa.date32()), ("max_temp_c", pa.float64()),
    ("precipitation_mm", pa.float64()),
])


def validate_response(raw: dict, start: date, end: date) -> list[WeatherDay]:
    """Validera ett API-svar och returnera en rad per förväntat dygn.

    ``raw`` är JSON-svaret omgjort till Python-data. Både ``start`` och ``end``
    räknas med. Pydantic kontrollerar fält och typer; denna funktion kontrollerar
    dessutom att hela datumserien är komplett och att enheterna stämmer.
    Vid fel avbryts flödet i stället för att analysera ofullständig data.
    """
    response = ApiResponse.model_validate(raw)
    if response.timezone != "Europe/Stockholm":
        raise ValueError("oväntad tidszon")
    if response.daily_units.model_dump() != {
        "time": "iso8601", "temperature_2m_max": "°C", "precipitation_sum": "mm"
    }:
        raise ValueError("oväntade enheter")
    series = response.daily
    n = (end - start).days + 1
    if any(len(column) != n for column in (
        series.time, series.temperature_2m_max, series.precipitation_sum
    )):
        raise ValueError("fel antal dagar eller olika långa kolumner")
    days = []
    for i in range(n):
        # Lika långa listor räcker inte: ett datum kan ändå saknas eller upprepas.
        expected = date.fromordinal(start.toordinal() + i)
        if series.time[i] != expected:
            raise ValueError(f"oväntat datum vid position {i}: {series.time[i]}")
        temp, rain = series.temperature_2m_max[i], series.precipitation_sum[i]
        if temp is None or rain is None:
            raise ValueError(f"saknat värde för {expected}")
        days.append(WeatherDay(day=expected, max_temp_c=temp, precipitation_mm=rain))
    return days


def write_parquet(days: list[WeatherDay], path: Path) -> None:
    """Skriv godkända dygn till en komprimerad Parquet-fil.

    Parquet bevarar kolumnernas typer så att filen kan läsas av analysverktyg.
    Målmappen måste finnas. Funktionen skriver över filen vid ``path``.
    """
    table = pa.Table.from_pylist([d.model_dump() for d in days], schema=SCHEMA)
    pq.write_table(table, path, compression="snappy")


def analyze(path: Path) -> list[tuple]:
    """Returnera månadsrader direkt från Parquet med DuckDB.

    Varje resultatpost innehåller månad, antal dygn, medel av dygnens
    maxtemperaturer i °C och sammanlagd nederbörd i mm. Detta medelvärde är
    inte månadens medeltemperatur. DuckDB läser filen direkt utan att en
    separat databasfil behöver skapas.
    """
    with duckdb.connect(":memory:") as con:
        return con.execute("""
            SELECT strftime(day, '%Y-%m') AS month,
                   count(*) AS days,
                   round(avg(max_temp_c), 2) AS mean_daily_max_c,
                   round(sum(precipitation_mm), 2) AS precipitation_mm
            FROM read_parquet(?)
            GROUP BY 1 ORDER BY 1
        """, [str(path)]).fetchall()
