/** Indicateurs financiers : Indicateur → formule → données utilisées → résultat → interprétation → source (Doc. 6, § 7). */
import { Badge } from "@/components/ui";
import { formatInput, formatMetric, INPUT_LABELS, type MetricResult, SOURCE_LABELS } from "@/lib/scoring";
import { OrgName } from "@/components/OrgName";

const BAND_TONES: Record<string, "danger" | "warning" | "neutral" | "brand" | "info"> = {
  Critique: "danger",
  Faible: "warning",
  Acceptable: "neutral",
  Bon: "info",
  Excellent: "brand",
};

export function MetricsTable({ metrics }: { metrics: MetricResult[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-line text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-muted">
          <tr>
            <th className="py-2 pr-4">Indicateur</th>
            <th className="py-2 pr-4">Formule</th>
            <th className="py-2 pr-4">Données utilisées</th>
            <th className="py-2 pr-4 text-right">Résultat</th>
            <th className="py-2 pr-4">Interprétation</th>
            <th className="py-2">Source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line align-top">
          {metrics.map((metric) => (
            <tr key={metric.code}>
              <td className="py-2.5 pr-4 font-medium text-ink">{metric.name}</td>
              <td className="py-2.5 pr-4 text-muted">{metric.formula}</td>
              <td className="py-2.5 pr-4 text-xs text-muted">
                {Object.entries(metric.inputs).map(([key, value]) => (
                  <div key={key}>
                    {INPUT_LABELS[key] ?? key} : {formatInput(key, value)}
                  </div>
                ))}
              </td>
              <td className="py-2.5 pr-4 text-right font-semibold tabular-nums text-ink">{formatMetric(metric.value, metric.unit)}</td>
              <td className="py-2.5 pr-4">
                {metric.band ? (
                  <Badge tone={BAND_TONES[metric.band] ?? "neutral"}>{metric.band}</Badge>
                ) : (
                  <span className="text-xs text-muted">{metric.value === null ? "Non évaluable" : "Informatif"}</span>
                )}
              </td>
              <td className="py-2.5 text-xs text-muted">
                {metric.sources.length ? metric.sources.map((s) => SOURCE_LABELS[s] ?? s).join(", ") : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-xs text-muted">
        Seuils d'interprétation indicatifs, à calibrer par secteur avec les experts de <OrgName fallback="l'organisation" />. Les sources « déclaratif » seront
        remplacées par les états financiers vérifiés à partir des phases 3 et 4.
      </p>
    </div>
  );
}
