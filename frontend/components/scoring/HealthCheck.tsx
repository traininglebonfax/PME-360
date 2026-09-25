/**
 * « PME Health Check » (Document 6, § 10) : score global, niveau (avec plafonnement expliqué), confiance,
 * indices, scores par dimension et écarts à plus fort impact. Barres : une seule série (pas de légende),
 * teinte unique, valeur en bout de barre, info-bulle native au survol.
 */
import { Badge, cx } from "@/components/ui";
import {
  DIMENSION_STATUS_LABELS,
  type EngineResult,
  formatPercent,
  formatScore,
  PRIORITY_LABELS,
  PRIORITY_TONES,
  QUADRANT_LABELS,
} from "@/lib/scoring";

function Tile({ label, value, hint, emphasis = false }: { label: string; value: React.ReactNode; hint?: React.ReactNode; emphasis?: boolean }) {
  return (
    <div className="rounded-xl border border-line bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className={cx("mt-1 font-semibold text-ink", emphasis ? "text-4xl" : "text-xl")}>{value}</p>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function ConfidenceBadge({ value, label }: { value: number; label: string }) {
  const tone = value >= 0.75 ? "brand" : value >= 0.5 ? "warning" : "muted";
  return (
    <Badge tone={tone}>
      Confiance {label.toLowerCase()} · {formatPercent(value)}
    </Badge>
  );
}

export function DimensionBars({ result }: { result: EngineResult }) {
  return (
    <ul className="space-y-3" aria-label="Scores par dimension">
      {result.dimensions.map((dimension) => {
        const score = dimension.score;
        const title = `${dimension.name} : ${score === null ? "non évaluable" : `${formatScore(score)}/100`} · couverture ${formatPercent(dimension.coverage)} · confiance ${dimension.confidence === null ? "—" : formatPercent(dimension.confidence)}`;
        return (
          <li key={dimension.code} title={title}>
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="truncate text-ink">{dimension.short_name}</span>
              <span className="flex items-center gap-2">
                {dimension.status !== "EVALUE" && <Badge tone="muted">{DIMENSION_STATUS_LABELS[dimension.status]}</Badge>}
                <span className="w-8 text-right font-semibold tabular-nums text-ink">{formatScore(score)}</span>
              </span>
            </div>
            <div className="mt-1 h-2.5 rounded-full bg-gray-100" aria-hidden="true">
              {score !== null && (
                <div
                  className={cx("h-2.5 rounded-full", dimension.status === "PROVISOIRE" ? "bg-brand-500/60" : "bg-brand-600")}
                  style={{ width: `${Math.max(score, 2)}%` }}
                />
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function HealthCheck({ result, delta }: { result: EngineResult; delta?: number | null }) {
  const { maturity } = result;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile
          label="Score global 360"
          emphasis
          value={
            <>
              {formatScore(result.global_score)}
              <span className="text-base font-normal text-muted">/100</span>
            </>
          }
          hint={
            <div className="flex flex-wrap items-center gap-1.5">
              <ConfidenceBadge value={result.confidence} label={result.confidence_label} />
              {delta !== undefined && delta !== null && (
                <span className="font-medium text-ink">
                  {delta >= 0 ? "▲ +" : "▼ "}
                  {String(delta).replace(".", ",")} pts depuis la référence
                </span>
              )}
            </div>
          }
        />
        <Tile
          label="Niveau de maturité"
          value={maturity.level ? `N${maturity.level} · ${maturity.label}` : "—"}
          hint={maturity.capped ? `Plafonné (niveau N${maturity.level_uncapped} selon l'IMO)` : maturity.message}
        />
        <Tile
          label="Maturité / Performance"
          value={`${formatScore(result.imo)} / ${formatScore(result.ipe)}`}
          hint={QUADRANT_LABELS[result.quadrant] ?? result.quadrant}
        />
        <Tile
          label="Priorité d'intervention"
          value={<Badge tone={PRIORITY_TONES[result.priority.priority]}>{PRIORITY_LABELS[result.priority.priority]}</Badge>}
          hint={`Exposition au risque : ${formatScore(result.risk_index)}/100 · Maturité digitale : ${formatScore(result.digital.index)} (${result.digital.label ?? "—"})`}
        />
      </div>

      {maturity.gates_failed.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="status">
          <p className="font-medium">
            Niveau plafonné : la porte du niveau N{maturity.gates_failed[0].level} n'est pas franchie.
          </p>
          <ul className="mt-1 list-disc pl-5">
            {maturity.gates_failed.map((gate) => (
              <li key={gate.rule}>
                {gate.message}
                {gate.criteria?.length ? ` (${gate.criteria.join(", ")})` : ""}
                {gate.dimensions?.length ? ` (${gate.dimensions.join(", ")})` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="mb-3 text-sm font-semibold text-ink">Scores par dimension</h3>
          <DimensionBars result={result} />
        </div>
        <div>
          <h3 className="mb-3 text-sm font-semibold text-ink">Écarts à plus fort impact</h3>
          <ol className="space-y-2.5">
            {result.gaps.map((gap, index) => (
              <li key={gap.criterion} className="flex gap-3 text-sm">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand-800">
                  {index + 1}
                </span>
                <div>
                  <p className="text-ink">
                    {gap.name} <span className="font-mono text-xs text-muted">{gap.criterion}</span>
                  </p>
                  <p className="text-xs text-muted">
                    Score {formatScore(gap.score)} · jusqu'à +{String(gap.potential_gain.toFixed(1)).replace(".", ",")} pts
                    de score global
                    {gap.is_critical && " · critère critique"}
                    {gap.capped && " · plafonné faute de preuve"}
                  </p>
                </div>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-xs text-muted">
            Classement provisoire (impact seul). La matrice Impact × Urgence × Risque × Effort et le plan 90 jours arrivent en phase 5.
          </p>
        </div>
      </div>
    </div>
  );
}
