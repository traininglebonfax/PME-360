"use client";

/**
 * Graphiques du reporting (Document 9) : heatmap secteur × dimension, nuage maturité × performance,
 * haltère « initial → actuel ». Marques fines, une seule teinte par encodage, info-bulle au survol et au
 * clavier, vue tableau disponible (identité jamais portée par la couleur seule).
 */
import Link from "next/link";
import { useState } from "react";

import { cx } from "@/components/ui";

// Rampe séquentielle (une teinte, clair → foncé) et teintes ordinales validées (palette de référence).
const SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"];
const INITIAL = "#86b6ef"; // ordinal clair (≥ 2:1 sur fond clair)
const CURRENT = "#1c5cab"; // ordinal foncé
const MASKED = "#f0efec";

function sequential(value: number): string {
  const index = Math.min(SEQUENTIAL.length - 1, Math.floor((value / 100) * SEQUENTIAL.length));
  return SEQUENTIAL[Math.max(0, index)];
}

function readable(background: string): string {
  return SEQUENTIAL.indexOf(background) >= 3 ? "#ffffff" : "#1f2937";
}

export function TableToggle({ table, children }: { table: React.ReactNode; children: React.ReactNode }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <div>
      <div className="mb-2 flex justify-end">
        <button className="text-xs text-brand-700 hover:underline" onClick={() => setAsTable(!asTable)} aria-pressed={asTable}>
          {asTable ? "Voir le graphique" : "Voir le tableau"}
        </button>
      </div>
      {asTable ? table : children}
    </div>
  );
}

// --- Heatmap secteur × dimension -------------------------------------------------------------------------------

export interface HeatmapData {
  min_cell: number;
  sectors: { code: string; name: string }[];
  dimensions: { code: string; name: string }[];
  cells: { sector: string; dimension: string; n: number; average: number | null }[];
}

