# Validerat väderdataflöde i Python

*Individuell fördjupning inom Python för Data Science. Namn: Tim Rydén. Datum: 2026-09-25.*

## Syfte

Jag undersöker hur ett litet, reproducerbart dataflöde kan byggas från ett JSON-API till analysbar Parquet-data. Min fråga är: vilka kontroller behövs för att ett lyckat API-anrop också ska bli en tillförlitlig tabell? Jag demonstrerar hämtning av historiska dygnsvärden, validering med Pydantic, skrivning med PyArrow och SQL-analys med DuckDB. Jag avgränsar mig till en plats, två variabler och ett datumintervall i live-läget; demot omfattar fyra syntetiska dygn.

## Området och dess relevans

Data Science börjar ofta innan modellen eller diagrammet: externa källor måste tolkas, kvalitetssäkras och göras tillgängliga för analys. Ett HTTP-svar med status 200 säger bara att en begäran lyckades, inte att dygnsserien är komplett eller att enheterna är de förväntade. I detta projekt används Open-Meteos historiska API för Malmö (55.6059, 13.0007), `temperature_2m_max` och `precipitation_sum` för ett valt datumintervall. API:t erbjuder historiska data via `/v1/archive`; de representerar modell-/återanalysdata och ska inte förväxlas med lokala stationsobservationer [1].

## Viktiga begrepp

**API och JSON.** Begäran anger koordinater, datum, dygnsvariabler, enheter och tidszon. Svaret har parallella arrayer: `daily.time[i]`, `daily.temperature_2m_max[i]` och `daily.precipitation_sum[i]` hör ihop. Om listorna har olika längd skulle Pythons zip() utan en föregående längdkontroll stanna vid den kortaste listan. Då kan dygn försvinna ur analysen utan ett felmeddelande.

**Schema kontra semantisk validering.** Pydantic kontrollerar fältnamn, typer och numeriska gränser genom modeller [2]. Vår egen funktion kontrollerar även att varje index motsvarar exakt det väntade kalenderdatumet och att varje kolumn har rätt längd. Värden `null` stoppas uttryckligen. Min field_validator gör om API:ts ISO-datumsträngar till date före Pydantics typkontroll. De numeriska värdena i dygnslistan kontrolleras strikt och accepterar därför inte texten "2.5". Förkortningen `mm` kontrolleras innan talet får tolkas som millimeter. Rimlighetsgränserna (−90 till 60 °C och 0 till 2000 mm) är skydd mot grova fel, inte en garanti för meteorologisk korrekthet.

**Parquet och DuckDB.** Parquet lagrar tabellens kolumner med schema och kan komprimera dem [3]. Här skrivs ett explicit Arrow-schema: datum, temperatur och nederbörd. DuckDB frågar direkt mot filen med `read_parquet(?)`, utan import till en separat databas [4]. SQL-grupperingen beräknar medelvärde för *dagens maxtemperatur* och summa nederbörd per månad. Medelvärdet är inte samma sak som månadens medeltemperatur.

## Genomförande

Inom ETL-processen så finns hämtning, validering, bearbetning och lagring. Här använder jag samma grundidé med API-hämtning, ett validerat dygnsschema, Parquet-lagring och SQL-analys. Jag valde att testa datumseriens fullständighet särskilt, eftersom Pydantics fälttyper inte uttrycker att varje dygn i ett begärt intervall måste finnas.

Jag byggde en liten modul där CLI-delen hämtar data och styr körningen, medan `core.py` ansvarar för validering, lagring och analys. `requests.get(..., timeout=30)` hämtar JSON och `raise_for_status()` avbryter vid HTTP-fel. Två körlägen finns: `--live` hämtar det datumintervall som anges med `--start-date` och `--end-date` och `--demo` läser fyra **påhittade** dygn ur `data/demo.json`. Det senare visar exakt samma validerings- och analysväg utan osäkerhet kring nätåtkomst under presentationen.

Ett viktigt eget val är att kräva en obruten, sorterad dagserie. Jag beräknar väntat datum från startdatum plus radens index och jämför med svaret. Därmed upptäcks även dubbletter och fel ordning. Alternativet hade varit att tyst hoppa över felaktiga rader och ändå få ett resultat, men då skulle månadsmedelvärden och totalsummor kunna se trovärdiga ut trots saknade dagar. Här stoppar flödet hellre hela körningen. Det är ett medvetet val för en liten demonstration; ett större system kan karantänlägga felaktiga poster och logga kvalitetsmått.

Efter valideringen skapas `WeatherDay`-objekt, en Arrow-tabell och `weather.parquet`. DuckDB grupperar datan med SQL och resultat skrivs till `monthly_summary.csv`. Filerna skapas först i en tillfällig underkatalog. Vid fel före publiceringen blir tidigare resultat kvar; de tre slutliga filbytena är dock inte en atomisk transaktion som grupp. De automatiska testerna kontrollerar att godkänd data kan sparas som Parquet och analyseras med SQL, och att flera typer av felaktig data stoppas.

Jag stötte vid verifiering på att Pydantics striktläge inte automatiskt gör JSON-strängar till `date` när man validerar en redan parsad Python-dictionary. Jag lade därför in en tydlig `mode="before"`-validator som konverterar just ISO-datumsträngarna, utan att lätta på kravet för numeriska värden. Detta skiljer avsiktlig konvertering från oavsiktlig typkoercion [2].

## Resultat

Offlinekörningen `python -m weather_pipeline --demo` gav **4 validerade dagar** och följande analys. Alla värden nedan är syntetiska och säger inget om verkligt väder:

