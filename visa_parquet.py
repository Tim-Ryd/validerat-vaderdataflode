from pathlib import Path
import duckdb

fil = Path("output/weather.parquet")

if not fil.exists():
    raise SystemExit("Filen saknas. Kör först: python -m weather_pipeline --demo")

result = duckdb.sql(
    "SELECT * FROM read_parquet(?) ORDER BY day LIMIT 10",
    params=[str(fil)],
)

print(result.columns)

for row in result.fetchall():
    print(row)