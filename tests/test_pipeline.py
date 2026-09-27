"""Tester som visar att korrekt data fungerar och felaktig data stoppas.

Alla tester använder syntetisk data och kräver varken nätverk eller API-nyckel.
"""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from weather_pipeline.core import analyze, validate_response, write_parquet

DEMO = Path(__file__).resolve().parent.parent / "data/demo.json"


class PipelineTest(unittest.TestCase):
    """Kontrollera både ett komplett flöde och avvisning av felaktiga svar."""

    def setUp(self):
        """Läs en ny kopia av demot före varje test för att isolera ändringar."""
        self.raw = json.loads(DEMO.read_text(encoding="utf-8"))
        self.start, self.end = date(2023, 1, 1), date(2023, 1, 4)

    def check(self):
        """Validera den aktuella testdatan mot fyra förväntade dygn."""
        return validate_response(self.raw, self.start, self.end)

    def test_roundtrip_and_sql(self):
        """Godkänd data ska kunna skrivas som Parquet och summeras med SQL."""
        days = self.check()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "weather.parquet"
            write_parquet(days, path)
            self.assertEqual(analyze(path), [("2023-01", 4, 2.0, 4.0)])

    def test_null_rejected(self):
        """Ett saknat nederbördsvärde får inte ingå i månadsresultatet."""
        self.raw["daily"]["precipitation_sum"][1] = None
        with self.assertRaisesRegex(ValueError, "saknat värde"):
            self.check()

    def test_wrong_unit_rejected(self):
        """Enhetsbyte till tum får inte tyst tolkas som millimeter."""
        self.raw["daily_units"]["precipitation_sum"] = "inch"
        with self.assertRaisesRegex(ValueError, "enheter"):
            self.check()

    def test_duplicate_day_rejected(self):
        """Dubblerat datum avslöjar en lucka även om listlängden stämmer."""
        self.raw["daily"]["time"][1] = "2023-01-01"
        with self.assertRaisesRegex(ValueError, "datum"):
            self.check()

    def test_missing_day_rejected(self):
        """En kortare datumlista ska stoppas före filskrivning."""
        self.raw["daily"]["time"].pop()
        with self.assertRaisesRegex(ValueError, "antal"):
            self.check()

    def test_negative_precipitation_rejected(self):
        """Negativ nederbörd bryter mot datakontraktet."""
        self.raw["daily"]["precipitation_sum"][1] = -1.0
        with self.assertRaises(ValueError):
            self.check()


if __name__ == "__main__":
    unittest.main()
