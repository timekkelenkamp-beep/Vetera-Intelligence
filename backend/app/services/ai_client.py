"""Claude-integratie (Anthropic API) met kostenlimieten, gebruiksregistratie en
privacybewaking.

- De API-sleutel blijft server-side (omgevingsvariabele of backend/.env).
- Iedere aanroep wordt vastgelegd in ``ai_analyses`` met tokens en kostenraming.
- Vóór verzending kan altijd een preview worden opgevraagd (``dry_run``).
- Externe AI-verzoeken gaan via internet naar Anthropic: de app is lokaal, de AI niet.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AIAnalysis
from .settings_store import get_setting

log = logging.getLogger("vetera.ai")

# Prijzen per miljoen tokens (USD, list price). Wordt gebruikt als kostenraming.
MODEL_PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-2": (8.0, 40.0),
}
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2"}
WEB_SEARCH_COST_PER_USE = 0.01
USD_TO_EUR = 0.92
AVAILABLE_MODELS = list(MODEL_PRICES)


class AIUnavailable(Exception):
    """AI niet geconfigureerd of uitgeschakeld."""


class AIBlocked(Exception):
    """Verzoek geblokkeerd (budget, privacy)."""


class AIFailed(Exception):
    pass


def ai_status(db: Session) -> dict:
    key = get_settings().resolved_api_key()
    enabled = bool(get_setting(db, "ai_enabled", True))
    month_cost = month_spend(db)
    budget = float(get_setting(db, "ai_monthly_budget_eur", 25.0) or 0)
    return {
        "configured": bool(key),
        "enabled": enabled,
        "available": bool(key) and enabled,
        "model": get_setting(db, "ai_model", "claude-opus-5-5"),
        "effort": get_setting(db, "ai_effort", "medium"),
        "month_spend_eur": round(month_cost, 4),
        "monthly_budget_eur": budget,
        "web_research": bool(get_setting(db, "ai_web_research", False)),
        "allow_nonpublic": bool(get_setting(db, "ai_allow_nonpublic", False)),
        "message": None if key else "Geen Anthropic API-sleutel ingesteld. Basisfuncties werken zonder AI; "
                                    "zet ANTHROPIC_API_KEY in backend/.env om AI-functies te gebruiken.",
    }


def month_spend(db: Session) -> float:
    start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return float(db.scalar(select(func.coalesce(func.sum(AIAnalysis.cost_estimate), 0.0))
                           .where(AIAnalysis.created_at >= start)) or 0.0)


def estimate_tokens(text: str) -> int:
    return int(len(text) / 3.5) + 50


def estimate_cost(model: str, input_tokens: int, output_tokens: int, web_uses: int = 0) -> float:
    pin, pout = MODEL_PRICES.get(model, (5.0, 25.0))
    usd = input_tokens / 1e6 * pin + output_tokens / 1e6 * pout + web_uses * WEB_SEARCH_COST_PER_USE
    return round(usd * USD_TO_EUR, 4)


def build_preview(db: Session, kind: str, system: str, user_text: str, sent_summary: dict,
                  expected_output_tokens: int = 4000, web_search: bool = False) -> dict:
    model = get_setting(db, "ai_model", "claude-opus-5-5")
    tin = estimate_tokens(system + user_text)
    cost = estimate_cost(model, tin, expected_output_tokens, 5 if web_search else 0)
    return {
        "kind": kind, "model": model, "estimated_input_tokens": tin,
        "estimated_output_tokens": expected_output_tokens, "estimated_cost_eur": cost,
        "web_search": web_search, "sent": sent_summary, "characters": len(user_text),
        "destination": "Anthropic API (api.anthropic.com) — gegevens verlaten deze computer",
        "text_excerpt": user_text[:3000],
        "status": ai_status(db),
    }


def _check_budget(db: Session, est_cost: float) -> None:
    budget = float(get_setting(db, "ai_monthly_budget_eur", 25.0) or 0)
    max_req = float(get_setting(db, "ai_max_request_cost_eur", 2.0) or 0)
    if max_req and est_cost > max_req:
        raise AIBlocked(f"Geraamde kosten (€ {est_cost:.2f}) overschrijden de limiet per verzoek "
                        f"(€ {max_req:.2f}). Pas de limiet aan in Instellingen of verklein de selectie.")
    if budget and month_spend(db) + est_cost > budget:
        raise AIBlocked(f"Maandbudget voor AI (€ {budget:.2f}) zou worden overschreden.")


def run_structured(db: Session, *, kind: str, system: str, user_text: str, schema: dict,
                   sent_summary: dict, question: str | None = None, web_search: bool = False,
                   web_domains: list[str] | None = None,
                   max_tokens: int = 16000, documents: list[dict] | None = None) -> tuple[dict, AIAnalysis]:
    """Voer een Claude-verzoek uit met gestructureerde JSON-uitvoer."""
    status = ai_status(db)
    if not status["configured"]:
        raise AIUnavailable(status["message"])
    if not status["enabled"]:
        raise AIUnavailable("AI-functies zijn uitgeschakeld in Instellingen.")
    if web_search and not status["web_research"]:
        raise AIBlocked("Webonderzoek door AI is niet geactiveerd in Instellingen.")
    model = status["model"]
    _check_budget(db, estimate_cost(model, estimate_tokens(system + user_text), 4000, 5 if web_search else 0))

    import anthropic  # lazy import: app werkt zonder AI

    client = anthropic.Anthropic(api_key=get_settings().resolved_api_key(), max_retries=2, timeout=600)
    content: list[dict] = list(documents or [])
    if web_search:
        # Webzoekresultaten bevatten citaties; die combineren niet met een afgedwongen JSON-formaat.
        user_text = (user_text + "\n\nAntwoord uitsluitend met één JSON-object (zonder toelichting eromheen) "
                     "dat voldoet aan dit JSON-schema:\n" + json.dumps(schema, ensure_ascii=False))
    content.append({"type": "text", "text": user_text})
    output_config: dict[str, Any] = {"effort": status["effort"]}
    if not web_search:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    kwargs: dict[str, Any] = dict(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": content}],
        output_config=output_config,
    )
    if web_search:
        tool = {"type": "web_search_20260209", "name": "web_search", "max_uses": 8,
                "user_location": {"type": "approximate", "country": "NL"}}
        if web_domains:
            tool["allowed_domains"] = web_domains[:20]
        kwargs["tools"] = [tool]
    analysis = AIAnalysis(kind=kind, model=model, question=question, sent_summary=sent_summary)
    try:
        if model in FALLBACK_MODELS:
            resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                               **kwargs)
        else:
            resp = client.messages.create(**kwargs)
    except anthropic.AuthenticationError as exc:
        analysis.status, analysis.error = "fout", "Ongeldige API-sleutel"
        db.add(analysis); db.commit()
        raise AIFailed("De Anthropic API-sleutel is ongeldig.") from exc
    except anthropic.RateLimitError as exc:
        analysis.status, analysis.error = "fout", "Rate limit"
        db.add(analysis); db.commit()
        raise AIFailed("Te veel verzoeken; probeer het over enkele minuten opnieuw.") from exc
    except anthropic.APIStatusError as exc:
        analysis.status, analysis.error = "fout", f"API-fout {exc.status_code}"
        db.add(analysis); db.commit()
        raise AIFailed(f"De AI-dienst gaf een fout ({exc.status_code}).") from exc
    except anthropic.APIConnectionError as exc:
        analysis.status, analysis.error = "fout", "Verbindingsfout"
        db.add(analysis); db.commit()
        raise AIFailed("Geen verbinding met de AI-dienst. Controleer de internetverbinding.") from exc

    usage = resp.usage
    web_uses = 0
    try:
        web_uses = int(getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0)
    except Exception:
        web_uses = 0
    analysis.input_tokens = int(usage.input_tokens or 0) + int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    analysis.output_tokens = int(usage.output_tokens or 0)
    analysis.cost_estimate = estimate_cost(model, analysis.input_tokens, analysis.output_tokens, web_uses)
    if resp.stop_reason == "refusal":
        analysis.status, analysis.error = "geweigerd", "Verzoek geweigerd door het model"
        db.add(analysis); db.commit()
        raise AIFailed("Het AI-model heeft dit verzoek niet uitgevoerd.")
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    citations_urls = []
    for b in resp.content:
        if getattr(b, "type", None) == "web_search_tool_result" and isinstance(getattr(b, "content", None), list):
            for r in b.content:
                url = getattr(r, "url", None)
                if url:
                    citations_urls.append({"url": url, "title": getattr(r, "title", None)})
    try:
        data = parse_json_text(text)
    except json.JSONDecodeError as exc:
        analysis.status, analysis.error = "fout", "Ongeldige JSON in antwoord"
        db.add(analysis); db.commit()
        if resp.stop_reason == "max_tokens":
            raise AIFailed("Het AI-antwoord was te lang en is afgebroken. Verklein de vraag of selectie.") from exc
        raise AIFailed("Het AI-antwoord kon niet worden verwerkt.") from exc
    if citations_urls:
        data["_web_results"] = citations_urls[:40]
    analysis.response = data
    analysis.status = "voltooid"
    db.add(analysis)
    db.commit()
    return data, analysis


def parse_json_text(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if "```" in text:
        for part in text.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                try:
                    return json.loads(part)
                except json.JSONDecodeError:
                    continue
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    raise json.JSONDecodeError("geen JSON", text, 0)


def obj(props: dict, required: list[str] | None = None) -> dict:
    """JSON-schema object met verplichte velden en zonder extra velden (structured outputs)."""
    return {"type": "object", "properties": props, "required": required or list(props),
            "additionalProperties": False}


def arr(items: dict) -> dict:
    return {"type": "array", "items": items}


STR = {"type": "string"}
INT = {"type": "integer"}
