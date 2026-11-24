"""Basisconfiguratie bij een nieuwe installatie.

Er worden GEEN fictieve premies, voorwaarden of concurrentiegegevens aangemaakt.
Wel: vergelijkingsrubrieken, voorbeeld-rekenprofielen (duidelijk gemarkeerd),
standaard-instellingen, een scoreprofiel en het Vetera-referentieprofiel (leeg).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Feature, Provider, ReferenceProfile, ScoreProfile, Setting

# (key, categorie, label, scoring_aspect, value_type, trefwoorden)
FEATURES: list[tuple[str, str, str, str, str, list[str]]] = [
    # Acceptatie
    ("acc_min_voertuigleeftijd", "Acceptatie", "Minimale voertuigleeftijd", "acceptatie", "tekst",
     ["jaar oud", "bouwjaar", "minimaal", "leeftijd van het voertuig", "ouder dan"]),
    ("acc_min_leeftijd_bestuurder", "Acceptatie", "Minimale leeftijd bestuurder", "acceptatie", "tekst",
     ["leeftijd", "bestuurder", "jaar of ouder", "minimumleeftijd"]),
    ("acc_tweede_voertuig", "Acceptatie", "Tweede voertuig verplicht", "acceptatie", "status",
     ["tweede auto", "tweede voertuig", "dagelijks vervoermiddel", "ander motorrijtuig"]),
    ("acc_dagelijks_gebruik", "Acceptatie", "Dagelijks gebruik toegestaan", "acceptatie", "status",
     ["dagelijks gebruik", "dagelijks", "hobbymatig"]),
    ("acc_stalling", "Acceptatie", "Stallingsvereisten", "acceptatie", "tekst",
     ["stalling", "garage", "afgesloten ruimte", "inpandig", "gestald"]),
    ("acc_beperkingen", "Acceptatie", "Acceptatiebeperkingen", "acceptatie", "tekst",
     ["acceptatie", "niet geaccepteerd", "voorwaarden voor acceptatie", "uitgesloten van verzekering"]),
    # Gebruik
    ("geb_hobby", "Gebruik", "Hobbymatig gebruik", "gebruik", "status", ["hobby", "recreatief", "toer"]),
    ("geb_woon_werk", "Gebruik", "Woon-werkverkeer", "gebruik", "status", ["woon-werk", "woon werkverkeer", "werk"]),
    ("geb_zakelijk", "Gebruik", "Zakelijk gebruik", "gebruik", "status", ["zakelijk", "beroepsmatig", "verhuur"]),
    ("geb_km_beperking", "Gebruik", "Kilometerbeperkingen", "flexibiliteit", "tekst",
     ["kilometer", "km per jaar", "kilometrage", "kilometerstand"]),
    ("geb_buitenland", "Gebruik", "Buitenlands gebruik", "flexibiliteit", "status",
     ["buitenland", "europa", "groene kaart", "landen"]),
    ("geb_evenementen", "Gebruik", "Evenementen en rally's", "flexibiliteit", "status",
     ["rally", "evenement", "toertocht", "regelmatigheidsrit", "concours"]),
    ("geb_circuit", "Gebruik", "Circuitgebruik", "flexibiliteit", "status",
     ["circuit", "race", "wedstrijd", "snelheidsrit", "trackday"]),
    # Verzekerde waarde
    ("waa_taxatie", "Verzekerde waarde", "Taxatiewaarde", "waarde", "status", ["taxatie", "taxatierapport", "getaxeerd"]),
    ("waa_dagwaarde", "Verzekerde waarde", "Dagwaarde", "waarde", "status", ["dagwaarde", "marktwaarde"]),
    ("waa_taxatie_geldigheid", "Verzekerde waarde", "Geldigheidsduur taxatie", "waarde", "tekst",
     ["geldig", "jaar geldig", "geldigheidsduur", "hertaxatie"]),
    ("waa_indexatie", "Verzekerde waarde", "Indexatie", "waarde", "status", ["indexatie", "geïndexeerd", "index"]),
    ("waa_waardevermindering", "Verzekerde waarde", "Waardevermindering", "waarde", "status",
     ["waardevermindering", "waardedaling", "afschrijving"]),
    ("waa_totaal_verlies", "Verzekerde waarde", "Totaalverliesregeling", "waarde", "tekst",
     ["total loss", "totaal verlies", "totaalverlies", "technisch totaal", "economisch totaal"]),
    # Dekkingen
    ("dek_wa", "Dekkingen", "Wettelijke aansprakelijkheid", "dekking", "status", ["aansprakelijkheid", "wam", "wa-"]),
    ("dek_beperkt_casco", "Dekkingen", "Beperkt casco", "dekking", "status", ["beperkt casco", "beperkte cascodekking"]),
    ("dek_volledig_casco", "Dekkingen", "Volledig casco", "dekking", "status", ["volledig casco", "allrisk", "all risk"]),
    ("dek_brand", "Dekkingen", "Brand", "dekking", "status", ["brand", "ontploffing", "zelfontbranding", "kortsluiting"]),
    ("dek_diefstal", "Dekkingen", "Diefstal", "dekking", "status", ["diefstal", "joyriding", "verduistering", "inbraak"]),
    ("dek_ruitbreuk", "Dekkingen", "Ruitbreuk", "dekking", "status", ["ruit", "ruitschade", "glas"]),
    ("dek_storm", "Dekkingen", "Storm", "dekking", "status", ["storm", "hagel", "natuurgeweld", "overstroming"]),
    ("dek_vandalisme", "Dekkingen", "Vandalisme", "dekking", "status", ["vandalisme", "kwaadwillig"]),
    ("dek_eigen_gebrek", "Dekkingen", "Eigen gebrek", "dekking", "status", ["eigen gebrek", "constructiefout", "slijtage"]),
    ("dek_transport", "Dekkingen", "Schade tijdens transport", "dekking", "status",
     ["transport", "vervoer", "aanhanger", "trailer", "ambulancetrailer"]),
    ("dek_pechhulp", "Dekkingen", "Pechhulp", "aanvullend", "status", ["pechhulp", "hulpverlening", "berging", "sleep"]),
    ("dek_rechtsbijstand", "Dekkingen", "Rechtsbijstand", "aanvullend", "status", ["rechtsbijstand", "juridische hulp"]),
    ("dek_ongevallen_inzittenden", "Dekkingen", "Ongevallenverzekering inzittenden/opzittenden", "aanvullend", "status",
     ["ongevallen", "inzittenden", "opzittenden", "opzittende"]),
    ("dek_schade_inzittenden", "Dekkingen", "Schadeverzekering inzittenden/opzittenden", "aanvullend", "status",
     ["schadeverzekering inzittenden", "svi", "svo", "schadeverzekering opzittenden"]),
    # Eigen risico
    ("er_standaard", "Eigen risico", "Standaard eigen risico", "eigen_risico", "bedrag", ["eigen risico"]),
    ("er_afwijkend", "Eigen risico", "Afwijkende eigen risico's", "eigen_risico", "tekst",
     ["verhoogd eigen risico", "afwijkend eigen risico", "jonge bestuurder", "extra eigen risico"]),
    ("er_vrijwillig", "Eigen risico", "Vrijwillige keuzes", "eigen_risico", "tekst", ["vrijwillig eigen risico", "keuze"]),
    ("er_bijzonder", "Eigen risico", "Bijzondere voorwaarden eigen risico", "eigen_risico", "tekst",
     ["geen eigen risico", "vervalt", "eigen risico geldt niet"]),
    # Collecties
    ("col_meerdere_voertuigen", "Collecties", "Meerdere voertuigen op één polis", "collectie", "status",
     ["collectie", "meerdere voertuigen", "verzameling", "één polis"]),
    ("col_verschillende_soorten", "Collecties", "Verschillende voertuigsoorten", "collectie", "status",
     ["auto's en motoren", "verschillende voertuigen", "motorfiets", "bromfiets"]),
    ("col_extra_bestuurders", "Collecties", "Aanvullende bestuurders", "collectie", "status",
     ["regelmatige bestuurder", "andere bestuurders", "bestuurders"]),
    ("col_pakketvoordeel", "Collecties", "Pakketvoordelen", "collectie", "status", ["pakketkorting", "korting", "pakket"]),
    ("col_verzamelaars", "Collecties", "Bijzondere voorwaarden voor verzamelaars", "collectie", "tekst",
     ["verzamelaar", "collectie", "museum"]),
]

# Kernkenmerken voor het overzicht (zelf aan te passen in de app)
CORE_FEATURES = ["acc_min_leeftijd_bestuurder", "acc_dagelijks_gebruik", "geb_km_beperking", "geb_evenementen",
                 "geb_buitenland", "waa_taxatie", "waa_totaal_verlies", "dek_diefstal", "dek_transport",
                 "dek_pechhulp", "er_standaard", "col_meerdere_voertuigen"]

EXAMPLE_PROFILES = [
    dict(name="Klassieke auto – lage waarde", vehicle_category="auto", vehicle_type="Personenauto",
         build_year=1978, insured_value=8000, valuation_value=8000, driver_age_band="45-65", annual_km=3000,
         storage="Afgesloten garage", usage="Hobbymatig", coverage="wa_beperkt_casco", deductible=150),
    dict(name="Klassieke auto – hoge waarde", vehicle_category="auto", vehicle_type="Sportwagen",
         build_year=1965, insured_value=95000, valuation_value=95000, driver_age_band="45-65", annual_km=2500,
         storage="Afgesloten garage", usage="Hobbymatig", coverage="wa_volledig_casco", deductible=250),
    dict(name="Klassieke motorfiets", vehicle_category="motor", vehicle_type="Motorfiets", engine_cc=750,
         build_year=1972, insured_value=12000, valuation_value=12000, driver_age_band="45-65", annual_km=2000,
         storage="Afgesloten garage", usage="Hobbymatig", coverage="wa_volledig_casco", deductible=150),
    dict(name="Klassieke bromfiets", vehicle_category="bromfiets", vehicle_type="Bromfiets", engine_cc=49,
         build_year=1975, insured_value=2500, valuation_value=2500, driver_age_band="30-45", annual_km=1000,
         storage="Afgesloten schuur", usage="Hobbymatig", coverage="wa_beperkt_casco", deductible=0),
    dict(name="Verzamelaar – meerdere voertuigen", vehicle_category="meerdere", vehicle_type="Collectie (3 auto's, 1 motor)",
         build_year=1970, insured_value=150000, valuation_value=150000, driver_age_band="45-65", annual_km=5000,
         storage="Afgesloten garage", usage="Hobbymatig", coverage="wa_volledig_casco", deductible=250, vehicle_count=4),
]

# Startlijst uit de opdracht. Wordt alleen op verzoek geladen, met status 'te_beoordelen'.
START_LIST = ["GIO", "KNAC", "Kuiper Verzekeringen", "Turien & Co.", "Univé", "ANWB", "Nh1816",
              "Interpolis", "Nationale-Nederlanden"]

DEFAULT_SETTINGS = {
    "ai_enabled": True,
    "ai_model": "claude-opus-5-5",
    "ai_effort": "medium",
    "ai_monthly_budget_eur": 25.0,
    "ai_max_request_cost_eur": 2.0,
    "ai_allow_nonpublic": False,  # niet-publieke data nooit zonder expliciete toestemming
    "ai_web_research": False,     # web-zoeken door AI alleen na expliciete activering
    "monitor_mode": "handmatig",   # handmatig | automatisch — standaard start de gebruiker controles zelf
    "monitor_interval_days": 91,  # bij automatisch: elk kwartaal
    "monitor_last_run_at": None,
    "monitor_request_delay_s": 3,
    "premium_stale_months": 12,
    "premium_difference_alert_pct": 15,
    "onboarding_done": False,
}

DEFAULT_WEIGHTS = {"voorwaarden": 40, "premie": 30, "acceptatie": 20, "flexibiliteit": 10}


def seed_defaults(db: Session) -> None:
    existing = {f.key for f in db.scalars(select(Feature))}
    for i, (key, cat, label, aspect, vtype, kws) in enumerate(FEATURES):
        if key not in existing:
            db.add(Feature(key=key, category=cat, label=label, scoring_aspect=aspect, value_type=vtype,
                           keywords=kws, sort_order=i, is_core=key in CORE_FEATURES))
    for k, v in DEFAULT_SETTINGS.items():
        if db.get(Setting, k) is None:
            db.add(Setting(key=k, value=v))
    if not db.scalars(select(ReferenceProfile).where(ReferenceProfile.is_example.is_(True))).first():
        for p in EXAMPLE_PROFILES:
            db.add(ReferenceProfile(is_example=True,
                                    notes="Voorbeeld-rekenprofiel. Geen persoonsgegevens en geen echte offerte.", **p))
    if not db.scalars(select(ScoreProfile)).first():
        db.add(ScoreProfile(name="Standaard", description="Startwegingen; vrij aan te passen.",
                            weights=DEFAULT_WEIGHTS))
    if not db.scalars(select(Provider).where(Provider.is_reference.is_(True))).first():
        db.add(Provider(name="Vetera", is_reference=True, status="actief", provider_type="onbekend",
                        origin="handmatig",
                        verification_note="Referentie-aanbieder. Voeg de huidige, openbaar gepubliceerde "
                                          "Vetera-producten en polisvoorwaarden toe."))
    db.commit()


def load_start_list(db: Session) -> list[Provider]:
    names = {p.name.lower() for p in db.scalars(select(Provider))}
    added = []
    for n in START_LIST:
        if n.lower() in names:
            continue
        p = Provider(name=n, status="te_beoordelen", origin="startlijst",
                     verification_note="Afkomstig uit de startlijst van de opdracht. Nog niet geverifieerd of "
                                       "deze partij een relevant oldtimer-, klassieke motor- of bromfietsproduct "
                                       "aanbiedt. Controleer website, type aanbieder en producten.")
        db.add(p)
        added.append(p)
    db.commit()
    return added