export function Heatmap({ data }: { data: HeatmapData }) {
  const [active, setActive] = useState<string | null>(null);
  const cell = (sector: string, dimension: string) => data.cells.find((c) => c.sector === sector && c.dimension === dimension);
  if (data.sectors.length === 0) return <p className="text-sm text-muted">Aucun diagnostic validé.</p>;
  const table = (
    <table className="w-full text-sm">
      <thead className="text-left text-xs text-muted">
        <tr>
          <th className="py-1">Secteur</th>
          <th className="py-1">Dimension</th>
          <th className="py-1 text-right">Score moyen</th>
          <th className="py-1 text-right">PME</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {data.cells.map((c) => (
          <tr key={`${c.sector}-${c.dimension}`}>
            <td className="py-1">{data.sectors.find((s) => s.code === c.sector)?.name}</td>
            <td className="py-1">{data.dimensions.find((d) => d.code === c.dimension)?.name}</td>
            <td className="py-1 text-right tabular-nums">{c.average === null ? `masqué (n < ${data.min_cell})` : c.average.toFixed(0)}</td>
            <td className="py-1 text-right tabular-nums">{c.n}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
  return (
    <TableToggle table={table}>
      <div className="overflow-x-auto">
        <table className="w-full border-separate text-xs" style={{ borderSpacing: 2 }}>
          <thead>
            <tr>
              <th className="sticky left-0 bg-surface" />
              {data.dimensions.map((d) => (
                <th key={d.code} className="px-1 pb-1 text-left font-normal text-muted" style={{ writingMode: "vertical-rl", transform: "rotate(180deg)", height: 96 }}>
                  {d.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.sectors.map((s) => (
              <tr key={s.code}>
                <th className="sticky left-0 whitespace-nowrap bg-surface pr-2 text-left font-normal text-ink">{s.name}</th>
                {data.dimensions.map((d) => {
                  const c = cell(s.code, d.code);
                  const key = `${s.code}-${d.code}`;
                  const masked = !c || c.average === null;
                  const background = masked ? MASKED : sequential(c.average!);
                  const label = c
                    ? `${s.name} · ${d.name} : ${masked ? `masqué, ${c.n} PME (moins de ${data.min_cell})` : `${c.average!.toFixed(0)}/100 sur ${c.n} PME`}`
                    : `${s.name} · ${d.name} : aucune donnée`;
                  return (
                    <td
                      key={key}
                      tabIndex={0}
                      aria-label={label}
                      onMouseEnter={() => setActive(label)}
                      onMouseLeave={() => setActive(null)}
                      onFocus={() => setActive(label)}
                      onBlur={() => setActive(null)}
                      className="h-8 min-w-8 rounded text-center tabular-nums outline-offset-1"
                      style={{ background, color: masked ? "#6b7280" : readable(background) }}
                    >
                      {masked ? (c ? `n=${c.n}` : "") : c!.average!.toFixed(0)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted" aria-hidden="true">
        <span>Score moyen :</span>
        {SEQUENTIAL.map((color, i) => (
          <span key={color} className="inline-flex items-center gap-1">
            <span className="h-3 w-5 rounded-sm" style={{ background: color }} />
            {Math.round((i * 100) / SEQUENTIAL.length)}
          </span>
        ))}
        <span className="inline-flex items-center gap-1">
          <span className="h-3 w-5 rounded-sm" style={{ background: MASKED }} /> masqué (n &lt; {data.min_cell})
        </span>
      </div>
      <p className="mt-1 min-h-5 text-xs text-ink" aria-live="polite">
        {active}
      </p>
    </TableToggle>
  );
}

// --- Nuage maturité × performance -------------------------------------------------------------------------------

export interface ScatterPoint {
  id: string;
  label: string;
  x: number; // IMO (maturité)
  y: number; // IPE (performance)
  href: string;
}

const W = 520;
const H = 340;
const PAD = { top: 16, right: 16, bottom: 36, left: 40 };

export function QuadrantScatter({ points, xThreshold, yThreshold }: { points: ScatterPoint[]; xThreshold: number; yThreshold: number }) {
  const [active, setActive] = useState<string | null>(null);
  const x = (v: number) => PAD.left + (v / 100) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - v / 100) * (H - PAD.top - PAD.bottom);
  const current = points.find((p) => p.id === active);
  if (points.length === 0) return <p className="text-sm text-muted">Aucune PME avec un diagnostic validé.</p>;
  const quadrant = [
    { label: "Performante mais fragile", tx: x(xThreshold / 2), ty: y(98) },
    { label: "Championne structurée", tx: x((100 + xThreshold) / 2), ty: y(98) },
    { label: "À consolider", tx: x(xThreshold / 2), ty: y(2) },
    { label: "Structurée, à développer", tx: x((100 + xThreshold) / 2), ty: y(2) },
  ];
  const table = (
    <table className="w-full text-sm">
      <thead className="text-left text-xs text-muted">
        <tr>
          <th className="py-1">PME</th>
          <th className="py-1 text-right">Maturité (IMO)</th>
          <th className="py-1 text-right">Performance (IPE)</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {points.map((p) => (
          <tr key={p.id}>
            <td className="py-1">
              <Link href={p.href} className="hover:text-brand-700">
                {p.label}
              </Link>
            </td>
            <td className="py-1 text-right tabular-nums">{p.x.toFixed(0)}</td>
            <td className="py-1 text-right tabular-nums">{p.y.toFixed(0)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
  return (
    <TableToggle table={table}>
      <div className="relative mx-auto max-w-2xl">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Maturité (IMO) en abscisse, performance (IPE) en ordonnée">
          {[0, 25, 50, 75, 100].map((t) => (
            <g key={t}>
              <line x1={x(0)} x2={x(100)} y1={y(t)} y2={y(t)} stroke="#eef0f3" />
              <text x={PAD.left - 6} y={y(t) + 3} textAnchor="end" fontSize="10" fill="#6b7280">
                {t}
              </text>
              <text x={x(t)} y={H - PAD.bottom + 14} textAnchor="middle" fontSize="10" fill="#6b7280">
                {t}
              </text>
            </g>
          ))}
          <line x1={x(xThreshold)} x2={x(xThreshold)} y1={y(0)} y2={y(100)} stroke="#9ca3af" strokeDasharray="4 4" />
          <line x1={x(0)} x2={x(100)} y1={y(yThreshold)} y2={y(yThreshold)} stroke="#9ca3af" strokeDasharray="4 4" />
          {quadrant.map((q) => (
            <text key={q.label} x={q.tx} y={q.ty + 4} textAnchor="middle" fontSize="10" fill="#6b7280">
              {q.label}
            </text>
          ))}
          <text x={(x(0) + x(100)) / 2} y={H - 4} textAnchor="middle" fontSize="11" fill="#374151">
            Maturité (IMO)
          </text>
          <text x={12} y={(y(0) + y(100)) / 2} textAnchor="middle" fontSize="11" fill="#374151" transform={`rotate(-90 12 ${(y(0) + y(100)) / 2})`}>
            Performance (IPE)
          </text>
          {points.map((p) => (
            <g key={p.id}>
              <circle cx={x(p.x)} cy={y(p.y)} r={5} fill={CURRENT} stroke="#ffffff" strokeWidth={2} />
              {points.length <= 12 && (
                <text x={x(p.x) + 8} y={y(p.y) + 3} fontSize="9" fill="#374151">
                  {p.label.length > 22 ? `${p.label.slice(0, 21)}…` : p.label}
                </text>
              )}
              <a href={p.href} aria-label={`${p.label} : maturité ${p.x.toFixed(0)}, performance ${p.y.toFixed(0)}`}>
                <circle
                  cx={x(p.x)}
                  cy={y(p.y)}
                  r={14}
                  fill="transparent"
                  onMouseEnter={() => setActive(p.id)}
                  onMouseLeave={() => setActive(null)}
                  onFocus={() => setActive(p.id)}
                  onBlur={() => setActive(null)}
                />
              </a>
            </g>
          ))}
        </svg>
        {current && (
          <div
            className="pointer-events-none absolute rounded-md border border-line bg-white px-2 py-1 text-xs shadow"
            style={{ left: `${(x(current.x) / W) * 100}%`, top: `${(y(current.y) / H) * 100}%`, transform: "translate(-50%, -130%)" }}
          >
            <p className="font-medium text-ink">{current.label}</p>
            <p className="text-muted">
              Maturité {current.x.toFixed(0)} · performance {current.y.toFixed(0)}
            </p>
          </div>
        )}
      </div>
    </TableToggle>
  );
}

// --- Haltère « initial → actuel » ------------------------------------------------------------------------------

export interface DumbbellRow {
  code: string;
  name: string;
  initial: number | null;
  current: number | null;
}

export function Dumbbell({ rows }: { rows: DumbbellRow[] }) {
  const [active, setActive] = useState<string | null>(null);
  const data = rows.filter((r) => r.current !== null);
  if (data.length === 0) return <p className="text-sm text-muted">Votre évolution s'affichera après votre premier diagnostic validé.</p>;
  const table = (
    <table className="w-full text-sm">
      <thead className="text-left text-xs text-muted">
        <tr>
          <th className="py-1">Dimension</th>
          <th className="py-1 text-right">Au départ</th>
          <th className="py-1 text-right">Aujourd'hui</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {data.map((r) => (
          <tr key={r.code}>
            <td className="py-1">{r.name}</td>
            <td className="py-1 text-right tabular-nums">{r.initial === null ? "—" : r.initial.toFixed(0)}</td>
            <td className="py-1 text-right tabular-nums">{r.current!.toFixed(0)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
  return (
    <TableToggle table={table}>
      <div className="mb-2 flex gap-4 text-xs text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: INITIAL }} /> Au départ
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: CURRENT }} /> Aujourd'hui
        </span>
      </div>
      <ul className="space-y-1.5">
        {data.map((r) => {
          const from = r.initial ?? r.current!;
          const to = r.current!;
          const [low, high] = [Math.min(from, to), Math.max(from, to)];
          const delta = r.initial === null ? null : to - r.initial;
          return (
            <li
              key={r.code}
              tabIndex={0}
              onMouseEnter={() => setActive(r.code)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(r.code)}
              onBlur={() => setActive(null)}
              aria-label={`${r.name} : ${r.initial === null ? "" : `${r.initial.toFixed(0)} au départ, `}${to.toFixed(0)} aujourd'hui`}
              className={cx("grid grid-cols-[7.5rem_1fr_3.5rem] items-center gap-2 rounded px-1 text-xs", active === r.code && "bg-gray-50")}
            >
              <span className="truncate text-ink">{r.name}</span>
              <span className="relative h-4">
                <span className="absolute inset-x-0 top-1/2 h-px bg-line" />
                <span className="absolute top-1/2 h-0.5 -translate-y-1/2 bg-gray-300" style={{ left: `${low}%`, width: `${high - low}%` }} />
                {r.initial !== null && (
                  <span className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white" style={{ left: `${r.initial}%`, background: INITIAL }} />
                )}
                <span className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white" style={{ left: `${to}%`, background: CURRENT }} />
              </span>
              <span className="text-right tabular-nums text-ink">
                {to.toFixed(0)}
                {delta !== null && delta !== 0 && (
                  <span className="ml-1 text-muted">
                    {delta > 0 ? "+" : "−"}
                    {Math.abs(delta).toFixed(0)}
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-1 text-xs text-muted">Échelle de 0 à 100 par dimension.</p>
    </TableToggle>
  );
}
