# Gerealiseerde functionaliteit, testdekking en beperkingen

Stand: eerste oplevering (fase 1 t/m 7 gebouwd; fase 7 als toestemmingsarchitectuur zonder bron-specifieke connectors).

Legenda testdekking: **A** = geautomatiseerd getest (pytest / Playwright) · **H** = handmatig/visueel gecontroleerd
in de browser · **X** = afhankelijk van externe dienst, toestemming of bron (niet end-to-end getest).

## Fase 1 — Functionele basis

| Functie | Status | Test |
|---|---|---|
| FastAPI-backend, SQLite, SQLAlchemy, Alembic-migraties (incl. FTS5-index) | Gereed | A |
| Windows-installatie/start (`install.bat`, `start.bat`), server op 127.0.0.1:3000 | Gereed | H (scripts niet op Windows uitgevoerd in de bouwomgeving, zie beperkingen) |
| Alleen lokale toegang (host-/clientcontrole), beveiligingsheaders | Gereed | A |
| Apple-achtige interface, vaste zijbalk met 9 onderdelen, animaties | Gereed | H, A |
| Dashboard met echte tellingen, onboarding, lege toestanden | Gereed | A, H |
| Concurrentenbeheer: zoeken, filteren, sorteren, toevoegen, bewerken, samenvoegen, verwijderen | Gereed | A |
| Status *Te beoordelen*, startlijst uit de opdracht (ongeverifieerd gemarkeerd) | Gereed | A |
| Onderscheid verzekeraar / gevolmachtigde / tussenpersoon / distributeur; risicodragers; canonieke producten tegen dubbeltelling | Gereed | A |
| Logobeheer: kandidaten van officiële website (robots.txt), upload, SVG-sanering, transparante achtergrond (flood-fill vanaf de rand, zonder vervorming), goedkeuring, tekstweergave als fallback | Gereed | H (ophalen van echte websites: X) |
| Bronregister met alle gevraagde velden, toegangsstatus, zichtbaarheid | Gereed | A |
| Audittrail van wijzigingen | Gereed | A |

## Fase 2 — Documentanalyse

| Functie | Status | Test |
|---|---|---|
| PDF-upload (meerdere tegelijk), validatie type/grootte, duplicaatdetectie (SHA-256) | Gereed | A |
| Openbare PDF ophalen via URL (robots.txt, blokkade lokaal netwerk) | Gereed | A (blokkades), X (echte sites) |
| Tekst per pagina, extractiekwaliteit per pagina, optionele OCR (Tesseract) | Gereed | A (extractie), X (OCR) |
| Herkenning aanbieder, product, documenttype, datum, versie | Gereed (heuristisch, ter bevestiging) | A |
| Clausule-/artikelherkenning | Gereed (heuristisch) | A |
| Versiebeheer: oude versies blijven bewaard, automatische vergelijking, classificatie van wijzigingen | Gereed | A |
| Gestandaardiseerde rubrieken (42 kenmerken in 6 rubrieken), uitbreidbaar in Instellingen | Gereed | A |
| Lokale passagezoeker: alleen *menselijke beoordeling* of *niet gevonden*, nooit *uitgesloten* | Gereed | A |
| Bevindingen met document, pagina, artikel en citaat; citaatverificatie tegen brontekst | Gereed | A |
| Menselijke correctie/goedkeuring vergrendelt bevinding; historie blijft bewaard | Gereed | A |
| Voorwaardenvergelijker: kaarten, matrix, filters, zoeken, kolommen, sorteren, verschiluitleg | Gereed | A (API), H (UI) |
| Export voorwaardenvergelijking naar Excel en PDF | Gereed | A |
| Geïntegreerde PDF-viewer met paginanavigatie en gemarkeerde passage in de geëxtraheerde tekst | Gereed | H (gebruikt de ingebouwde PDF-viewer van Edge/Chrome) |
| Full-text zoeken door alle documenten | Gereed | A |

## Fase 3 — Premielab

