"""FastAPI-applicatie. Draait standaard op http://127.0.0.1:3000 en serveert ook de frontend."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import PROJECT_DIR, get_settings
from . import auth
from .routers import ai, compare, documents, insights, premiums, products, providers, radar, reports, sources, system
from .services.migrate import upgrade_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vetera")

FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}


def _monitor_tick() -> None:
    from .db import SessionLocal
    from .models import MonitorRun
    from .services.monitor import run_monitor, schedule_status
    db = SessionLocal()
    try:
        if db.query(MonitorRun).filter(MonitorRun.status == "bezig").first():
            return
        if schedule_status(db)["overdue"]:
            log.info("Geplande broncontrole gestart")
            run_monitor(db, "gepland")
    except Exception:
        log.exception("Geplande broncontrole mislukt")
    finally:
        db.close()


async def _monitor_loop() -> None:
    """Online is er geen Windows Taakplanner: de server controleert zelf elk uur of een broncontrole nodig is."""
    await asyncio.sleep(60)
    while True:
        await asyncio.to_thread(_monitor_tick)
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    s = get_settings()
    upgrade_database()
    from .routers.system import fix_paths
    fix_paths()
    if s.cloud and not auth.configured():
        log.error("Online modus zonder VETERA_APP_PASSWORD/VETERA_SESSION_SECRET: alle toegang wordt geweigerd.")
    task = asyncio.create_task(_monitor_loop()) if s.auto_monitor else None
    log.info("Vetera Intelligence %s gestart (%s); data in %s", __version__, "online" if s.cloud else "lokaal", s.data_dir)
    yield
    if task:
        task.cancel()


app = FastAPI(title="Vetera Intelligence", version=__version__, lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.middleware("http")
async def access_control(request: Request, call_next):
    """Lokaal: alleen 127.0.0.1 en bekende hostnamen (tegen DNS-rebinding).
    Online: alles achter het wachtwoord, behalve de inlogpagina en de statusroutes."""
    s = get_settings()
    path = request.url.path
    if not s.cloud:
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].lower()
        client = request.client.host if request.client else ""
        if host not in ALLOWED_HOSTS or client not in ("127.0.0.1", "::1", "testclient", "localhost"):
            return JSONResponse({"detail": "Alleen lokale toegang toegestaan"}, status_code=403)
    elif path.startswith("/api/") and path not in auth.PUBLIC_API:
        if not auth.configured():
            return JSONResponse({"detail": "Deze installatie is online gezet zonder wachtwoord en is daarom geblokkeerd. "
                                           "Stel VETERA_APP_PASSWORD en VETERA_SESSION_SECRET in."}, status_code=503)
        if not auth.is_authenticated(request):
            return JSONResponse({"detail": "Log in om verder te gaan."}, status_code=401)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if s.cloud:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if path.startswith("/api/") and not path.endswith(("/file", "/logo")):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # Log zonder gevoelige inhoud (geen request body)
    log.error("Onverwachte fout bij %s %s: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse({"detail": "Er ging iets mis aan de serverkant. Details staan in het logbestand."},
                        status_code=500)


app.include_router(auth.router)
for r in (providers, products, documents, compare, premiums, sources, ai, radar, reports, system, insights):
    app.include_router(r.router)


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Niet gevonden"}, status_code=404)
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def no_frontend():
        return JSONResponse({"detail": "Frontend is nog niet gebouwd. Voer install.bat uit (of 'npm run build' in frontend/)."})
