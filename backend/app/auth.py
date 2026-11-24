"""Eenvoudige, veilige toegang met één wachtwoord voor online gebruik.

- Alleen actief als VETERA_ALLOW_REMOTE_ACCESS=true (lokaal gebruik blijft zonder wachtwoord,
  beschermd doordat de server alleen op 127.0.0.1 luistert).
- Faalt dicht: online zonder wachtwoord of sessiegeheim wordt alle toegang geweigerd.
- Sessie = ondertekende cookie (HMAC-SHA256), HttpOnly, Secure, SameSite=Lax.
- Beperking van inlogpogingen per IP-adres.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request, Response

from .config import get_settings

COOKIE = "vi_session"
PUBLIC_API = {"/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/logout"}
_attempts: dict[str, deque] = defaultdict(deque)
MAX_ATTEMPTS, WINDOW_S = 8, 300

router = APIRouter(prefix="/api/auth", tags=["toegang"])


def configured() -> bool:
    s = get_settings()
    return bool(s.app_password and s.session_secret and len(s.session_secret) >= 16)


def _sign(payload: str) -> str:
    key = get_settings().session_secret.encode()
    return base64.urlsafe_b64encode(hmac.new(key, payload.encode(), hashlib.sha256).digest()).decode().rstrip("=")


def make_token() -> str:
    # Het wachtwoord zit in de handtekening: na wijziging van het wachtwoord vervallen oude sessies.
    pw = hashlib.sha256((get_settings().app_password or "").encode()).hexdigest()[:16]
    exp = str(int(time.time()) + get_settings().session_days * 86400)
    return f"{exp}.{_sign(exp + '.' + pw)}"


def valid_token(token: str | None) -> bool:
    if not token or not configured() or "." not in token:
        return False
    exp, sig = token.split(".", 1)
    if not exp.isdigit() or int(exp) < time.time():
        return False
    pw = hashlib.sha256((get_settings().app_password or "").encode()).hexdigest()[:16]
    return hmac.compare_digest(sig, _sign(exp + "." + pw))


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


def is_authenticated(request: Request) -> bool:
    return valid_token(request.cookies.get(COOKIE))


@router.get("/status")
def status(request: Request):
    s = get_settings()
    return {"cloud": s.cloud, "required": s.cloud, "configured": configured() if s.cloud else True,
            "authenticated": (not s.cloud) or is_authenticated(request)}


@router.post("/login")
def login(data: dict, request: Request, response: Response):
    s = get_settings()
    if not s.cloud:
        return {"ok": True}
    if not configured():
        raise HTTPException(503, "Inloggen is niet ingesteld. Zet VETERA_APP_PASSWORD en VETERA_SESSION_SECRET op de server.")
    ip = client_ip(request)
    q = _attempts[ip]
    now = time.time()
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if len(q) >= MAX_ATTEMPTS:
        raise HTTPException(429, "Te veel inlogpogingen. Probeer het over een paar minuten opnieuw.")
    pw = str(data.get("password") or "")
    if not hmac.compare_digest(pw.encode(), (s.app_password or "").encode()):
        q.append(now)
        time.sleep(0.5)
        raise HTTPException(401, "Onjuist wachtwoord.")
    q.clear()
    response.set_cookie(COOKIE, make_token(), max_age=s.session_days * 86400, httponly=True, secure=True,
                        samesite="lax", path="/")
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}
