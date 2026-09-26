"use client";

/**
 * Carte des régions de Côte d'Ivoire (Document 9, § 4.3) : choroplèthe à une teinte (clair → foncé) sur le nombre
 * de PME, le score moyen ou la part à risque. Moyennes masquées sous 5 PME évaluées (hachures) ; info-bulle au
 * survol et au clavier ; vue tableau. Fond de carte : geoBoundaries (CC BY 4.0), tracés précalculés.
 */
import { useMemo, useState } from "react";

import geo from "@/lib/geo/civRegions.json";
import type { RegionalMap } from "@/lib/dashboards";

import { TableToggle } from "./Charts";

// Même rampe séquentielle validée que la heatmap (une teinte, clair → foncé).
const SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"];
const EMPTY = "#f3f4f6";
const MASKED = "#e5e7eb";

type Metric = "pmes" | "average_score" | "at_risk_share";
const METRICS: { key: Metric; label: string }[] = [
  { key: "pmes", label: "Nombre de PME" },
  { key: "average_score", label: "Score moyen" },
  { key: "at_risk_share", label: "Part de PME à risque" },
];

type Row = RegionalMap["regions"][number];

function formatValue(metric: Metric, row: Row, minCell: number): string {
  if (metric === "pmes") return String(row.pmes);
  if (row.pmes === 0) return "aucune PME";
  const value = row[metric];
  if (value === null) return row.scored === 0 ? "non évaluée" : `masqué (moins de ${minCell} PME évaluées)`;
  return metric === "average_score" ? `${value.toFixed(0)}/100` : `${Math.round(value * 100)} %`;
}

