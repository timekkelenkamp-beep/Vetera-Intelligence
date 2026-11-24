# Vetera Intelligence

**Competitive Intelligence Platform** voor verzekeringen van klassieke auto's, motorfietsen en bromfietsen.

Vetera Intelligence vergelijkt de huidige, aantoonbaar beschikbare Vetera-propositie objectief met Nederlandse
concurrenten. Het platform verzamelt en analyseert polisvoorwaarden, premies en marktontwikkelingen, en houdt
iedere conclusie herleidbaar naar document, pagina en artikel.

De applicatie draait volledig lokaal op een Windows-computer en wordt via de browser gebruikt op
**http://localhost:3000**. Database en documenten blijven op de computer. Alleen AI-functies (optioneel) en
toegestaan internetonderzoek maken een externe verbinding.

---

## Online gebruiken (zonder installatie)

De app kan ook online draaien bij Render, beveiligd met een wachtwoord. Volg
[`docs/ONLINE_ZETTEN.md`](docs/ONLINE_ZETTEN.md): account aanmaken, *New → Blueprint*, repository kiezen,
wachtwoord invullen. Het `Dockerfile` en `render.yaml` staan klaar.

## Installatie (Windows)

**Benodigd**

| Onderdeel | Versie | Download |
|---|---|---|
| Python | 3.12 of 3.13 (aanbevolen) | https://www.python.org/downloads/ — vink *Add python.exe to PATH* aan |
| Node.js | 20 LTS of nieuwer | https://nodejs.org/ |

**Stappen**

1. Pak het project uit of clone het naar bijvoorbeeld `C:\VeteraIntelligence`.
2. Dubbelklik **`install.bat`**. Dit maakt een Python-omgeving, installeert de pakketten, bouwt de interface en
   maakt de database aan (`data\vetera.db`).
3. Dubbelklik **`start.bat`**. De browser opent automatisch op http://localhost:3000.
   Sluit het zwarte venster om de app te stoppen.

**Optioneel**

- **AI-functies:** open `backend\.env` (aangemaakt door de installatie) en vul `ANTHROPIC_API_KEY=...` in.
  Herstart daarna de app. Zonder sleutel werken alle basisfuncties.
- **Wekelijkse broncontrole:** dubbelklik `scripts\schedule_weekly_check.bat`. Dit registreert een Windows-taak
  (maandag 09:00) die ook alsnog draait zodra de computer weer aan staat. Verwijderen kan met
  `scripts\remove_weekly_check.bat`.
- **OCR voor gescande PDF's:** installeer Tesseract (met Nederlands taalpakket) en Poppler, en daarna
  `backend\.venv\Scripts\pip install pytesseract pdf2image`. Zonder OCR worden gescande pagina's als
  *onbetrouwbaar* gemarkeerd.
- **Back-up:** via *Instellingen → Data & back-up* of `scripts\backup.bat`.

## Eerste gebruik

Een nieuwe installatie bevat bewust **geen** fictieve premies of voorwaarden. Het dashboard toont een
onboarding:

1. Leg bij *Concurrenten → Vetera* het huidige, openbaar gepubliceerde Vetera-product vast.
2. Voeg concurrenten toe, of laad de startlijst uit de opdracht (status *Te beoordelen*).
3. Importeer polisvoorwaarden (PDF, meerdere tegelijk, of via URL) bij *Bronnen & documenten*.
4. Leg bevindingen vast in de *Voorwaardenvergelijker* (handmatig, met de passagezoeker of met AI).
5. Leg premies vast of importeer je bestaande Excel-onderzoek in het *Premielab*.

---

## Functionaliteit in het kort

| Module | Wat het doet |
|---|---|
| **Dashboard** | AI-onderzoeksvraag, kerncijfers uit de database, onboarding, gemiste-controle-melding |
| **Concurrenten** | Zoeken, filteren, sorteren; toevoegen, bewerken, samenvoegen, verwijderen; status *Te beoordelen*; distributie- vs. canonieke producten; risicodragers; logobeheer met goedkeuring; **concurrentiekaart** (afdrukbaar) en **tijdlijn** per aanbieder |
| **Voorwaardenvergelijker** | Kaarten, matrix als heatmap en scores; referentie Vetera; filters, zoeken op clausule; uitleg per verschil; bron openen; export Excel/PDF; verkoopargumenten; **positioneringskaart** (premie × voorwaarden) en **wat-als-simulator** |
| **Adviestool** | Een paar vragen over de klant → welke producten aantoonbaar passen en waarom, met bronnen en gespreksvragen |
| **Premielab** | Rekenprofielen, premiewaarnemingen (6 typen), vergelijkbaarheidscontroles, grafieken, historie per gelijkwaardige reeks, uitsplitsing, Excel Import Studio, proefberekeningen (toestemmingsregister + handmatige workflow) |
| **Marktmonitor** | **Marktbericht** na elke controle; broncontrole met robots.txt, conditionele verzoeken en vertraging; documentversies en wijzigingsclassificatie; meldingen (markeren/archiveren/filteren); controlehistorie |
| **Verbeterradar** | Datagedreven signalen zonder AI, AI-voorstellen en innovatiehypotheses, 14-veldenstructuur, werkproces Nieuw → Afgerond/Afgewezen, *Onderzoek verder*-dossiers |
| **Rapportages** | 7 rapporttypen als PDF, Excel en printweergave, met managementsamenvatting, bronnen en beperkingen |
| **Bronnen & documenten** | Bronregister, documentbibliotheek met versies, full-text zoeken, PDF-viewer met gemarkeerde passage, datakwaliteit, beoordeling van AI-bevindingen |
| **Instellingen** | AI (model, effort, budgetten, privacy, webonderzoek, gebruik), rubrieken, monitor, back-up/herstel, verwijderen, audittrail |