| Functie | Status | Test |
|---|---|---|
| Rekenprofielen (5 voorbeeldprofielen, gemarkeerd), bewerken met bescherming tegen onvergelijkbaar maken | Gereed | A |
| Premiewaarnemingen met alle gevraagde velden en 6 waarnemingstypen; omrekening naar jaarpremie | Gereed | A |
| Nooit geschatte premies (bedrag verplicht, of type *niet beschikbaar*) | Gereed | A |
| Vergelijking per profiel en peildatum: absoluut/procentueel, totale jaarlast incl. lidmaatschap/kosten, vergelijkbaarheidswaarschuwingen | Gereed | A |
| Historie per gelijkwaardige reeks, uitsplitsing naar dekking, categorie, waarde, kilometers | Gereed | A (API), H (grafieken) |
| Melding bij relevant premieverschil t.o.v. Vetera | Gereed | A |
| Excel Import Studio: XLSX/XLS/CSV, werkbladkeuze, kopregeldetectie, automatische kolomherkenning, handmatige koppeling, typecontrole, verplichte velden, duplicaten (binnen bestand en t.o.v. database), goedkeuringsstap, sjablonen, terugdraaien, origineel bestand lokaal bewaard, standaard historisch | Gereed | A |

## Fase 4 — AI Intelligence

| Functie | Status | Test |
|---|---|---|
| Claude-integratie (officiële SDK), modelkeuze, effort, maandbudget en limiet per verzoek, gebruiksregistratie | Gereed | A (blokkades/budget), X (echte API) |
| Preview vóór verzending: wat, waarheen, geraamde kosten; niet-publieke data uitgesloten | Gereed | A |
| Onderzoeksassistent met gestructureerd antwoord (7 onderdelen) en bronvalidatie | Gereed | A (validatielogica met gesimuleerd model), X |
| AI-voorwaardenanalyse van documenten met citaatverificatie en beschermingsregels | Gereed | A (gesimuleerd model), X |
| Verkoopargumenten: lokaal (zonder AI) en met AI; feit / klantvoordeel / verkoopargument; ook concurrentvoordelen | Gereed | A (lokaal), X (AI) |
| Verbeterradar: lokale signalering, AI-voorstellen, innovatiehypotheses, 14 velden, werkproces, dossiers | Gereed | A (lokaal), X (AI) |
| Wijzigingsanalyse van documentversies met AI | Gereed | X |
| Scores per aspect met aanpasbare wegingen, scenario's, minimale datadekking, transparante methode | Gereed | A |

## Fase 5 — Marktmonitor

| Functie | Status | Test |
|---|---|---|
| Broncontrole: robots.txt, ETag/Last-Modified, vertraging per host, max. 50 MB | Gereed | A (gesimuleerde webserver) |
| Nieuwe documentversies automatisch importeren en vergelijken; productpagina-wijzigingen (zichtbare tekst); nieuwe PDF-links ontdekken | Gereed | A |
| Wekelijkse Windows-taak (`StartWhenAvailable`), gemiste controle tonen en inhalen | Gereed | A (detectie), H/X (Taakplanner op Windows) |
| Meldingen: markeren, archiveren, filteren, alles gelezen | Gereed | A (API), H |
| Concurrentieontdekking via AI-webonderzoek (status *Te beoordelen*) | Gereed | X |

## Fase 6 — Rapportage en afwerking

| Functie | Status | Test |
|---|---|---|
| 7 rapporttypen als PDF en Excel, printweergave in de browser | Gereed | A |
| Managementsamenvatting, tabellen, grafiek (premie), bronnen, beperkingen | Gereed | A, H |
| Datakwaliteitsscherm (duplicaten, koppelingen, verouderde/onvergelijkbare premies, tegenstrijdige bronnen, extractie, niet-onderbouwde AI) | Gereed | A |
| Back-up (ZIP), herstel met veiligheidsback-up en integriteitscontrole, verwijderen per categorie | Gereed | A |

## Fase 7 — Automatische proefberekeningen (optioneel)

Gebouwd als **architectuur en beheerinterface**: register van calculators met gebruiksvoorwaarden,
toestemmingsstatus (onderbouwing verplicht bij *toegestaan*), controlelogboek en een handmatige workflow die
het resultaat als *vastgelegde proefberekening* opslaat (getoonde premie ≠ uitgebrachte offerte).

