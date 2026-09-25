"use client";

/**
 * Évolution du score global dans le temps (une série : pas de légende, le titre la nomme).
 * Ligne 2px, points ≥ 8px avec anneau de surface, étiquette sur le dernier point seulement,
 * info-bulle au survol et au focus clavier ; les valeurs restent lisibles dans l'historique (vue tableau).
 */
import { useState } from "react";

import { formatDate } from "@/lib/format";
import { formatScore } from "@/lib/scoring";

export interface TrendPoint {
  id: string;
  date: string;
  score: number | null;
  label: string;
}

const WIDTH = 560;
const HEIGHT = 200;
const PAD = { top: 16, right: 40, bottom: 28, left: 32 };

export function ScoreTrend({ points }: { points: TrendPoint[] }) {
  const [active, setActive] = useState<string | null>(null);
  const data = points.filter((p): p is TrendPoint & { score: number } => p.score !== null);
  if (data.length < 2) {
    return <p className="text-sm text-muted">La courbe d'évolution s'affichera dès le deuxième diagnostic validé.</p>;
  }
  const times = data.map((p) => new Date(p.date).getTime());
  const [t0, t1] = [Math.min(...times), Math.max(...times)];
  const x = (t: number) => PAD.left + ((t - t0) / (t1 - t0 || 1)) * (WIDTH - PAD.left - PAD.right);
  const y = (s: number) => PAD.top + (1 - s / 100) * (HEIGHT - PAD.top - PAD.bottom);
  const path = data.map((p, i) => `${i ? "L" : "M"}${x(new Date(p.date).getTime())},${y(p.score)}`).join(" ");
  const last = data[data.length - 1];
  const current = data.find((p) => p.id === active);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full" role="img" aria-label="Évolution du score global">
        {[0, 25, 50, 75, 100].map((tick) => (
          <g key={tick}>
            <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} stroke="#e5e7eb" strokeWidth={1} />
            <text x={PAD.left - 6} y={y(tick) + 4} textAnchor="end" fontSize="10" fill="#6b7280">
              {tick}
            </text>
          </g>
        ))}
        <path d={`${path} L${x(new Date(last.date).getTime())},${y(0)} L${x(t0)},${y(0)} Z`} fill="#0f6b4f" fillOpacity={0.08} />
        <path d={path} fill="none" stroke="#0f6b4f" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {data.map((p) => {
          const cx = x(new Date(p.date).getTime());
          return (
            <g key={p.id}>
              <text x={cx} y={HEIGHT - 8} textAnchor="middle" fontSize="10" fill="#6b7280">
                {formatDate(p.date)}
              </text>
              <circle
                cx={cx}
                cy={y(p.score)}
                r={active === p.id ? 6 : 4.5}
                fill="#0f6b4f"
                stroke="#ffffff"
                strokeWidth={2}
                tabIndex={0}
                aria-label={`${p.label} du ${formatDate(p.date)} : ${formatScore(p.score)}/100`}
                onMouseEnter={() => setActive(p.id)}
                onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(p.id)}
                onBlur={() => setActive(null)}
              />
              {/* Zone de survol plus large que le point */}
              <circle cx={cx} cy={y(p.score)} r={14} fill="transparent" onMouseEnter={() => setActive(p.id)} onMouseLeave={() => setActive(null)} />
            </g>
          );
        })}
        <text x={x(new Date(last.date).getTime()) + 10} y={y(last.score) + 4} fontSize="12" fontWeight="600" fill="#1f2937">
          {formatScore(last.score)}
        </text>
      </svg>
      {current && (
        <div
          className="pointer-events-none absolute rounded-md border border-line bg-white px-2.5 py-1.5 text-xs shadow-md"
          style={{
            left: `${(x(new Date(current.date).getTime()) / WIDTH) * 100}%`,
            top: `${(y(current.score) / HEIGHT) * 100}%`,
            transform: "translate(-50%, -120%)",
          }}
        >
          <p className="font-medium text-ink">{formatScore(current.score)}/100</p>
          <p className="text-muted">
            {current.label} · {formatDate(current.date)}
          </p>
        </div>
      )}
    </div>
  );
}
