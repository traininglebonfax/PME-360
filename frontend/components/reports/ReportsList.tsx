"use client";

/**
 * Rapports archivés d'une PME (Document 9, § 7) : diagnostic (à la validation), suivi (trimestriel ou à la demande),
 * conformité et annuel (à la demande). Chaque version reste téléchargeable ; une nouvelle édition n'efface pas les
 * précédentes. Téléchargement direct du PDF (session, même origine).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Alert, Badge, Button, Card, EmptyState, LoadingBlock } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { formatSize } from "@/lib/documents";
import { EDITABLE_REPORT_TYPES, type PmeReportType, REPORT_TYPES, reportLabel } from "@/lib/reports";
import { hasPermission, useMe } from "@/lib/session";

export function ReportsList({ pmeId, pmeView = false }: { pmeId: string; pmeView?: boolean }) {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const key = ["reports", pmeId];
  const reports = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/v1/pmes/{pme_id}/reports", { params: { path: { pme_id: pmeId } } })),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: key });
  const regenerate = useMutation({
    mutationFn: (diagnosticId: string) =>
      unwrap(api.POST("/api/v1/diagnostics/{diagnostic_id}/report", { params: { path: { diagnostic_id: diagnosticId } } })),
    onSuccess: refresh,
  });
  const edit = useMutation({
    mutationFn: (type: PmeReportType) =>
      unwrap(api.POST("/api/v1/pmes/{pme_id}/reports", { params: { path: { pme_id: pmeId } }, body: { type } })),
    onSuccess: refresh,
  });
  if (reports.isLoading) return <LoadingBlock />;
  if (reports.error) return <Alert>{errorMessage(reports.error)}</Alert>;
  const items = reports.data!;
  const latestDiagnostic = items.find((r) => r.type === "DIAGNOSTIC");
  const canGenerate = !pmeView && hasPermission(me, "report.generate");
  const error = regenerate.error ?? edit.error;

  const editor = canGenerate && (
    <div className="mb-4 rounded-lg border border-line p-3" aria-label="Éditer un rapport">
      <p className="mb-2 text-sm font-medium text-ink">Éditer un rapport</p>
      <div className="flex flex-wrap gap-2">
        {EDITABLE_REPORT_TYPES.map((type) => (
          <Button
            key={type}
            variant="secondary"
            className="px-3 py-1.5"
            title={REPORT_TYPES[type].hint}
            loading={edit.isPending && edit.variables === type}
            disabled={edit.isPending}
            onClick={() => edit.mutate(type)}
          >
            {REPORT_TYPES[type].label}
          </Button>
        ))}
        {latestDiagnostic?.diagnostic && (
          <Button variant="ghost" className="px-3 py-1.5" loading={regenerate.isPending} onClick={() => regenerate.mutate(latestDiagnostic.diagnostic!)}>
            Nouvelle version du rapport de diagnostic
          </Button>
        )}
      </div>
      <ul className="mt-2 space-y-0.5 text-xs text-muted">
        {EDITABLE_REPORT_TYPES.map((type) => (
          <li key={type}>
            <span className="font-medium text-ink">{REPORT_TYPES[type].label}</span> : {REPORT_TYPES[type].hint}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted">Données figées à la date d'édition ; la PME et son conseiller sont prévenus. Une nouvelle édition ne modifie pas les précédentes.</p>
    </div>
  );

  if (items.length === 0 && !canGenerate)
    return (
      <EmptyState title="Aucun rapport">
        {pmeView ? "Votre rapport de diagnostic sera disponible ici après la validation de votre diagnostic." : "Le rapport de diagnostic est édité automatiquement à la validation du diagnostic."}
      </EmptyState>
    );

  return (
    <Card title={pmeView ? "Mes rapports" : "Rapports"}>
      {editor}
      {error && <Alert>{errorMessage(error)}</Alert>}
      {items.length === 0 ? (
        <p className="text-sm text-muted">Aucun rapport pour l'instant. Le rapport de diagnostic est édité automatiquement à la validation du diagnostic.</p>
      ) : (
        <ul className="divide-y divide-line" aria-label="Rapports">
          {items.map((report) => (
            <li key={report.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm" data-testid="report-row">
              <div>
                <p className="font-medium text-ink">
                  {reportLabel(report.type, report.period)} <Badge tone="muted">v{report.version}</Badge>
                </p>
                <p className="text-xs text-muted">
                  Édité le {formatDateTime(report.generated_at)}
                  {report.generated_by_name ? ` par ${report.generated_by_name}` : " automatiquement"} · {formatSize(report.size_bytes)}
                  {report.confidence !== null && ` · confiance ${Math.round(report.confidence * 100)} %`}
                </p>
              </div>
              <a
                href={`/api/v1/reports/${report.id}/pdf`}
                className="rounded-lg border border-brand-600 px-3 py-1.5 text-sm font-medium text-brand-700 hover:bg-brand-50"
                download
              >
                Télécharger le PDF
              </a>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