**Er zijn bewust geen bron-specifieke connectors meegeleverd.** Of geautomatiseerd gebruik van een specifieke
calculator is toegestaan, moet per bron worden vastgesteld (gebruiksvoorwaarden of schriftelijke toestemming).
De knop *Automatisch* weigert en logt dit zolang er geen toegestane, gebouwde connector is.

## Uitbreiding — inzichten en vormgeving

| Functie | Status | Test |
|---|---|---|
| Kleurrijkere, rustige vormgeving: gekleurde module-iconen, vaste kleur per aanbieder, matrix als heatmap, kleurverloop op het dashboard | Gereed | H |
| Positioneringskaart (premie × voorwaardenscore, kwadranten t.o.v. mediaan; producten zonder data apart vermeld) | Gereed | A |
| Adviestool: klantvragen → passende producten met onderbouwing; onbekend blijft onbekend | Gereed | A, H |
| Wat-als-simulator: hypothetische voorwaarden/premie, effect op scores en ranglijst; niets wordt opgeslagen | Gereed | A |
| Concurrentiekaart per aanbieder (prijsniveau, sterke/zwakke punten, tegenargumenten, gespreksvragen), afdrukbaar | Gereed | A, H |
| Tijdlijn per aanbieder (documenten, wijzigingen, premies, bevindingen, status) met filters | Gereed | A, H |
| Marktbericht: automatisch na elke broncontrole, ook als rapport (PDF/Excel) | Gereed | A |
| Automatisch onderzoek per aanbieder: AI-webonderzoek beperkt tot het officiële domein, server haalt pagina's en PDF's op (robots.txt), premie-indicaties alleen als het bedrag letterlijk op de pagina staat, gebruiker kiest wat wordt geïmporteerd, daarna optioneel AI-analyse van alle nieuwe documenten | Gereed | A (gesimuleerde AI en website), X (echte websites) |
| Snelzoeken (Ctrl+K / ⌘K) over aanbieders, producten, documenten, clausules en volledige tekst | Gereed | A |

---

## Bekende beperkingen en openstaande punten

1. **Concurrentiegegevens zijn niet vooraf gevuld.** De startlijst uit de opdracht is opgenomen maar niet
   geverifieerd; of deze partijen relevante producten aanbieden, moet worden vastgesteld (handmatig of via AI-
   webonderzoek). Er zijn geen officiële logo's meegeleverd; deze worden per aanbieder opgehaald en goedgekeurd.
2. **Vetera-product en -voorwaarden** moeten zelf worden vastgelegd op basis van de actuele, openbare publicaties.
3. **Windows-scripts** zijn geschreven en gecontroleerd op syntaxis, maar konden in de Linux-bouwomgeving niet op
   Windows zelf worden uitgevoerd. De Python- en Node-onderdelen zijn platformonafhankelijk getest.
4. **Clausule- en documentherkenning is heuristisch.** Afwijkende opmaak kan tot minder herkende artikelen leiden;
   de tekst blijft per pagina doorzoekbaar en citeerbaar.
5. **OCR** vereist een lokale Tesseract-/Poppler-installatie en is niet in de standaardinstallatie opgenomen.
6. **AI-functies** zijn getest met een gesimuleerd model (validatie, blokkades, budget). Echte antwoorden vereisen
   een API-sleutel en internet; kwaliteit en kosten hangen af van model en hoeveelheid data.
7. **Kostenramingen** gebruiken de publieke lijstprijzen per model en een vaste USD→EUR-factor; de werkelijke
   factuur kan afwijken.
8. **Wijzigingsclassificatie** (dekkingsuitbreiding, nieuwe uitsluiting, …) is indicatief op basis van
   tekstpatronen en wordt als zodanig getoond; inhoudelijke beoordeling blijft nodig.
9. De PDF-viewer gebruikt de ingebouwde viewer van de browser (Edge/Chrome); de gemarkeerde passage staat in het
   tekstpaneel ernaast.
10. De applicatie is ontworpen voor één gebruiker op één computer; er is geen gebruikersbeheer.
