"use client";

/**
 * Rapports de diagnostic archivés (Document 9, § 7) : chaque version reste téléchargeable ; une nouvelle version
 * se génère sans effacer les précédentes. Téléchargement direct du PDF (session, même origine).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Alert, Badge, Button, Card, EmptyState, LoadingBlock } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { formatSize } from "@/lib/documents";
import { hasPermission, useMe } from "@/lib/session";

export function ReportsList({ pmeId, pmeView = false }: { pmeId: string; pmeView?: boolean }) {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const key = ["reports", pmeId];
  const reports = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/v1/pmes/{pme_id}/reports", { params: { path: { pme_id: pmeId } } })),
  });
  const regenerate = useMutation({
    mutationFn: (diagnosticId: string) =>
      unwrap(api.POST("/api/v1/diagnostics/{diagnostic_id}/report", { params: { path: { diagnostic_id: diagnosticId } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });
  if (reports.isLoading) return <LoadingBlock />;
  if (reports.error) return <Alert>{errorMessage(reports.error)}</Alert>;
  const items = reports.data!;
  const latest = items[0];
  const canGenerate = !pmeView && hasPermission(me, "report.generate");

  if (items.length === 0)
    return (
      <EmptyState title="Aucun rapport">
        {pmeView ? "Votre rapport de diagnostic sera disponible ici après la validation de votre diagnostic." : "Le rapport est édité automatiquement à la validation du diagnostic."}
      </EmptyState>
    );

  return (
    <Card
      title={pmeView ? "Mes rapports" : "Rapports de diagnostic"}
      action={
        canGenerate &&
        latest?.diagnostic && (
          <Button variant="secondary" loading={regenerate.isPending} onClick={() => regenerate.mutate(latest.diagnostic!)}>
            Éditer une nouvelle version
          </Button>
        )
      }
    >
      {!pmeView && (
        <p className="mb-3 text-sm text-muted">
          16 sections, des données figées à la date d'édition. Une nouvelle version reprend l'état actuel (plan, documents) sans modifier les
          précédentes.
        </p>
      )}
      <ul className="divide-y divide-line" aria-label="Rapports">
        {items.map((report) => (
          <li key={report.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
            <div>
              <p className="font-medium text-ink">
                Rapport de diagnostic du {formatDate(report.period)} <Badge tone="muted">v{report.version}</Badge>
              </p>
              <p className="text-xs text-muted">
                Édité le {formatDateTime(report.generated_at)}
                {report.generated_by_name && ` par ${report.generated_by_name}`} · {formatSize(report.size_bytes)}
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
      {regenerate.error && <Alert>{errorMessage(regenerate.error)}</Alert>}
    </Card>
  );
}
