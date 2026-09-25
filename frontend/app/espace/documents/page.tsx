"use client";

/**
 * « Mes documents » (portail PME) : ce qu'il faut déposer, avant quand, et ce qui a été validé ou refusé
 * (Document 1, § 10). Dépôt par fichier ou par photo depuis le téléphone.
 */
import { useQuery } from "@tanstack/react-query";

import { ComplianceSummary, DeadlineList } from "@/components/documents/DocumentsTab";
import { UploadButton } from "@/components/documents/UploadButton";
import { PmeShell } from "@/components/PmeShell";
import { Alert, Badge, Card, LoadingBlock } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import { DOCUMENT_STATUS, FOLDER_STATE } from "@/lib/documents";
import { formatDate } from "@/lib/format";

export default function PmeDocumentsPage() {
  return (
    <PmeShell title="Mes documents" subtitle="Déposez vos justificatifs : votre conseiller les vérifie et vous répond ici.">
      {(me) => <Content pmeId={me.pme_ids[0]} />}
    </PmeShell>
  );
}

function Content({ pmeId }: { pmeId: string }) {
  const folder = useQuery({
    queryKey: ["folder", pmeId],
    queryFn: () => unwrap(api.GET("/api/v1/pmes/{pme_id}/compliance-folder", { params: { path: { pme_id: pmeId } } })),
  });
  const deadlines = useQuery({
    queryKey: ["deadlines", pmeId],
    queryFn: () => unwrap(api.GET("/api/v1/pmes/{pme_id}/deadlines", { params: { path: { pme_id: pmeId } } })),
  });
  if (folder.isLoading) return <LoadingBlock />;
  if (folder.error) return <Alert>{errorMessage(folder.error)}</Alert>;
  const items = folder.data!.categories.flatMap((c) => c.items);

  return (
    <>
      <Card title="À transmettre">
        {deadlines.data ? <DeadlineList pmeId={pmeId} deadlines={deadlines.data} canUpload /> : <LoadingBlock />}
      </Card>
      <Card title="Mon dossier">
        <div className="mb-4">
          <ComplianceSummary rate={folder.data!.rate} />
        </div>
        <ul className="divide-y divide-line">
          {items.map((item) => {
            const type = item.document_type as { code: string; name: string; guidance: string };
            const state = FOLDER_STATE[item.state];
            const latest = item.documents[0];
            return (
              <li key={type.code} className="space-y-2 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium">{type.name}</p>
                  <Badge tone={state?.tone}>{state?.label ?? item.state}</Badge>
                </div>
                {type.guidance && <p className="text-xs text-muted">{type.guidance}</p>}
                {latest && (
                  <p className="text-xs text-muted">
                    Dernier dépôt le {formatDate(latest.created_at)} : {DOCUMENT_STATUS[latest.status]?.label.toLowerCase() ?? latest.status}
                    {latest.decision_reason && <span className="block text-ink">→ « {latest.decision_reason} »</span>}
                  </p>
                )}
                {item.state !== "CONFORME" && item.state !== "EN_VERIFICATION" && (
                  <UploadButton pmeId={pmeId} fields={{ document_type: type.code, document_id: latest?.id }} label="Déposer un fichier" />
                )}
              </li>
            );
          })}
        </ul>
        <p className="mt-3 text-xs text-muted">
          Formats acceptés : PDF, Word, Excel, CSV, JPG, PNG, HEIC (25 Mo maximum). Masquez les données personnelles de vos salariés.
        </p>
      </Card>
    </>
  );
}
