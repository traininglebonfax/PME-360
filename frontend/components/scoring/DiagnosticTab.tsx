"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ChangeExplanation } from "@/components/scoring/ChangeExplanation";
import { HealthCheck } from "@/components/scoring/HealthCheck";
import { MetricsTable } from "@/components/scoring/MetricsTable";
import { ScoreTrend } from "@/components/scoring/ScoreTrend";
import { Alert, Badge, Button, ButtonLink, Card, EmptyState, LoadingBlock, SelectInput } from "@/components/ui";
import { api, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatDate } from "@/lib/format";
import {
  type ChangeExplanation as Explanation,
  DIAGNOSTIC_STATUS_LABELS,
  DIAGNOSTIC_TYPE_LABELS,
  type EngineResult,
  formatPercent,
  formatScore,
  PRIORITY_LABELS,
  SNAPSHOT_KIND_LABELS,
} from "@/lib/scoring";
import { hasPermission, useMe } from "@/lib/session";

type Snapshot = Schemas["SnapshotSummary"];

/** Onglet « Diagnostic & scores » de la fiche PME 360°. */
export function DiagnosticTab({ pmeId }: { pmeId: string }) {
  const { data: me } = useMe();
  const router = useRouter();
  const queryClient = useQueryClient();
  const canRun = hasPermission(me, "diagnostic.validate");
  const health = useQuery({
    queryKey: ["health", pmeId],
    queryFn: () => unwrap(api.GET("/api/v1/pmes/{pme_id}/health-check", { params: { path: { pme_id: pmeId } } })),
  });
  const [kind, setKind] = useState<Schemas["DiagnosticTypeEnum"]>("SUIVI");
  const [compareWith, setCompareWith] = useState<string>("");

  const start = useMutation({
    mutationFn: (type: Schemas["DiagnosticTypeEnum"]) =>
      unwrap(api.POST("/api/v1/pmes/{pme_id}/diagnostics", { params: { path: { pme_id: pmeId } }, body: { type } })),
    onSuccess: (diagnostic) => {
      queryClient.invalidateQueries({ queryKey: ["pme", pmeId] });
      router.push(`/diagnostics/${diagnostic.id}`);
    },
  });

  const history = health.data?.history ?? [];
  const latest = health.data?.snapshot;
  const baselineId = compareWith || (history.length > 1 ? history[0].id : "");
  const comparison = useQuery({
    queryKey: ["compare", latest?.id, baselineId],
    queryFn: async () =>
      (await unwrap(
        api.GET("/api/v1/snapshots/{snapshot_id}/compare/{other_id}", {
          params: { path: { snapshot_id: latest!.id, other_id: baselineId } },
        }),
      )) as unknown as Explanation,
    enabled: Boolean(latest && baselineId && baselineId !== latest.id),
  });

  if (health.isLoading) return <LoadingBlock />;
  if (health.error) return <Alert>{errorMessage(health.error)}</Alert>;
  const data = health.data!;
  const open = data.open_diagnostic as Schemas["Diagnostic"] | null;
  const result = latest?.result as unknown as EngineResult | undefined;
  const delta =
    latest && data.baseline && data.baseline.id !== latest.id && latest.global_score !== null && data.baseline.global_score !== null
      ? Math.round((Number(latest.global_score) - Number(data.baseline.global_score)) * 10) / 10
      : null;

  return (
    <div className="space-y-6">
      {open ? (
        <Card title={`${DIAGNOSTIC_TYPE_LABELS[open.type]} en cours`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted">
              Référence au {formatDate(open.reference_date)} · <Badge tone="info">{DIAGNOSTIC_STATUS_LABELS[open.status]}</Badge>
            </p>
            <div className="flex gap-2">
              <ButtonLink href={`/diagnostics/${open.id}`} variant="secondary">
                Questionnaire
              </ButtonLink>
              {canRun && open.status === "EN_REVUE" && <ButtonLink href={`/diagnostics/${open.id}/revue`}>Revue et validation</ButtonLink>}
            </div>
          </div>
        </Card>
      ) : (
        canRun && (
          <Card title={latest ? "Nouveau diagnostic" : "Démarrer le diagnostic 360°"}>
            {start.error && (
              <div className="mb-3">
                <Alert>{errorMessage(start.error)}</Alert>
              </div>
            )}
            {latest ? (
              <div className="flex flex-wrap items-end gap-3">
                <div className="w-64">
                  <SelectInput
                    label="Type"
                    value={kind}
                    onChange={(e) => setKind(e.target.value as Schemas["DiagnosticTypeEnum"])}
                    options={(["SUIVI", "REEVALUATION", "CLOTURE"] as const).map((value) => ({ value, label: DIAGNOSTIC_TYPE_LABELS[value] }))}
                    placeholder="—"
                  />
                </div>
                <Button onClick={() => start.mutate(kind)} loading={start.isPending}>
                  Démarrer
                </Button>
                <p className="w-full text-xs text-muted">Le diagnostic de suivi reprend les réponses précédentes : la PME confirme ou corrige.</p>
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-muted">
                  Questionnaire adaptatif de 12 dimensions (60 à 90 questions), à remplir avec la PME ou par elle depuis son espace.
                </p>
                <Button onClick={() => start.mutate("INITIAL")} loading={start.isPending}>
                  Démarrer le diagnostic initial
                </Button>
              </div>
            )}
          </Card>
        )
      )}

      {!result ? (
        <EmptyState title="Aucun diagnostic validé">
          Le Health Check, les scores par dimension et le niveau de maturité apparaîtront après la validation du premier diagnostic.
        </EmptyState>
      ) : (
        <>
          <Card
            title={`PME Health Check · ${SNAPSHOT_KIND_LABELS[latest!.kind]} du ${formatDate(latest!.reference_date)}`}
            action={<span className="text-xs text-muted">Référentiel v{latest!.framework_version} · moteur {latest!.engine_version}</span>}
          >
            <HealthCheck result={result} delta={delta} />
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Évolution du score global">
              <ScoreTrend
                points={history.map((s) => ({
                  id: s.id,
                  date: s.reference_date,
                  score: s.global_score === null ? null : Number(s.global_score),
                  label: SNAPSHOT_KIND_LABELS[s.kind],
                }))}
              />
              <HistoryTable history={history} />
            </Card>
            <Card
              title="Explication de l'évolution"
              action={
                history.length > 2 && (
                  <select
                    aria-label="Comparer avec"
                    className="rounded-md border border-line px-2 py-1 text-xs"
                    value={baselineId}
                    onChange={(e) => setCompareWith(e.target.value)}
                  >
                    {history.slice(0, -1).map((s) => (
                      <option key={s.id} value={s.id}>
                        {SNAPSHOT_KIND_LABELS[s.kind]} · {formatDate(s.reference_date)}
                      </option>
                    ))}
                  </select>
                )
              }
            >
              {history.length < 2 ? (
                <p className="text-sm text-muted">Disponible dès le diagnostic de suivi.</p>
              ) : comparison.isLoading ? (
                <LoadingBlock />
              ) : comparison.data ? (
                <ChangeExplanation explanation={comparison.data} />
              ) : (
                <Alert>{errorMessage(comparison.error)}</Alert>
              )}
            </Card>
          </div>

          <Card title="Indicateurs financiers">
            <MetricsTable metrics={result.metrics} />
          </Card>
        </>
      )}
    </div>
  );
}

function HistoryTable({ history }: { history: Snapshot[] }) {
  return (
    <table className="mt-4 min-w-full divide-y divide-line text-sm">
      <caption className="sr-only">Historique des snapshots</caption>
      <thead className="text-left text-xs uppercase tracking-wide text-muted">
        <tr>
          <th className="py-1.5 pr-3">Date</th>
          <th className="py-1.5 pr-3">Type</th>
          <th className="py-1.5 pr-3 text-right">Score</th>
          <th className="py-1.5 pr-3">Niveau</th>
          <th className="py-1.5 pr-3 text-right">Confiance</th>
          <th className="py-1.5">Priorité</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {[...history].reverse().map((s) => (
          <tr key={s.id}>
            <td className="py-1.5 pr-3">{formatDate(s.reference_date)}</td>
            <td className="py-1.5 pr-3 text-muted">{SNAPSHOT_KIND_LABELS[s.kind]}</td>
            <td className="py-1.5 pr-3 text-right font-medium tabular-nums">{formatScore(s.global_score)}</td>
            <td className="py-1.5 pr-3 text-muted">{s.maturity_level ? `N${s.maturity_level} · ${s.maturity_label}` : "—"}</td>
            <td className="py-1.5 pr-3 text-right tabular-nums">{formatPercent(s.confidence)}</td>
            <td className="py-1.5 text-muted">{PRIORITY_LABELS[s.intervention_priority] ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

