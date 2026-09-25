import type { Breakdown } from "@/lib/dashboards";

/** Répartition en barres horizontales triées (Document 9, § 4.2). */
export function BarList({ items, labels, emptyLabel = "Aucune donnée" }: { items: Breakdown[]; labels?: Record<string, string>; emptyLabel?: string }) {
  const max = Math.max(1, ...items.map((item) => item.count));
  if (items.length === 0) return <p className="text-sm text-muted">{emptyLabel}</p>;
  return (
    <ul className="space-y-2.5">
      {items.map((item) => {
        const label = (item.key && labels?.[item.key]) ?? item.label ?? "Non renseigné";
        return (
          <li key={item.key ?? "none"}>
            <div className="flex justify-between gap-3 text-sm">
              <span className="truncate text-ink">{label}</span>
              <span className="font-medium tabular-nums text-ink">{item.count}</span>
            </div>
            <div className="mt-1 h-2 rounded-full bg-gray-100" aria-hidden="true">
              <div className="h-2 rounded-full bg-brand-500" style={{ width: `${(item.count / max) * 100}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
