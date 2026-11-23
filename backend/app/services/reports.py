"""Rapportages: inhoud wordt uitsluitend uit de database samengesteld en
vervolgens gerenderd als PDF (reportlab), Excel (openpyxl) en printweergave."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (Document, DocumentDiff, DocumentVersion, ImprovementSuggestion, MonitorRun, Notification,
                      Product, Provider, ReferenceProfile, Report, ResearchDossier, SalesCard, ScoreProfile)
from .analysis import compute_scores, local_sales_card, matrix, product_label
from .common import FINDING_STATUSES
from .premiums import compare_profile

REPORT_TYPES = {
    "concurrentievergelijking": "Complete concurrentievergelijking",
    "voorwaarden": "Voorwaardenanalyse",
    "premie": "Premieanalyse",
    "markt": "Marktontwikkelingen",
    "radar": "Verbeterradar-rapport",
    "dossier": "Verdiepend marktonderzoek",
    "verkoop": "Verkoopargumenten per concurrent",
    "marktbericht": "Marktbericht",
}
STANDARD_LIMITATIONS = [
    "Uitsluitend gebaseerd op gegevens die in Vetera Intelligence zijn vastgelegd op de rapportagedatum.",
    "Onderdelen met status 'niet gevonden' of 'onvoldoende informatie' zijn niet als voor- of nadeel meegewogen.",
    "Automatisch of door AI vastgestelde bevindingen zonder menselijke controle zijn als zodanig gemarkeerd.",
]


def _eur(v):
    return "–" if v is None else f"€ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _products(db: Session, ids: list[int] | None) -> list[Product]:
    if ids:
        return [p for p in (db.get(Product, i) for i in ids) if p]
    return db.scalars(select(Product).join(Provider, Product.provider_id == Provider.id)
                      .where(Provider.status == "actief", Product.canonical_product_id.is_(None))).all()


def _reference(db: Session, products: list[Product]) -> Product | None:
    for p in products:
        if db.get(Provider, p.provider_id).is_reference:
            return p
    return None


def _matrix_section(db: Session, products: list[Product], ref: Product | None, sources: list) -> tuple[dict, list[str]]:
    m = matrix(db, [p.id for p in products], ref.id if ref else None)
    cols = ["Rubriek", "Kenmerk"] + [f"{p['provider_name']} – {p['name']}" for p in m["products"]]
    rows, summary = [], []
    diffs_comp, diffs_ref = 0, 0
    for r in m["rows"]:
        row = [r["feature"]["category"], r["feature"]["label"]]
        for p in m["products"]:
            c = r["cells"].get(str(p["id"]))
            if c:
                cell = FINDING_STATUSES.get(c["status"], c["status"])
                if c.get("value_text"):
                    cell += f" – {c['value_text']}"
                if c.get("page_number") and c.get("document"):
                    ref_txt = f"{c['document']['title']}, p.{c['page_number']}" + (f", art. {c['article']}" if c.get("article") else "")
                    cell += f" [{len(sources) + 1}]"
                    sources.append(ref_txt)
                if c["review_status"] not in ("goedgekeurd", "gecorrigeerd"):
                    cell += " (ongecontroleerd)"
            else:
                cell = "Geen gegevens"
            row.append(cell)
        for d in r["differences"].values():
            if d["kind"] == "concurrent_ruimer":
                diffs_comp += 1
            elif d["kind"] == "referentie_ruimer":
                diffs_ref += 1
        rows.append(row)
    if ref:
        summary.append(f"Op {diffs_ref} kenmerk-vergelijkingen biedt Vetera aantoonbaar een ruimere regeling; "
                       f"op {diffs_comp} vergelijkingen is een concurrent aantoonbaar ruimer.")
    unknown = sum(1 for r in m["rows"] if r["has_unknown"])
    summary.append(f"Bij {unknown} van {len(m['rows'])} kenmerken ontbreekt voor minstens één product een "
                   "vastgestelde regeling.")
    return {"heading": "Voorwaardenvergelijking", "paragraphs": [
        "Statussen per kenmerk met bronverwijzing. Verschillen worden alleen benoemd als beide regelingen "
        "aantoonbaar zijn vastgesteld."], "tables": [{"columns": cols, "rows": rows}]}, summary


def _premium_section(db: Session, profile_ids: list[int] | None) -> tuple[dict, list[str]]:
    profiles = [db.get(ReferenceProfile, i) for i in profile_ids] if profile_ids else db.scalars(select(ReferenceProfile)).all()
    tables, summary, charts = [], [], []
    for prof in [p for p in profiles if p]:
        c = compare_profile(db, prof.id)
        if not c["rows"]:
            continue
        rows = [[r["provider_name"], r["product_name"] or "–", r["coverage_variant"] or "–", _eur(r["deductible"]),
                 _eur(r["annual_premium"]), _eur(r["total_annual_cost"]),
                 "–" if r["diff_pct"] is None else f"{r['diff_pct']:+.1f}%", r["observation_type_label"],
                 r["reference_date"] or "–", "; ".join(r["comparability_issues"]) or ("Basis" if r["is_baseline"] else "Vergelijkbaar")]
                for r in c["rows"]]
        tables.append({"title": f"Profiel: {prof.name}", "columns": ["Aanbieder", "Product", "Dekking", "Eigen risico",
                                                                    "Jaarpremie", "Totale jaarlast", "Verschil",
                                                                    "Type", "Peildatum", "Vergelijkbaarheid"],
                       "rows": rows})
        charts.append({"title": prof.name, "labels": [r["provider_name"] for r in c["rows"]],
                       "values": [r["total_annual_cost"] or 0 for r in c["rows"]]})
        comparable = [r for r in c["rows"] if r["fully_comparable"] or r["is_baseline"]]
        summary.append(f"{prof.name}: {len(c['rows'])} premies vastgelegd, waarvan {len(comparable)} volledig "
                       f"vergelijkbaar met de basis ({c['baseline_note']})")
    if not tables:
        summary.append("Er zijn nog geen premies vastgelegd voor de gekozen profielen.")
    return {"heading": "Premieanalyse", "paragraphs": [
        "Per rekenprofiel de meest recente actuele waarneming per aanbieder/product. Historische tarieven zijn "
        "uitgesloten. Afwijkingen in dekking, eigen risico, belasting of peildatum worden expliciet vermeld."],
        "tables": tables, "charts": charts}, summary


def build_content(db: Session, report_type: str, params: dict) -> dict:
    if report_type not in REPORT_TYPES:
        raise ValueError("Onbekend rapporttype")
    products = _products(db, params.get("product_ids"))
    ref = _reference(db, products)
    sources: list[str] = []
    sections, summary = [], []
    limitations = list(STANDARD_LIMITATIONS)
    title = params.get("title") or REPORT_TYPES[report_type]

    if report_type in ("concurrentievergelijking", "voorwaarden"):
        sec, s = _matrix_section(db, products, ref, sources)
        sections.append(sec)
        summary += s
        if not ref:
            limitations.append("Er is geen Vetera-product geselecteerd; verschillen zijn niet ten opzichte van Vetera bepaald.")
    if report_type in ("concurrentievergelijking", "premie"):
        sec, s = _premium_section(db, params.get("profile_ids"))
        sections.append(sec)
        summary += s
        limitations.append("Premies zijn momentopnames; getoonde premies zijn geen uitgebrachte offertes tenzij vermeld.")
    if report_type == "concurrentievergelijking":
        sp = db.get(ScoreProfile, params.get("score_profile_id")) if params.get("score_profile_id") else \
            db.scalars(select(ScoreProfile)).first()
        if sp:
            sc = compute_scores(db, sp, [p.id for p in products])
            aspects = list(sp.weights)
            rows = [[f"{r['product']['provider_name']} – {r['product']['name']}"] +
                    [("–" if r["aspects"].get(a, {}).get("score") is None else f"{r['aspects'][a]['score']:.0f}") for a in aspects] +
                    ["–" if r["total"] is None else f"{r['total']:.0f}"] for r in sc["results"]]
            sections.append({"heading": f"Scores (profiel '{sp.name}')", "paragraphs": [sc["method"],
                             "Wegingen: " + ", ".join(f"{k} {v}%" for k, v in sp.weights.items())],
                             "tables": [{"columns": ["Product"] + [a.capitalize() for a in aspects] + ["Totaal"], "rows": rows}]})
        prov_rows = [[p.name, p.provider_type, p.status, p.website or "–", str(len(p.products))]
                     for p in db.scalars(select(Provider).where(Provider.status.in_(["actief", "te_beoordelen"])))]
        sections.insert(0, {"heading": "Onderzochte aanbieders", "paragraphs": [],
                            "tables": [{"columns": ["Aanbieder", "Type", "Status", "Website", "Producten"], "rows": prov_rows}]})
    if report_type == "markt":
        days = int(params.get("days") or 90)
        since = datetime.now() - timedelta(days=days)
        diffs = db.scalars(select(DocumentDiff).where(DocumentDiff.created_at >= since)).all()
        rows = []
        for d in diffs:
            doc = db.get(Document, d.document_id)
            for c in (d.changes or [])[:40]:
                if c["category"] == "redactioneel":
                    continue
                rows.append([doc.title if doc else "?", d.created_at.date().isoformat(), c["category_label"],
                             (c["old"] or "–")[:250], (c["new"] or "–")[:250]])
        sections.append({"heading": f"Documentwijzigingen (laatste {days} dagen)", "paragraphs": [
            "Classificatie is automatisch en indicatief; zie de marktmonitor voor de volledige vergelijking."],
            "tables": [{"columns": ["Document", "Datum", "Soort", "Oud", "Nieuw"], "rows": rows}]})
        notes = db.scalars(select(Notification).where(Notification.created_at >= since,
                                                      Notification.type != "systeem")).all()
        sections.append({"heading": "Meldingen", "paragraphs": [], "tables": [{
            "columns": ["Datum", "Soort", "Titel"],
            "rows": [[n.created_at.date().isoformat(), n.type, n.title] for n in notes]}]})
        runs = db.scalars(select(MonitorRun).where(MonitorRun.started_at >= since)).all()
        summary.append(f"{len(diffs)} documentvergelijkingen, {len(rows)} niet-redactionele wijzigingen en "
                       f"{len(notes)} meldingen in de afgelopen {days} dagen; {len(runs)} broncontroles uitgevoerd.")
        products = []
    if report_type == "radar":
        sugg = db.scalars(select(ImprovementSuggestion).where(ImprovementSuggestion.status != "afgewezen")).all()
        order = {"hoog": 0, "middel": 1, "laag": 2}
        sugg.sort(key=lambda s: order.get(s.priority, 3))
        for s in sugg:
            sections.append({"heading": f"{s.title}", "paragraphs": [
                f"{'INNOVATIEHYPOTHESE – geen bewezen marktkans. ' if s.kind == 'innovatiehypothese' else ''}"
                f"Categorie: {s.category} · Prioriteit: {s.priority} · Betrouwbaarheid: {s.confidence} · Status: {s.status}",
                f"Samenvatting: {s.summary or '–'}", f"Geconstateerde kans/tekortkoming: {s.gap or '–'}",
                f"Huidige Vetera-situatie: {s.vetera_situation or '–'}", f"Markt/concurrentie: {s.market_context or '–'}",
                f"Suggestie: {s.suggestion or '–'}", f"Klantvoordelen: {s.customer_benefits or '–'}",
                f"Commerciële voordelen: {s.commercial_benefits or '–'}", f"Risico's: {s.risks or '–'}",
                f"Vervolgonderzoek: {s.follow_up or '–'}",
                "Onderbouwing: " + ("; ".join(e.get("label") or e.get("ref") or e.get("url") or e.get("type", "")
                                              for e in (s.evidence or [])) or "geen bronverwijzingen")]})
        summary.append(f"{len(sugg)} verbetervoorstellen, waarvan {sum(1 for s in sugg if s.priority == 'hoog')} met "
                       f"prioriteit hoog en {sum(1 for s in sugg if s.kind == 'innovatiehypothese')} innovatiehypotheses.")
        limitations.append("Verbetervoorstellen zijn suggesties voor doorontwikkeling, geen bestaande productvoorwaarden.")
        products = []
    if report_type == "dossier":
        ids = params.get("dossier_ids") or []
        dossiers = [db.get(ResearchDossier, i) for i in ids] if ids else db.scalars(select(ResearchDossier)).all()
        for d in [x for x in dossiers if x]:
            c = d.content or {}
            paras = [f"Achtergrond: {c.get('background', '–')}", f"Concurrentieanalyse: {c.get('competitive_analysis', '–')}",
                     f"Doelgroep: {c.get('target_group', '–')}"]
            for key, lbl in (("product_adjustments", "Mogelijke productaanpassingen"), ("commercial_opportunities", "Commerciële kansen"),
                             ("risks", "Risico's"), ("open_questions", "Openstaande vragen"), ("next_steps", "Vervolgstappen"),
                             ("uncertainties", "Onzekerheden")):
                if c.get(key):
                    paras.append(f"{lbl}: " + "; ".join(c[key]))
            tables = []
            if c.get("market_figures"):
                tables.append({"columns": ["Marktcijfer", "Bron"], "rows": [[m["figure"], m["source"]] for m in c["market_figures"]]})
            sections.append({"heading": d.title, "paragraphs": paras, "tables": tables})
            sources += [s.get("ref", "") + (f" – {s['note']}" if s.get("note") else "") for s in c.get("sources", [])]
        summary.append(f"{len([x for x in dossiers if x])} onderzoeksdossier(s).")
        limitations.append("Dossiers zijn met AI samengesteld; marktcijfers zijn alleen opgenomen met bron.")
        products = []
    if report_type == "marktbericht":
        from .insights import market_brief
        since = datetime.fromisoformat(params["since"]) if params.get("since") else None
        until = datetime.fromisoformat(params["until"]) if params.get("until") else None
        b = market_brief(db, since, until)
        title = params.get("title") or f"Marktbericht {date.fromisoformat(b['period']['to'][:10]).strftime('%d-%m-%Y')}"
        summary += b["headline"]
        sections.append({"heading": "Gewijzigde polisvoorwaarden", "paragraphs": [] if b["changes"] else
                         ["Geen inhoudelijke wijzigingen in deze periode."], "tables": [{
                             "columns": ["Aanbieder", "Document", "Wijzigingen", "Soort", "Voorbeeld"],
                             "rows": [[c["provider"], c["document"], str(c["count"]), ", ".join(c["categories"]),
                                       c["examples"][0]["new"] if c["examples"] else ""] for c in b["changes"]]}]
                         if b["changes"] else []})
        if b["new_providers"]:
            sections.append({"heading": "Nieuwe aanbieders", "paragraphs": [f"{p['name']} (status: {p['status']})" for p in b["new_providers"]]})
        if b["price_signals"]:
            sections.append({"heading": "Premiesignalen", "paragraphs": b["price_signals"]})
        if b["unavailable_sources"]:
            sections.append({"heading": "Niet bereikbare bronnen", "paragraphs": b["unavailable_sources"]})
        if b["suggestions"]:
            sections.append({"heading": "Nieuwe verbetervoorstellen", "paragraphs": [
                f"{s['title']}{' (innovatiehypothese)' if s['kind'] == 'innovatiehypothese' else ''}" for s in b["suggestions"]]})
        limitations.append(f"Periode {b['period']['from'][:16].replace('T', ' ')} t/m {b['period']['to'][:16].replace('T', ' ')}; "
                           f"{b['checks']} broncontrole(s). Classificatie van wijzigingen is indicatief.")
        products = []
        params = {**params, "brief": b}
    if report_type == "verkoop":
        comp_id = params.get("competitor_product_id")
        vet_id = params.get("vetera_product_id") or (ref.id if ref else None)
        if not comp_id or not vet_id:
            raise ValueError("Kies een Vetera-product en een concurrentproduct.")
        card = db.scalars(select(SalesCard).where(SalesCard.competitor_product_id == comp_id,
                                                  SalesCard.vetera_product_id == vet_id)
                          .order_by(SalesCard.created_at.desc())).first()
        content = card.content if card else local_sales_card(db, db.get(Product, vet_id), db.get(Product, comp_id))
        title = content.get("title", title)
        args = content.get("arguments", [])
        sections.append({"heading": "Argumenten", "paragraphs": [], "tables": [{
            "columns": ["Feitelijk verschil", "Klantvoordeel", "Mogelijk verkoopargument"],
            "rows": [[a.get("fact", ""), a.get("customer_benefit", ""), a.get("sales_argument", "")] for a in args]}]})
        sections.append({"heading": "Aandachtspunten en beperkingen van Vetera", "paragraphs":
                         [s if isinstance(s, str) else s.get("text", "") for s in content.get("vetera_limitations", [])] or
                         ["Geen aantoonbare nadelen vastgesteld op basis van de beschikbare gegevens."]})
        sections.append({"heading": "Vragen voor de adviseur", "paragraphs": content.get("advisor_questions", [])})
        summary.append(f"{len(args)} onderbouwde argumenten; {len(content.get('competitor_strengths', []))} punten "
                       "waarop de concurrent aantoonbaar gunstiger is.")
        products = [db.get(Product, vet_id), db.get(Product, comp_id)]
    return {"title": title, "report_type": report_type, "type_label": REPORT_TYPES[report_type],
            "date": date.today().isoformat(),
            "products": [f"{product_label(db, p)['provider_name']} – {p.name}" for p in products if p],
            "management_summary": summary, "sections": sections, "sources": sources,
            "limitations": limitations}


# ---------------------------------------------------------------- PDF
def render_pdf(content: dict, path: Path) -> None:
    from reportlab.graphics.charts.barcharts import HorizontalBarChart
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    ACCENT = colors.HexColor("#1F4E46")
    INK = colors.HexColor("#1d1d1f")
    MUTED = colors.HexColor("#6e6e73")
    LINE = colors.HexColor("#e5e5ea")
    ss = getSampleStyleSheet()
    st = {
        "title": ParagraphStyle("t", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=24, textColor=INK,
                                alignment=TA_LEFT, spaceAfter=6),
        "sub": ParagraphStyle("s", parent=ss["Normal"], fontSize=10, textColor=MUTED, spaceAfter=14),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=14, textColor=INK,
                             spaceBefore=14, spaceAfter=6),
        "h3": ParagraphStyle("h3", parent=ss["Heading3"], fontSize=11, textColor=ACCENT, spaceBefore=8, spaceAfter=4),
        "p": ParagraphStyle("p", parent=ss["Normal"], fontSize=9.5, leading=13.5, textColor=INK, spaceAfter=5),
        "cell": ParagraphStyle("c", parent=ss["Normal"], fontSize=7.5, leading=9.5, textColor=INK),
        "cellh": ParagraphStyle("ch", parent=ss["Normal"], fontSize=7.5, leading=9.5, textColor=colors.white,
                                fontName="Helvetica-Bold"),
        "small": ParagraphStyle("sm", parent=ss["Normal"], fontSize=8, leading=10.5, textColor=MUTED),
    }

    def esc(s):
        return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    wide = any(len(t["columns"]) > 6 for s in content["sections"] for t in s.get("tables", []))
    pagesize = landscape(A4) if wide else A4

    def on_page(c, d):
        c.saveState()
        c.setFillColor(ACCENT)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(18 * mm, pagesize[1] - 12 * mm, "Vetera Intelligence")
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawRightString(pagesize[0] - 18 * mm, pagesize[1] - 12 * mm, content["type_label"])
        c.drawString(18 * mm, 10 * mm, f"Gegenereerd op {content['date']} · uitsluitend op basis van vastgelegde gegevens")
        c.drawRightString(pagesize[0] - 18 * mm, 10 * mm, f"Pagina {d.page}")
        c.setStrokeColor(LINE)
        c.line(18 * mm, pagesize[1] - 14 * mm, pagesize[0] - 18 * mm, pagesize[1] - 14 * mm)
        c.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=pagesize, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=22 * mm, bottomMargin=18 * mm, title=content["title"], author="Vetera Intelligence")
    width = pagesize[0] - 36 * mm
    story = [Paragraph(esc(content["title"]), st["title"]),
             Paragraph(f"{esc(content['type_label'])} · Onderzoeksdatum {content['date']}", st["sub"])]
    if content["products"]:
        story.append(Paragraph("<b>Onderzochte producten:</b> " + esc(", ".join(content["products"])), st["p"]))
    story.append(Paragraph("Managementsamenvatting", st["h2"]))
    for s in content["management_summary"] or ["Geen kernconclusies: onvoldoende gegevens."]:
        story.append(Paragraph("• " + esc(s), st["p"]))

    def table(t):
        cols = t["columns"]
        data = [[Paragraph(esc(c), st["cellh"]) for c in cols]]
        for r in t["rows"]:
            data.append([Paragraph(esc(c), st["cell"]) for c in r])
        if len(data) == 1:
            data.append([Paragraph("Geen gegevens", st["cell"])] + [""] * (len(cols) - 1))
        tb = Table(data, colWidths=[width / len(cols)] * len(cols), repeatRows=1)
        tb.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ACCENT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f7")]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE), ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        return tb

    for sec in content["sections"]:
        story.append(Paragraph(esc(sec["heading"]), st["h2"]))
        for p in sec.get("paragraphs", []):
            story.append(Paragraph(esc(p), st["p"]))
        for t in sec.get("tables", []):
            if t.get("title"):
                story.append(Paragraph(esc(t["title"]), st["h3"]))
            story.append(table(t))
            story.append(Spacer(1, 6))
        for ch in sec.get("charts", []):
            if not ch["values"]:
                continue
            h = 30 + 16 * len(ch["values"])
            dr = Drawing(width, h)
            bc = HorizontalBarChart()
            bc.x, bc.y, bc.width, bc.height = 120, 10, width - 160, h - 20
            bc.data = [list(reversed(ch["values"]))]
            bc.categoryAxis.categoryNames = list(reversed(ch["labels"]))
            bc.categoryAxis.labels.fontSize = 7
            bc.valueAxis.labels.fontSize = 7
            bc.valueAxis.valueMin = 0
            bc.bars[0].fillColor = ACCENT
            bc.bars[0].strokeColor = None
            dr.add(bc)
            story.append(KeepTogether([Paragraph(f"Totale jaarlast – {esc(ch['title'])}", st["h3"]), dr]))
    story.append(PageBreak())
    story.append(Paragraph("Bronverwijzingen", st["h2"]))
    for i, s in enumerate(content["sources"], 1):
        story.append(Paragraph(f"[{i}] {esc(s)}", st["small"]))
    if not content["sources"]:
        story.append(Paragraph("Geen documentverwijzingen in dit rapport.", st["small"]))
    story.append(Paragraph("Beperkingen en onzekerheden", st["h2"]))
    for s in content["limitations"]:
        story.append(Paragraph("• " + esc(s), st["p"]))
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)


# ---------------------------------------------------------------- Excel
def render_xlsx(content: dict, path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Samenvatting"
    hdr = PatternFill("solid", fgColor="1F4E46")
    ws["A1"] = content["title"]
    ws["A1"].font = Font(size=16, bold=True)
    ws["A2"] = f"{content['type_label']} · Onderzoeksdatum {content['date']}"
    ws["A4"] = "Onderzochte producten"
    ws["A4"].font = Font(bold=True)
    ws["B4"] = ", ".join(content["products"]) or "–"
    r = 6
    ws.cell(r, 1, "Managementsamenvatting").font = Font(bold=True)
    for s in content["management_summary"]:
        r += 1
        ws.cell(r, 1, s)
    r += 2
    ws.cell(r, 1, "Beperkingen").font = Font(bold=True)
    for s in content["limitations"]:
        r += 1
        ws.cell(r, 1, s)
    ws.column_dimensions["A"].width = 100
    used = set()
    for sec in content["sections"]:
        for ti, t in enumerate(sec.get("tables", [])):
            name = (t.get("title") or sec["heading"])[:28]
            base, k = "".join(c for c in name if c not in "[]:*?/\\"), 1
            name = base
            while name in used:
                k += 1
                name = f"{base[:25]} {k}"
            used.add(name)
            sh = wb.create_sheet(name)
            for ci, c in enumerate(t["columns"], 1):
                cell = sh.cell(1, ci, c)
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = hdr
                sh.column_dimensions[get_column_letter(ci)].width = 28
            for ri, row in enumerate(t["rows"], 2):
                for ci, v in enumerate(row, 1):
                    sh.cell(ri, ci, v).alignment = Alignment(wrap_text=True, vertical="top")
            sh.freeze_panes = "A2"
        if not sec.get("tables") and sec.get("paragraphs"):
            name = sec["heading"][:28]
            name = "".join(c for c in name if c not in "[]:*?/\\")
            while name in used:
                name = name[:25] + "_"
            used.add(name)
            sh = wb.create_sheet(name)
            for i, p in enumerate(sec["paragraphs"], 1):
                sh.cell(i, 1, p).alignment = Alignment(wrap_text=True)
            sh.column_dimensions["A"].width = 120
    if content["sources"]:
        sh = wb.create_sheet("Bronnen")
        for i, s in enumerate(content["sources"], 1):
            sh.cell(i, 1, f"[{i}]")
            sh.cell(i, 2, s)
        sh.column_dimensions["B"].width = 100
    wb.save(path)


def generate(db: Session, report_type: str, params: dict) -> Report:
    content = build_content(db, report_type, params)
    rep = Report(report_type=report_type, title=content["title"], params=params, content=content)
    db.add(rep)
    db.flush()
    d = get_settings().reports_dir
    stem = f"rapport_{rep.id}_{report_type}_{date.today().isoformat()}"
    pdf, xlsx = d / f"{stem}.pdf", d / f"{stem}.xlsx"
    render_pdf(content, pdf)
    render_xlsx(content, xlsx)
    rep.file_pdf, rep.file_xlsx = str(pdf), str(xlsx)
    db.commit()
    return rep


def version_title(db: Session, version_id: int) -> str:
    v = db.get(DocumentVersion, version_id)
    doc = db.get(Document, v.document_id) if v else None
    return doc.title if doc else f"versie {version_id}"
