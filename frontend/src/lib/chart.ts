// Categorisch palet in vaste volgorde, gevalideerd (lichtheid, chroma, CVD- en normaal-zicht-scheiding).
// Vetera heeft een eigen vaste kleur; concurrenten krijgen een kleur op basis van hun id,
// zodat de kleur de entiteit volgt en filters bestaande series niet herkleuren.
// Geel (#eda100) heeft < 3:1 contrast: grafieken tonen daarom altijd ook een tabel/labels.
export const VETERA_COLOR = "#00866f";
export const SERIES = ["#2a78d6", "#eb6834", "#6250d6", "#eda100", "#e34948"];
export function colorFor(id: number | string | null | undefined, isReference = false) {
  if (isReference) return VETERA_COLOR;
  const n = typeof id === "number" ? id : [...String(id ?? "")].reduce((a, c) => a + c.charCodeAt(0), 0);
  return SERIES[Math.abs(n) % SERIES.length];
}
export const AXIS = { stroke: "#86868b", fontSize: 11.5, tickLine: false, axisLine: false } as const;
