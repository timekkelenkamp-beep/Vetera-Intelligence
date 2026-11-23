export function normalizeForSearch(s: string) {
  return s
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/-\s*\n\s*/g, "")
    .replace(/[^\w€%]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}
