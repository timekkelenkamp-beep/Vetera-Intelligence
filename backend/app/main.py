"""FastAPI-applicatie. Draait standaard op http://127.0.0.1:3000 en serveert ook de frontend."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import PROJECT_DIR, get_settings
from .routers import ai, compare, documents, premiums, products, providers, radar, reports, sources, system
from .services.migrate import upgrade_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vetera")

FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    upgrade_database()
    from .routers.system import fix_paths
    fix_paths()
    log.info("Vetera Intelligence %s gestart; data in %s", __version__, get_settings().data_dir)
    yield


app = FastAPI(title="Vetera Intelligence", version=__version__, lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.middleware("http")
async def local_only(request: Request, call_next):
    """Voorkom toegang via andere hostnamen (DNS-rebinding) en via het netwerk."""
    s = get_settings()
    if not s.allow_remote_access:
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].lower()
        client = request.client.host if request.client else ""
        if host not in ALLOWED_HOSTS or client not in ("127.0.0.1", "::1", "testclient", "localhost"):
            return JSONResponse({"detail": "Alleen lokale toegang toegestaan"}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/") and not request.url.path.endswith(("/file", "/logo")):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # Log zonder gevoelige inhoud (geen request body)
    log.error("Onverwachte fout bij %s %s: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse({"detail": "Er ging iets mis aan de serverkant. Details staan in het logbestand."},
                        status_code=500)


for r in (providers, products, documents, compare, premiums, sources, ai, radar, reports, system):
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
