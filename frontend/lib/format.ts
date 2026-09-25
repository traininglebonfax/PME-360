const dateFormatter = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
const dateTimeFormatter = new Intl.DateTimeFormat("fr-FR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const relativeFormatter = new Intl.RelativeTimeFormat("fr-FR", { numeric: "auto" });

export function formatDate(value?: string | null): string {
  return value ? dateFormatter.format(new Date(value)) : "—";
}

export function formatDateTime(value?: string | null): string {
  return value ? dateTimeFormatter.format(new Date(value)) : "—";
}

/** « il y a 3 jours », « hier »… */
export function formatRelative(value?: string | null, now: Date = new Date()): string {
  if (!value) return "jamais";
  const seconds = Math.round((new Date(value).getTime() - now.getTime()) / 1000);
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31536000],
    ["month", 2592000],
    ["week", 604800],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) return relativeFormatter.format(Math.round(seconds / size), unit);
  }
  return "à l'instant";
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