export function RegionMap({ data }: { data: RegionalMap }) {
  const [metric, setMetric] = useState<Metric>("pmes");
  const [active, setActive] = useState<string | null>(null);
  const rows = useMemo(() => Object.fromEntries(data.regions.map((r) => [r.code, r])), [data.regions]);
  const max = Math.max(1, ...data.regions.map((r) => r.pmes));

  // Classe de couleur : bornes régulières sur l'échelle de la mesure (0–max, 0–100 ou 0–100 %).
  const scaleMax = metric === "pmes" ? max : metric === "average_score" ? 100 : 1;
  const bin = (value: number) => Math.min(SEQUENTIAL.length - 1, Math.floor((value / scaleMax) * SEQUENTIAL.length));
  const fill = (row: Row | undefined): string => {
    if (!row || row.pmes === 0) return EMPTY;
    const value = metric === "pmes" ? row.pmes : row[metric];
    if (value === null) return row.scored > 0 ? "url(#masked)" : MASKED;
    return SEQUENTIAL[bin(value)];
  };
  const legend = SEQUENTIAL.map((color, i) => {
    const from = (i * scaleMax) / SEQUENTIAL.length;
    const to = ((i + 1) * scaleMax) / SEQUENTIAL.length;
    const fmt = (v: number) => (metric === "at_risk_share" ? `${Math.round(v * 100)} %` : metric === "pmes" ? String(Math.round(v)) : v.toFixed(0));
    // Nombre de PME : bornes entières, la classe 0 ayant sa propre teinte (« aucune PME »).
    const label = metric === "pmes" ? `${Math.floor(from) + 1}–${Math.max(Math.floor(from) + 1, Math.round(to))}` : `${fmt(from)}–${fmt(to)}`;
    return { color, label };
  });
  const current = active ? rows[active] : null;
  const shape = active ? geo.regions.find((r) => r.code === active) : null;

  const table = (
    <table className="w-full text-sm">
      <thead className="text-left text-xs text-muted">
        <tr>
          <th className="py-1">Région</th>
          <th className="py-1 text-right">PME</th>
          <th className="py-1 text-right">Évaluées</th>
          <th className="py-1 text-right">Score moyen</th>
          <th className="py-1 text-right">Part à risque</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {data.regions.map((r) => (
          <tr key={r.code}>
            <td className="py-1">{r.name}</td>
            <td className="py-1 text-right tabular-nums">{r.pmes}</td>
            <td className="py-1 text-right tabular-nums">{r.scored}</td>
            <td className="py-1 text-right tabular-nums">{formatValue("average_score", r, data.min_cell)}</td>
            <td className="py-1 text-right tabular-nums">{formatValue("at_risk_share", r, data.min_cell)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <TableToggle table={table}>
      <div className="mb-3 flex flex-wrap gap-1" role="radiogroup" aria-label="Mesure affichée">
        {METRICS.map((m) => (
          <button
            key={m.key}
            role="radio"
            aria-checked={metric === m.key}
            onClick={() => setMetric(m.key)}
            className={
              metric === m.key
                ? "rounded-md bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-800 ring-1 ring-brand-600"
                : "rounded-md px-2.5 py-1 text-xs text-muted ring-1 ring-line hover:text-ink"
            }
          >
            {m.label}
          </button>
        ))}
      </div>
      <div className="relative mx-auto max-w-xl">
        <svg viewBox={`0 0 ${geo.width} ${geo.height}`} className="h-auto w-full" role="img" aria-label={`Carte des régions : ${METRICS.find((m) => m.key === metric)?.label}`}>
          <defs>
            <pattern id="masked" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="6" height="6" fill={MASKED} />
              <line x1="0" y1="0" x2="0" y2="6" stroke="#9ca3af" strokeWidth="1.5" />
            </pattern>
          </defs>
          {geo.regions.map((region) => {
            const row = rows[region.code];
            return (
              <path
                key={region.code}
                d={region.path}
                fill={fill(row)}
                stroke={active === region.code ? "#111827" : "#ffffff"}
                strokeWidth={active === region.code ? 2 : 1}
                tabIndex={0}
                aria-label={`${row?.name ?? region.code} : ${row ? formatValue(metric, row, data.min_cell) : "—"}`}
                onMouseEnter={() => setActive(region.code)}
                onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(region.code)}
                onBlur={() => setActive(null)}
                className="cursor-pointer outline-none"
                data-testid={`region-${region.code}`}
              />
            );
          })}
          {/* Contour de la région active redessiné au-dessus des voisines. */}
          {shape && <path d={shape.path} fill="none" stroke="#111827" strokeWidth={2} pointerEvents="none" />}
        </svg>
        {current && shape && (
          <div
            role="tooltip"
            className="pointer-events-none absolute z-10 w-56 -translate-x-1/2 rounded-lg bg-white p-2.5 text-xs shadow-lg ring-1 ring-line"
            style={{ left: `${(shape.cx / geo.width) * 100}%`, top: `${(shape.cy / geo.height) * 100}%`, transform: "translate(-50%, calc(-100% - 10px))" }}
          >
            <p className="font-medium text-ink">{current.name}</p>
            <p className="text-muted">
              {current.pmes} PME · {current.scored} évaluée(s)
            </p>
            <p className="text-ink">Score moyen : {formatValue("average_score", current, data.min_cell)}</p>
            <p className="text-ink">Part à risque : {formatValue("at_risk_share", current, data.min_cell)}</p>
          </div>
        )}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted" aria-label="Légende">
        {legend.map((item) => (
          <span key={item.label} className="flex items-center gap-1">
            <span className="h-3 w-4 rounded-sm" style={{ background: item.color }} />
            {item.label}
          </span>
        ))}
        <span className="flex items-center gap-1">
          <span className="h-3 w-4 rounded-sm ring-1 ring-line" style={{ background: EMPTY }} />
          aucune PME
        </span>
        {metric !== "pmes" && (
          <span className="flex items-center gap-1">
            <svg width="16" height="12" aria-hidden="true">
              <rect width="16" height="12" fill="url(#masked)" />
            </svg>
            masqué (moins de {data.min_cell} PME évaluées)
          </span>
        )}
      </div>
      <p className="mt-2 text-[11px] text-muted">
        {data.without_region > 0 && `${data.without_region} PME sans région renseignée ne figurent pas sur la carte. `}
        {geo.attribution}.
      </p>
    </TableToggle>
  );
}
