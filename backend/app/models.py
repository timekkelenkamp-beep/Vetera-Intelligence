"""Relationeel datamodel van Vetera Intelligence.

Uitgangspunten:
- Historische gegevens worden nooit overschreven: nieuwe documentversies, nieuwe
  bevindingen en nieuwe premiewaarnemingen krijgen eigen records.
- Menselijke correcties (``locked``) worden niet door AI-analyses overschreven.
- Iedere bevinding verwijst waar mogelijk naar documentversie, pagina en artikel.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


# ---------------------------------------------------------------- Aanbieders
class Provider(TimestampMixin, Base):
    __tablename__ = "providers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    website: Mapped[str | None] = mapped_column(String(500))
    # verzekeraar | gevolmachtigde | tussenpersoon | distributeur | onbekend
    provider_type: Mapped[str] = mapped_column(String(40), default="onbekend")
    is_reference: Mapped[bool] = mapped_column(Boolean, default=False)  # Vetera
    # actief | te_beoordelen | afgewezen | samengevoegd
    status: Mapped[str] = mapped_column(String(30), default="te_beoordelen")
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id"))
    origin: Mapped[str] = mapped_column(String(30), default="handmatig")  # handmatig|startlijst|ontdekt
    description: Mapped[str | None] = mapped_column(Text)
    target_groups: Mapped[str | None] = mapped_column(Text)
    strengths: Mapped[str | None] = mapped_column(Text)
    weaknesses: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    verification_note: Mapped[str | None] = mapped_column(Text)
    logo_path: Mapped[str | None] = mapped_column(String(500))
    logo_status: Mapped[str] = mapped_column(String(20), default="geen")  # geen|kandidaat|goedgekeurd
    logo_source_url: Mapped[str | None] = mapped_column(String(1000))
    logo_auto: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # automatisch gekozen
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)

    products: Mapped[list[Product]] = relationship(back_populates="provider", foreign_keys="Product.provider_id", cascade="all, delete-orphan",
                                                   passive_deletes=True)


class RiskCarrier(TimestampMixin, Base):
    __tablename__ = "risk_carriers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    website: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    risk_carrier_id: Mapped[int | None] = mapped_column(ForeignKey("risk_carriers.id"))
    # Hetzelfde product dat via meerdere distributeurs loopt verwijst naar één canoniek product,
    # zodat het niet dubbel als concurrentieproduct wordt geteld.
    canonical_product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    name: Mapped[str] = mapped_column(String(300))
    vehicle_category: Mapped[str] = mapped_column(String(30), default="auto")  # auto|motor|bromfiets|meerdere
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(30), default="actief")  # actief|te_beoordelen|beeindigd
    notes: Mapped[str | None] = mapped_column(Text)

    provider: Mapped[Provider] = relationship(back_populates="products", foreign_keys=[provider_id])
    risk_carrier: Mapped[RiskCarrier | None] = relationship()


class ProductVersion(TimestampMixin, Base):
    __tablename__ = "product_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(100))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------- Bronnen & documenten
class Source(TimestampMixin, Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str | None] = mapped_column(String(1500))
    title: Mapped[str | None] = mapped_column(String(500))
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id", ondelete="SET NULL"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    # officieel_primair | openbaar_overig | handmatig | historisch | niet_geverifieerd
    source_type: Mapped[str] = mapped_column(String(30), default="niet_geverifieerd")
    document_type: Mapped[str | None] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(20), default="document")  # document|pagina|tarief|calculator
    published_at: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime)
    version_label: Mapped[str | None] = mapped_column(String(100))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    # toegestaan | onbekend | niet_toegestaan | robots_blokkeert
    access_status: Mapped[str] = mapped_column(String(30), default="onbekend")
    permission_note: Mapped[str | None] = mapped_column(Text)
    processing_status: Mapped[str] = mapped_column(String(30), default="nieuw")
    visibility: Mapped[str] = mapped_column(String(20), default="publiek")  # publiek|niet_publiek
    monitor_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_check_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_check_result: Mapped[str | None] = mapped_column(String(50))
    etag: Mapped[str | None] = mapped_column(String(200))
    last_modified: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id", ondelete="SET NULL"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    # polisvoorwaarden | verzekeringskaart | productinformatie | clausule |
    # aanvullende_voorwaarden | premietabel | overig
    document_type: Mapped[str] = mapped_column(String(50), default="overig")
    visibility: Mapped[str] = mapped_column(String(20), default="publiek")
    current_version_id: Mapped[int | None] = mapped_column(ForeignKey("document_versions.id", use_alter=True))
    identification: Mapped[dict | None] = mapped_column(JSON)  # automatische herkenning (kandidaten)

    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", foreign_keys="DocumentVersion.document_id",
        order_by="DocumentVersion.imported_at", cascade="all, delete-orphan", passive_deletes=True)


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_label: Mapped[str | None] = mapped_column(String(100))
    doc_date: Mapped[date | None] = mapped_column(Date)
    file_path: Mapped[str] = mapped_column(String(1000))
    original_filename: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(1500))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    extraction_quality: Mapped[str] = mapped_column(String(20), default="onbekend")  # goed|matig|onbetrouwbaar
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="verwerken")  # verwerken|gereed|fout
    error: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("document_versions.id"))

    document: Mapped[Document] = relationship(back_populates="versions", foreign_keys=[document_id])
    pages: Mapped[list[DocumentPage]] = relationship(back_populates="version", order_by="DocumentPage.page_number",
                                                     cascade="all, delete-orphan")
    clauses: Mapped[list[Clause]] = relationship(back_populates="version", order_by="Clause.order",
                                                 cascade="all, delete-orphan")


class DocumentPage(Base):
    __tablename__ = "document_pages"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    quality: Mapped[str] = mapped_column(String(20), default="goed")
    version: Mapped[DocumentVersion] = relationship(back_populates="pages")


class Clause(Base):
    __tablename__ = "clauses"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    article: Mapped[str | None] = mapped_column(String(50))
    heading: Mapped[str | None] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)
    order: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[DocumentVersion] = relationship(back_populates="clauses")


class DocumentDiff(Base):
    __tablename__ = "document_diffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    old_version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"))
    new_version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"))
    summary: Mapped[dict | None] = mapped_column(JSON)
    changes: Mapped[list | None] = mapped_column(JSON)
    ai_analysis_id: Mapped[int | None] = mapped_column(ForeignKey("ai_analyses.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------------------------------------------------------- Vergelijkingsrubrieken & bevindingen
class Feature(Base):
    """Gestandaardiseerd vergelijkingskenmerk (rubriek). Uitbreidbaar via de instellingen."""
    __tablename__ = "features"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    label: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(String(20), default="status")  # status|tekst|bedrag|getal
    # dekking|acceptatie|gebruik|flexibiliteit|eigen_risico|collectie|aanvullend|waarde
    scoring_aspect: Mapped[str | None] = mapped_column(String(40))
    keywords: Mapped[list | None] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Finding(Base):
    """Waarde van een kenmerk voor een product, met bronverwijzing.

    Status-waarden: gedekt | uitgesloten | voorwaardelijk | aanvullende_clausule |
    niet_gevonden | onvoldoende_informatie | menselijke_beoordeling
    """
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    feature_id: Mapped[int] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="menselijke_beoordeling")
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[str | None] = mapped_column(Text)
    document_version_id: Mapped[int | None] = mapped_column(ForeignKey("document_versions.id", ondelete="SET NULL"))
    page_number: Mapped[int | None] = mapped_column(Integer)
    article: Mapped[str | None] = mapped_column(String(80))
    quote: Mapped[str | None] = mapped_column(Text)
    quote_verified: Mapped[bool | None] = mapped_column(Boolean)
    origin: Mapped[str] = mapped_column(String(20), default="handmatig")  # handmatig|ai|lokaal
    confidence: Mapped[str | None] = mapped_column(String(20))  # hoog|middel|laag
    review_status: Mapped[str] = mapped_column(String(30), default="te_beoordelen")
    locked: Mapped[bool] = mapped_column(Boolean, default=False)  # menselijke correctie
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("findings.id"))
    ai_analysis_id: Mapped[int | None] = mapped_column(ForeignKey("ai_analyses.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    feature: Mapped[Feature] = relationship()
    product: Mapped[Product] = relationship()


# ---------------------------------------------------------------- Premielab
class ReferenceProfile(TimestampMixin, Base):
    """Rekenprofiel (geen persoonsgegevens, geen echte offerte)."""
    __tablename__ = "reference_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    vehicle_category: Mapped[str] = mapped_column(String(30), default="auto")
    make: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    build_year: Mapped[int | None] = mapped_column(Integer)
    vehicle_type: Mapped[str | None] = mapped_column(String(100))
    engine_cc: Mapped[int | None] = mapped_column(Integer)
    insured_value: Mapped[float | None] = mapped_column(Float)
    valuation_value: Mapped[float | None] = mapped_column(Float)
    postcode_area: Mapped[str | None] = mapped_column(String(20))
    driver_age_band: Mapped[str | None] = mapped_column(String(30))
    claim_free_years: Mapped[int | None] = mapped_column(Integer)
    annual_km: Mapped[int | None] = mapped_column(Integer)
    storage: Mapped[str | None] = mapped_column(String(100))
    usage: Mapped[str | None] = mapped_column(String(100))
    coverage: Mapped[str | None] = mapped_column(String(50))  # wa|wa_beperkt_casco|wa_volledig_casco
    deductible: Mapped[float | None] = mapped_column(Float)
    extras: Mapped[list | None] = mapped_column(JSON)
    vehicle_count: Mapped[int] = mapped_column(Integer, default=1)
    is_example: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class PremiumObservation(TimestampMixin, Base):
    __tablename__ = "premium_observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id", ondelete="SET NULL"), index=True)
    provider_name_raw: Mapped[str | None] = mapped_column(String(200))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), index=True)
    product_name_raw: Mapped[str | None] = mapped_column(String(300))
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("reference_profiles.id", ondelete="SET NULL"), index=True)
    amount: Mapped[float | None] = mapped_column(Float)            # bedrag zoals vastgelegd
    period: Mapped[str] = mapped_column(String(20), default="jaar")  # jaar|half_jaar|kwartaal|maand
    annual_premium: Mapped[float | None] = mapped_column(Float)    # genormaliseerd naar jaar
    currency: Mapped[str] = mapped_column(String(5), default="EUR")
    tax_included: Mapped[str] = mapped_column(String(10), default="onbekend")  # ja|nee|onbekend
    extra_costs: Mapped[float | None] = mapped_column(Float)
    membership_costs: Mapped[float | None] = mapped_column(Float)
    coverage_variant: Mapped[str | None] = mapped_column(String(50))
    deductible: Mapped[float | None] = mapped_column(Float)
    # Voertuig-/risicokenmerken (vooral uit imports, als er geen profiel is)
    vehicle_category: Mapped[str | None] = mapped_column(String(30))
    vehicle_description: Mapped[str | None] = mapped_column(String(300))
    build_year: Mapped[int | None] = mapped_column(Integer)
    insured_value: Mapped[float | None] = mapped_column(Float)
    km_band: Mapped[str | None] = mapped_column(String(50))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    source_description: Mapped[str | None] = mapped_column(Text)
    reference_date: Mapped[date | None] = mapped_column(Date)   # peildatum
    calculated_at: Mapped[date | None] = mapped_column(Date)    # berekeningsdatum
    # geverifieerd_tarief | proefberekening | handmatige_offerte | openbare_indicatie |
    # historisch_tarief | niet_beschikbaar
    observation_type: Mapped[str] = mapped_column(String(40), default="handmatige_offerte")
    reliability: Mapped[str] = mapped_column(String(20), default="middel")  # hoog|middel|laag
    is_historical: Mapped[bool] = mapped_column(Boolean, default=False)
    is_actual_quote: Mapped[bool] = mapped_column(Boolean, default=False)  # uitgebrachte offerte vs getoonde premie
    import_id: Mapped[int | None] = mapped_column(ForeignKey("excel_imports.id", ondelete="SET NULL"), index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="niet_publiek")
    notes: Mapped[str | None] = mapped_column(Text)


class ExcelImport(TimestampMixin, Base):
    __tablename__ = "excel_imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(500))
    stored_path: Mapped[str] = mapped_column(String(1000))
    sha256: Mapped[str] = mapped_column(String(64))
    sheet: Mapped[str | None] = mapped_column(String(200))
    header_row: Mapped[int] = mapped_column(Integer, default=1)
    mapping: Mapped[dict | None] = mapped_column(JSON)
    defaults: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="geupload")  # geupload|gevalideerd|geimporteerd|teruggedraaid|fout
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    validation: Mapped[dict | None] = mapped_column(JSON)
    treat_as: Mapped[str] = mapped_column(String(20), default="historisch")  # historisch|actueel
    visibility: Mapped[str] = mapped_column(String(20), default="niet_publiek")


class ImportMappingTemplate(TimestampMixin, Base):
    __tablename__ = "import_mapping_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    mapping: Mapped[dict] = mapped_column(JSON)


# ---------------------------------------------------------------- Monitor
class MonitorRun(Base):
    __tablename__ = "monitor_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[str] = mapped_column(String(20), default="handmatig")  # gepland|handmatig|inhaal
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="bezig")  # bezig|voltooid|fout
    summary: Mapped[dict | None] = mapped_column(JSON)


class SourceCheck(Base):
    __tablename__ = "source_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("monitor_runs.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    http_status: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(30))  # ongewijzigd|gewijzigd|nieuw|fout|geblokkeerd|niet_beschikbaar
    content_hash: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str | None] = mapped_column(Text)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    # nieuwe_concurrent | voorwaarden_gewijzigd | premieverschil | nieuw_product |
    # marktkans | bron_onbeschikbaar | beoordeling_nodig | systeem
    type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    severity: Mapped[str] = mapped_column(String(20), default="info")  # info|belangrijk
    status: Mapped[str] = mapped_column(String(20), default="nieuw")  # nieuw|gelezen|gearchiveerd
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


# ---------------------------------------------------------------- AI
class AIAnalysis(Base):
    __tablename__ = "ai_analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)  # vraag|extractie|verkoop|radar|dossier|wijziging|ontdekking
    model: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="voltooid")  # voltooid|fout|geweigerd
    question: Mapped[str | None] = mapped_column(Text)
    sent_summary: Mapped[dict | None] = mapped_column(JSON)  # wat is er verstuurd (bron-id's, aantallen)
    response: Mapped[dict | None] = mapped_column(JSON)
    validation: Mapped[dict | None] = mapped_column(JSON)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class ImprovementSuggestion(TimestampMixin, Base):
    __tablename__ = "improvement_suggestions"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), default="datagedreven")  # datagedreven|innovatiehypothese
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(60))
    summary: Mapped[str | None] = mapped_column(Text)
    gap: Mapped[str | None] = mapped_column(Text)
    vetera_situation: Mapped[str | None] = mapped_column(Text)
    market_context: Mapped[str | None] = mapped_column(Text)
    suggestion: Mapped[str | None] = mapped_column(Text)
    customer_benefits: Mapped[str | None] = mapped_column(Text)
    commercial_benefits: Mapped[str | None] = mapped_column(Text)
    risks: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list | None] = mapped_column(JSON)  # [{type, finding_id, document_version_id, page, quote, url}]
    confidence: Mapped[str] = mapped_column(String(20), default="laag")  # hoog|middel|laag
    priority: Mapped[str] = mapped_column(String(20), default="middel")  # hoog|middel|laag
    priority_factors: Mapped[dict | None] = mapped_column(JSON)
    follow_up: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="nieuw")  # nieuw|onderzoeken|interessant|uitwerken|afgerond|afgewezen
    origin: Mapped[str] = mapped_column(String(20), default="lokaal")  # lokaal|ai|handmatig
    fingerprint: Mapped[str | None] = mapped_column(String(200), index=True)
    ai_analysis_id: Mapped[int | None] = mapped_column(ForeignKey("ai_analyses.id", ondelete="SET NULL"))


class ResearchDossier(Base):
    __tablename__ = "research_dossiers"
    id: Mapped[int] = mapped_column(primary_key=True)
    suggestion_id: Mapped[int | None] = mapped_column(ForeignKey("improvement_suggestions.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[dict] = mapped_column(JSON)
    ai_analysis_id: Mapped[int | None] = mapped_column(ForeignKey("ai_analyses.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class SalesCard(Base):
    __tablename__ = "sales_cards"
    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    vetera_product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    content: Mapped[dict] = mapped_column(JSON)
    origin: Mapped[str] = mapped_column(String(20), default="lokaal")
    ai_analysis_id: Mapped[int | None] = mapped_column(ForeignKey("ai_analyses.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------------------------------------------------------- Scores, rapporten, instellingen
class ScoreProfile(TimestampMixin, Base):
    __tablename__ = "score_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    weights: Mapped[dict] = mapped_column(JSON)
    reference_profile_id: Mapped[int | None] = mapped_column(ForeignKey("reference_profiles.id", ondelete="SET NULL"))
    vehicle_category: Mapped[str | None] = mapped_column(String(30))
    min_coverage: Mapped[float] = mapped_column(Float, default=0.6)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    params: Mapped[dict | None] = mapped_column(JSON)
    content: Mapped[dict | None] = mapped_column(JSON)
    file_pdf: Mapped[str | None] = mapped_column(String(1000))
    file_xlsx: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)


class CalculatorConnector(TimestampMixin, Base):
    __tablename__ = "calculator_connectors"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(1000))
    terms_url: Mapped[str | None] = mapped_column(String(1000))
    # onbekend | in_onderzoek | toegestaan | niet_toegestaan
    permission_status: Mapped[str] = mapped_column(String(30), default="onbekend")
    permission_evidence: Mapped[str | None] = mapped_column(Text)
    terms_checked_at: Mapped[date | None] = mapped_column(Date)
    robots_status: Mapped[str | None] = mapped_column(String(50))
    implemented: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class CalculatorLog(Base):
    __tablename__ = "calculator_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("calculator_connectors.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    action: Mapped[str] = mapped_column(String(50))
    message: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    entity: Mapped[str] = mapped_column(String(60), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(20), default="gebruiker")  # gebruiker|ai|systeem|import
    changes: Mapped[dict | None] = mapped_column(JSON)


class QualityResolution(Base):
    """Markeert een datakwaliteitssignaal als beoordeeld, zodat het niet steeds terugkomt."""
    __tablename__ = "quality_resolutions"
    __table_args__ = (UniqueConstraint("issue_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    issue_key: Mapped[str] = mapped_column(String(200))
    resolution: Mapped[str] = mapped_column(String(30))  # geaccepteerd|gecorrigeerd
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Job(Base):
    """Achtergrondtaak (bijv. automatisch onderzoek), zodat lange acties geen time-out geven."""
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="wachtrij")  # wachtrij|bezig|klaar|fout
    step: Mapped[str | None] = mapped_column(String(300))
    done: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
