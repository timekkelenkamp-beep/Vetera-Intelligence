# Vetera Intelligence — notities voor verdere ontwikkeling

Lokaal concurrentie-intelligenceplatform (Nederlandstalig). Backend: Python/FastAPI/SQLAlchemy/Alembic/SQLite in
`backend/`. Frontend: React/TS/Vite/Tailwind/Radix in `frontend/`, gebouwd naar `frontend/dist` en geserveerd door
de backend op http://127.0.0.1:3000.

## Commando's
- Backend-tests: `cd backend && .venv/bin/python -m pytest -q` (Windows: `.venv\Scripts\python`)
- Typecheck/build frontend: `cd frontend && npm run build`
- E2E: `cd frontend && npx playwright test --trace off` (start zelf een backend op poort 3100 met tijdelijke data)
- Migratie maken: `cd backend && .venv/bin/alembic revision --autogenerate -m "..."` (env.py gebruikt render_as_batch)

## Harde regels (niet versoepelen)
- Nooit fictieve premies/voorwaarden in productiedata; seed bevat alleen rubrieken, voorbeeld-rekenprofielen
  (`is_example`) en een lege Vetera-referentie. Synthetische data alleen in tests (tijdelijke datamap).
- Ontbrekende passage ≠ niet verzekerd. AI-'uitgesloten' zonder geverifieerd citaat → `menselijke_beoordeling`.
- `Finding.locked` (menselijke invoer/goedkeuring) nooit overschrijven; nieuwe bevindingen = nieuwe rij, oude
  `is_current=False` + `superseded_by_id`.
- Niet-publieke data (`visibility="niet_publiek"`) niet naar AI zonder instelling `ai_allow_nonpublic` én
  `consent_nonpublic` per verzoek. Elke AI-taak ondersteunt `dry_run` (preview).
- Geen Vetera 2.0-product; ideeën alleen in de Verbeterradar (innovatiehypothese gelabeld).
- Webverzoeken via `services/monitor.py` (`validate_external_url`, robots.txt, vertraging). Geen CAPTCHA-omzeiling,
  geen proxies, geen geautomatiseerde offerteaanvragen. Calculator-connectors alleen per bron mét vastgelegde toestemming.
- Wijzigingen loggen met `services.common.audit` / `apply_updates`.

## Structuur
- `app/services/`: documents (PDF, clausules, citaatverificatie, diff), premiums (vergelijkbaarheid), excel_import,
  analysis (matrix, scores, lokale verkoopargumenten/radar), ai_client + ai_tasks (Claude, structured outputs,
  bronvalidatie), monitor, logos, quality, reports.
- `frontend/src/components/AiAction.tsx`: twee-staps AI (preview → bevestigen). Gebruik dit voor elke nieuwe AI-actie.
- Kleuren grafieken: `frontend/src/lib/chart.ts` (gevalideerd palet; kleur volgt entiteit).

## Online (Render)
- `Dockerfile` + `render.yaml`; online modus = `VETERA_ALLOW_REMOTE_ACCESS=true`. Dan staat alles onder `/api`
  (behalve `auth.PUBLIC_API`) achter de wachtwoordcookie (`app/auth.py`) en faalt de app dicht zonder wachtwoord.
- `VETERA_AUTO_MONITOR=true` start een uurlijkse controle in `main.lifespan` (geen Windows-taak in de cloud).
