"use client";

/**
 * Analyse financière (Document 4, fonction D) : états financiers extraits (provisoires tant qu'ils ne sont pas
 * revus), ratios calculés de façon déterministe, et commentaire rédigé par l'IA en brouillon à relire.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { MetricsTable } from "@/components/scoring/MetricsTable";
import { Alert, Badge, Button, Card, EmptyState, LoadingBlock } from "@/components/ui";
import { formatConfidence, PROVIDER_LABELS, STATEMENT_STATUS } from "@/lib/ai";
import { api, errorMessage, unwrap } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { MetricResult } from "@/lib/scoring";
import { hasPermission, useMe } from "@/lib/session";

const POINT_TONES: Record<string, string> = {
  positif: "border-l-brand-600",
  vigilance: "border-l-amber-500",
  alerte: "border-l-red-600",
};

const STATEMENT_KEYS: [string, string][] = [
  ["ca_n", "Chiffre d'affaires"],
  ["resultat_net", "Résultat net"],
  ["ebe", "EBE"],
  ["capitaux_propres", "Capitaux propres"],
  ["total_passif", "Total du bilan"],
];

export function FinancialTab({ pmeId }: { pmeId: string }) {
  const { data: me } = useMe();
  const analysis = useQuery({
    queryKey: ["financial-analysis", pmeId],
    queryFn: () => unwrap(api.GET("/api/v1/pmes/{pme_id}/financial-analysis", { params: { path: { pme_id: pmeId } } })),
  });
  const interpret = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/api/v1/pmes/{pme_id}/financial-analysis/interpretation", { params: { path: { pme_id: pmeId } } })),
  });

  if (analysis.isLoading) return <LoadingBlock />;
  if (analysis.error) return <Alert>{errorMessage(analysis.error)}</Alert>;
  const data = analysis.data!;
  const evaluable = data.metrics.some((m) => m.value !== null);

  return (
    <div className="space-y-6">
      <Card title="États financiers">
        {data.statements.length === 0 ? (
          <EmptyState title="Aucun état financier lu">
            Déposez les états financiers SYSCOHADA de la PME : l'IA en extrait les montants, que vous validez dans « Documents à vérifier ».
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="py-2 pr-4">Exercice clos le</th>
                  <th className="py-2 pr-4">Statut</th>
                  {STATEMENT_KEYS.map(([, label]) => (
                    <th key={label} className="py-2 pr-4 text-right">
                      {label}
                    </th>
                  ))}
                  <th className="py-2 pr-4">Confiance</th>
                  <th className="py-2">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.statements.map((statement) => (
                  <tr key={statement.id}>
                    <td className="py-2.5 pr-4 font-medium">{formatDate(statement.fiscal_year_end)}</td>
                    <td className="py-2.5 pr-4">
                      <Badge tone={STATEMENT_STATUS[statement.status]?.tone}>{STATEMENT_STATUS[statement.status]?.label ?? statement.status}</Badge>
                    </td>
                    {STATEMENT_KEYS.map(([key]) => (
                      <td key={key} className="py-2.5 pr-4 text-right tabular-nums">
                        {statement.values[key] !== undefined ? statement.values[key].toLocaleString("fr-FR") : "—"}
                      </td>
                    ))}
                    <td className="py-2.5 pr-4 text-muted">{formatConfidence(statement.confidence)}</td>
                    <td className="py-2.5">
                      <Link href={`/verifications/${statement.document_id}`} className="text-brand-700 hover:underline">
                        {statement.document_title || "Document"}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-muted">Montants en FCFA. Un état « provisoire » n'a pas encore été relu par un conseiller.</p>
          </div>
        )}
      </Card>

      <Card title={`Indicateurs au ${formatDate(data.as_of)}`}>
        <MetricsTable metrics={data.metrics as unknown as MetricResult[]} />
      </Card>

      {hasPermission(me, "ai.review") && (
        <Card title="Commentaire des indicateurs">
          {!interpret.data ? (
            <>
              <p className="text-sm text-muted">
                L'IA rédige un commentaire à partir des seuls indicateurs ci-dessus (aucun calcul n'est fait par l'IA). C'est un brouillon à relire
                avant tout partage avec la PME.
              </p>
              <Button variant="secondary" className="mt-3" disabled={!evaluable} loading={interpret.isPending} onClick={() => interpret.mutate()}>
                Rédiger un commentaire
              </Button>
              {!evaluable && <p className="mt-2 text-xs text-muted">Aucun indicateur évaluable : rien à commenter.</p>}
              {interpret.error && <p className="mt-2 text-sm text-red-700">{errorMessage(interpret.error)}</p>}
            </>
          ) : (
            <div className="space-y-3 text-sm" data-testid="interpretation">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="warning">Brouillon à relire</Badge>
                <span className="text-xs text-muted">{PROVIDER_LABELS[interpret.data.provider] ?? interpret.data.provider}</span>
              </div>
              <p className="text-ink">{interpret.data.summary}</p>
              <ul className="space-y-2">
                {interpret.data.points.map((point, index) => (
                  <li key={index} className={`border-l-4 pl-3 ${POINT_TONES[point.tone] ?? "border-l-gray-300"}`}>
                    <span className="font-medium">{point.metric}</span> — {point.comment}
                  </li>
                ))}
              </ul>
              {interpret.data.limits.length > 0 && (
                <div className="text-xs text-muted">
                  <p className="font-medium">Limites</p>
                  <ul className="list-inside list-disc">
                    {interpret.data.limits.map((limit) => (
                      <li key={limit}>{limit}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="flex gap-3 text-xs">
                <Link href={`/ia/analyses/${interpret.data.analysis_id}`} className="text-brand-700 hover:underline">
                  Voir l'analyse IA
                </Link>
                <button className="text-muted hover:text-ink" onClick={() => interpret.mutate()}>
                  Régénérer
                </button>
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