| Månad | Dagar | Medel av dygnsmax (°C) | Nederbörd (mm) |
|---|---:|---:|---:|
| 2023-01 | 4 | 2,00 | 4,00 |

Beräkningen är kontrollerbar för hand: `(2 + 4 − 1 + 3) / 4 = 2`, och `0 + 2,5 + 1 + 0,5 = 4`. Sex automatiska kontroller passerade lokalt: normal genomgång av Parquet och SQL, `null`, fel enhet, dubblettdatum, saknat datum och negativ nederbörd. Ett exempel på kärnan i kontrollen är:

```python
expected = date.fromordinal(start.toordinal() + i)
if series.time[i] != expected:
    raise ValueError(f"oväntat datum vid position {i}")
```

Det sparade liveutfallet från historik-API:t gäller Malmö 2025: **365 dygn** och **12 månadsrader**. Januari 2025 gav 31 dagar, medel dygnsmax **4,59 °C** och nederbördssumma **65,5 mm**; juli gav 31 dagar, **21,39 °C** respektive **77,4 mm**. Detta är API:ts historiska modell-/återanalysdata vid körningen, inte syntetiska tal eller stationens observationer. De sparade livefilerna ligger i `output/`; en ny körning ersätter dessa. Läs `run_summary.txt` för att se vilken källa som användes vid senaste körning.

## Begränsningar och möjliga förbättringar

Programmet låter användaren välja datum, men Malmös koordinater är fasta. Det kräver också tidszonen Europe/Stockholm, temperatur i °C och nederbörd i mm. Jag har avgränsat det så för att tydligt kunna kontrollera att API-svaret har det format och de enheter som analysen förväntar sig.

 Hårda gränser kan avvisa giltiga extrema observationer eller släppa igenom rimliga men felaktiga värden. Ett fullständigt år får plats i minnet, men större datamängder bör hämtas och skrivas i batcher. SQL:s månadsgruppering har ingen jämförelse med klimatnormaler och påvisar inga trender.

API:t kan ändra svar eller vara otillgängligt. Programmet har timeout men ingen återförsökspolicy, versionssatt rådatakopia eller spårning av API-modellens ursprung. 

Resultatfilernas metadata innehåller läge och period men inte full begäran, hämtningstid och checksumma. I en större lösning skulle jag spara varje körnings resultat i en egen mapp och först när alla filer är färdiga byta vilken mapp som räknas som aktuell. Då minskar risken att någon läser en blandning av gamla och nya resultat. 

För fler platser behöver schemat plats-ID och en kontroll per `(plats, dag)`; då bör Parquet kunna partitioneras. Parquets styrkor syns tydligare med stor data och selektiva frågor: fyra rader i demot är ett pedagogiskt exempel, ingen prestandajämförelse med CSV eller Pandas.

## Koppling till yrkesrollen

En Data Scientist behöver kunna förklara vilken population och vilka enheter en tabell representerar innan resultat används för visualisering, prognoser eller beslutsstöd. Den här kodens gräns mellan extern JSON och intern typad data gör antaganden synliga och testbara. SQL mot Parquet är användbart när samma validerade data ska undersökas med olika frågor utan att skriva om insamlingssteget.

## Självreflektion

Innan det här arbetet hade jag inte arbetat med requests, Pydantic, PyArrow eller DuckDB. Jag behövde därför sätta mig in i vad varje paket gör och hur de kan användas tillsammans i ett dataflöde. Jag lärde mig att ett lyckat API-anrop bara är början: datan behöver kontrolleras innan den sparas och används i en analys.

Det som tog mest tid att förstå var Pydantic och skillnaden mellan att kontrollera enskilda värdens typer och att kontrollera en hel datumserie. Ett datum kan vara giltigt i sig, samtidigt som serien innehåller en dubblett och saknar en annan dag. Jag fick också förstå hur API datumsträngar omvandlas till Python-datum, hur PyArrow skriver validerade rader till Parquet och hur DuckDB läser filen för att beräkna månadsresultat med SQL.

Det tekniska val jag är mest nöjd med är att programmet avbryter när datum, enheter eller värden inte stämmer. Annars skulle en månadsöversikt kunna se trovärdig ut trots att underlaget är ofullständigt. Testerna hjälpte mig att se både att det normala flödet fungerar och att flera av dessa fel faktiskt stoppas.

Om jag började om skulle jag tidigare planera hur varje körning dokumenteras, till exempel vilken plats och period resultatfilerna gäller. Om jag fortsatte arbetet skulle jag också vilja göra det möjligt att välja plats och undersöka hur resultat kan jämföras med en annan datakälla.

Jag bedömer att arbetet kan motsvara VG eftersom jag har byggt ett fungerande och avgränsat dataflöde, motiverat mina tekniska val och undersökt både möjligheter och begränsningar. För mig är den viktigaste delen att jag nu kan förklara varför varje paket används och varför valideringen måste ske innan analysen.

## Källor

[1] Open-Meteo, [Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), läst senast 2026-09-23.

[2] Pydantic, [Models](https://docs.pydantic.dev/latest/concepts/models/) och [Validators](https://docs.pydantic.dev/latest/concepts/validators/), läst senast 2026-09-23.

[3] Apache Arrow, [Reading and Writing the Apache Parquet Format](https://arrow.apache.org/docs/python/parquet.html), läst senast 2026-09-23.

[4] DuckDB, [Reading and Writing Parquet Files](https://duckdb.org/docs/stable/data/parquet/overview), läst senast 2026-09-23.