Overal in de app: **Ctrl+K** (Mac: ⌘K) opent snelzoeken over aanbieders, producten, documenten, clausules en de volledige tekst van polisvoorwaarden.

Zie [`docs/FUNCTIONALITEITEN.md`](docs/FUNCTIONALITEITEN.md) voor het volledige overzicht, de testdekking en
de bekende beperkingen.

---

## Betrouwbaarheid en privacy (ontwerpprincipes)

- **Geen verzonnen informatie.** AI krijgt alleen lokale gegevens met id's; genoemde bronnen en citaten worden
  gecontroleerd tegen de werkelijk geëxtraheerde tekst. Onbekende verwijzingen en niet-teruggevonden citaten
  worden zichtbaar gemarkeerd.
- **Ontbreken ≠ niet verzekerd.** Statussen: aantoonbaar gedekt, aantoonbaar uitgesloten, voorwaardelijk,
  aanvullende clausule, niet gevonden, onvoldoende informatie, menselijke beoordeling. Een AI-"uitsluiting" zonder
  geverifieerde passage wordt automatisch omgezet naar *menselijke beoordeling*.
- **Menselijke correcties winnen.** Handmatige en goedgekeurde bevindingen worden vergrendeld en nooit door een
  volgende AI-analyse overschreven. Alle wijzigingen staan in de audittrail; oude versies blijven bewaard.
- **Premies worden nooit geschat.** Ongelijke scenario's (dekking, eigen risico, belasting, peildatum, profiel)
  worden alleen met expliciete waarschuwing naast elkaar getoond. Geïmporteerde oude tarieven zijn standaard
  historisch.
- **Niet-publieke data gaat niet naar AI** zonder aparte instelling én bevestiging per verzoek. Vóór elk
  AI-verzoek toont de app wat er wordt verstuurd, naar wie, en de geraamde kosten.
- **Alleen lokaal bereikbaar.** De server bindt aan `127.0.0.1` en weigert andere hostnamen (DNS-rebinding).
  API-sleutels staan alleen in `backend\.env`, nooit in de browser.
- **Respectvol ophalen.** robots.txt wordt gerespecteerd, verzoeken naar lokale netwerkadressen worden geweigerd,
  er geldt een wachttijd per website en er worden geen beveiligingen omzeild. Er is geen garantie dat
  internetverkeer niet herleidbaar is.

---

## Projectstructuur

```
├── install.bat / start.bat        Windows-installatie en -start
├── scripts\                       Planning, back-up, tests, ontwikkelmodus
├── backend\                       Python · FastAPI · SQLAlchemy · Alembic · SQLite
│   ├── app\main.py                App, beveiliging (alleen lokaal), statische frontend
│   ├── app\models.py              Relationeel datamodel (±30 tabellen)
│   ├── app\routers\               REST-API per module
│   ├── app\services\              Documentverwerking, premies, Excel-import, analyse,
│   │                              AI (Claude), monitor, logo's, kwaliteit, rapportages
│   ├── alembic\                   Databasemigraties (incl. FTS5-zoekindex)
│   └── tests\                     Unit- en integratietests (pytest)
├── frontend\                      React · TypeScript · Vite · Tailwind · Radix (shadcn-stijl)
│   ├── src\pages\                 Schermen
│   ├── src\components\            UI-bouwstenen, bronviewer, AI-preview, Import Studio
│   └── e2e\                       Browsertests (Playwright)
├── docs\FUNCTIONALITEITEN.md      Gerealiseerde functies, testdekking en beperkingen
└── data\                          (lokaal, niet in git) database, documenten, imports, logo's, rapporten, back-ups
```

## Ontwikkelen en testen

```bat
scripts\dev.bat           :: backend met auto-reload + Vite op http://127.0.0.1:5173
scripts\run_tests.bat     :: pytest + Playwright (eenmalig: cd frontend && npx playwright install chromium)
```

Handmatig:

```bat
cd backend
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
cd ..\frontend
npm run typecheck
npx playwright test
```

Nieuwe databasewijziging: pas `backend\app\models.py` aan en genereer een migratie met
`.venv\Scripts\alembic revision --autogenerate -m "omschrijving"`. Migraties draaien automatisch bij het starten.

API-documentatie (lokaal): http://localhost:3000/api/docs

## Configuratie

Zie `backend\.env.example`. Belangrijkste variabelen:

| Variabele | Standaard | Betekenis |
|---|---|---|
| `ANTHROPIC_API_KEY` | – | Optionele sleutel voor AI-functies |
| `VETERA_HOST` / `VETERA_PORT` | `127.0.0.1` / `3000` | Lokaal adres |
| `VETERA_DATA_DIR` | `.\data` | Datamap (database, bestanden, back-ups) |
| `VETERA_MAX_UPLOAD_MB` | `50` | Maximale uploadgrootte |
| `VETERA_ALLOW_REMOTE_ACCESS` | `false` | Online modus: alles achter het wachtwoord |
| `VETERA_APP_PASSWORD` / `VETERA_SESSION_SECRET` | – | Verplicht in online modus |
| `VETERA_AUTO_MONITOR` | `false` | Server voert de wekelijkse broncontrole zelf uit |

AI-model, effort, budgetten, privacy en webonderzoek stel je in via *Instellingen → AI*.

## Merkassets

Logo's worden uitsluitend als officiële bestanden van de website van de aanbieder opgehaald of handmatig
geüpload, en pas na goedkeuring gebruikt. Ze worden nooit nagemaakt. Controleer per aanbieder de merkrichtlijnen
voordat je logo's in externe rapportages gebruikt. Zonder goedgekeurd logo toont de app een nette tekstweergave.
