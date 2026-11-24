export const FINDING_STATUS: Record<string, { label: string; short: string; tone: Tone }> = {
  gedekt: { label: "Aantoonbaar gedekt", short: "Gedekt", tone: "positive" },
  uitgesloten: { label: "Aantoonbaar uitgesloten", short: "Uitgesloten", tone: "negative" },
  voorwaardelijk: { label: "Voorwaardelijk gedekt", short: "Voorwaardelijk", tone: "caution" },
  aanvullende_clausule: { label: "Afhankelijk van aanvullende clausule", short: "Aanv. clausule", tone: "info" },
  niet_gevonden: { label: "Niet gevonden", short: "Niet gevonden", tone: "neutral" },
  onvoldoende_informatie: { label: "Onvoldoende informatie", short: "Onvoldoende info", tone: "neutral" },
  menselijke_beoordeling: { label: "Menselijke beoordeling noodzakelijk", short: "Beoordelen", tone: "attention" },
};
export type Tone = "positive" | "negative" | "caution" | "info" | "neutral" | "attention" | "accent";

export const PROVIDER_TYPE: Record<string, string> = {
  verzekeraar: "Verzekeraar", gevolmachtigde: "Gevolmachtigd agent", tussenpersoon: "Tussenpersoon",
  distributeur: "Distributeur", onbekend: "Type onbekend",
};
export const PROVIDER_STATUS: Record<string, { label: string; tone: Tone }> = {
  actief: { label: "Actief", tone: "positive" }, te_beoordelen: { label: "Te beoordelen", tone: "attention" },
  afgewezen: { label: "Afgewezen", tone: "neutral" }, samengevoegd: { label: "Samengevoegd", tone: "neutral" },
};
export const VEHICLE: Record<string, string> = { auto: "Klassieke auto", motor: "Klassieke motorfiets", bromfiets: "Klassieke bromfiets", meerdere: "Meerdere voertuigsoorten" };
export const DOC_TYPE: Record<string, string> = {
  polisvoorwaarden: "Polisvoorwaarden", verzekeringskaart: "Verzekeringskaart", productinformatie: "Productinformatie",
  clausule: "Clausule", aanvullende_voorwaarden: "Aanvullende voorwaarden", premietabel: "Premietabel", overig: "Overig",
};
export const SOURCE_TYPE: Record<string, string> = {
  officieel_primair: "Officiële primaire bron", openbaar_overig: "Andere openbare bron", handmatig: "Handmatig ingevoerd",
  historisch: "Historisch document", niet_geverifieerd: "Niet geverifieerd",
};
export const ACCESS: Record<string, { label: string; tone: Tone }> = {
  toegestaan: { label: "Toegestaan", tone: "positive" }, onbekend: { label: "Onbekend", tone: "neutral" },
  niet_toegestaan: { label: "Niet toegestaan", tone: "negative" }, robots_blokkeert: { label: "Geblokkeerd (robots.txt)", tone: "negative" },
};
export const OBS_TYPE: Record<string, string> = {
  geverifieerd_tarief: "Geverifieerd tarief", proefberekening: "Vastgelegde proefberekening", handmatige_offerte: "Handmatig ingevoerde offerte",
  openbare_indicatie: "Openbare indicatie", historisch_tarief: "Historisch tarief", niet_beschikbaar: "Niet beschikbaar",
};
export const COVERAGE: Record<string, string> = {
  wa: "WA", wa_brand_diefstal: "WA + brand/diefstal", wa_beperkt_casco: "WA + beperkt casco", wa_volledig_casco: "WA + volledig casco",
};
/** Dekkingsniveaus van laag naar hoog (zelfde sleutels als bij premies en rekenprofielen). */
export const COVERAGE_LEVELS: { key: string; label: string; short: string }[] = [
  { key: "wa", label: "WA", short: "WA" },
  { key: "wa_brand_diefstal", label: "WA + brand/diefstal", short: "WA + B/D" },
  { key: "wa_beperkt_casco", label: "WA + beperkt casco", short: "Beperkt casco" },
  { key: "wa_volledig_casco", label: "WA + volledig casco", short: "Volledig casco" },
];
export const PERIOD: Record<string, string> = { jaar: "per jaar", half_jaar: "per half jaar", kwartaal: "per kwartaal", maand: "per maand" };
export const NOTIF_TYPE: Record<string, string> = {
  nieuwe_concurrent: "Nieuwe concurrent", voorwaarden_gewijzigd: "Voorwaarden gewijzigd", premieverschil: "Premieverschil",
  nieuw_product: "Nieuw product", marktkans: "Marktkans", bron_onbeschikbaar: "Bron niet beschikbaar",
  beoordeling_nodig: "Beoordeling nodig", systeem: "Systeem",
};
export const SUGGESTION_STATUS = [
  { key: "nieuw", label: "Nieuw" }, { key: "onderzoeken", label: "Onderzoeken" }, { key: "interessant", label: "Interessant" },
  { key: "uitwerken", label: "Uitwerken" }, { key: "afgerond", label: "Afgerond" }, { key: "afgewezen", label: "Afgewezen" },
];
export const SUGGESTION_CATEGORIES = ["Productverbetering", "Voorwaardenverbetering", "Commerciële kans", "Nieuwe doelgroep",
  "Innovatief concept", "Concurrentievoordeel", "Proces- of serviceverbetering"];
export const CHANGE_TONE: Record<string, Tone> = {
  redactioneel: "neutral", verduidelijking: "info", dekkingsuitbreiding: "positive", dekkingsbeperking: "negative",
  acceptatie: "caution", nieuwe_uitsluiting: "negative", overig: "neutral",
};
