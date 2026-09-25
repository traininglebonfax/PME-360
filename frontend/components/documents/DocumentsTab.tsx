"use client";

/** Dossier numérique de conformité d'une PME (Document 8, § 3) : taux, catégories, échéances. */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { UploadButton } from "@/components/documents/UploadButton";
import { Alert, Badge, Card, cx, EmptyState, Kpi, LoadingBlock } from "@/components/ui";
import { api, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { DEADLINE_STATUS, DOCUMENT_STATUS, FOLDER_STATE } from "@/lib/documents";
import { formatDate } from "@/lib/format";
import { formatPercent } from "@/lib/scoring";
import { hasPermission, useMe } from "@/lib/session";

type Deadline = Schemas["Deadline"];

export function ComplianceSummary({ rate }: { rate: Schemas["Rate"] }) {
  const counts = rate.counts as Record<string, number>;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
      <Kpi
        label="Conformité documentaire"
        value={rate.rate === null ? "—" : formatPercent(rate.rate)}
        hint={`${rate.eligible} élément(s) exigible(s)`}
      />
      <Kpi label="Conformes" value={(counts.CONFORME ?? 0) + (counts.CONFORME_SOUS_RESERVE ?? 0)} />
      <Kpi label="Manquants" value={counts.MANQUANT ?? 0} />
      <Kpi label="Expirés" value={counts.EXPIRE ?? 0} />
      <Kpi label="En vérification" value={counts.EN_VERIFICATION ?? 0} />
      <Kpi label="Non conformes" value={counts.NON_CONFORME ?? 0} />
    </div>
  );
}

export function DeadlineList({ pmeId, deadlines, canUpload }: { pmeId: string; deadlines: Deadline[]; canUpload: boolean }) {
  if (deadlines.length === 0) return <p className="text-sm text-muted">Aucune échéance ouverte.</p>;
  return (
    <ul className="divide-y divide-line">
      {deadlines.map((deadline) => {
        const status = DEADLINE_STATUS[deadline.status];
        const late = deadline.days_to_due < 0 && ["A_FOURNIR", "EN_RETARD"].includes(deadline.status);
        return (
          <li key={deadline.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <p className="text-sm font-medium">
                {deadline.document_type_name} <span className="font-normal text-muted">· {deadline.period_label}</span>
              </p>
              <p className={cx("text-xs", late ? "text-red-700" : "text-muted")}>
                À transmettre avant le {formatDate(deadline.due_date)}
                {late ? ` · ${-deadline.days_to_due} jour(s) de retard` : deadline.days_to_due >= 0 ? ` · dans ${deadline.days_to_due} jour(s)` : ""}
                {deadline.is_critical && " · obligation critique"}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge tone={status?.tone}>{status?.label ?? deadline.status}</Badge>
              {canUpload && ["A_FOURNIR", "EN_RETARD", "NON_CONFORME", "EXPIRE", "INCOHERENT"].includes(deadline.status) && (
                <UploadButton
                  pmeId={pmeId}
                  compact
                  fields={{ deadline_id: deadline.id, period_start: deadline.period_start, period_end: deadline.period_end }}
                />
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function DocumentsTab({ pmeId }: { pmeId: string }) {
  const { data: me } = useMe();
  const canUpload = hasPermission(me, "document.upload");
  const canVerify = hasPermission(me, "document.verify");
  const [open, setOpen] = useState<string | null>(null);
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
  const data = folder.data!;

  return (
    <div className="space-y-6">
      <ComplianceSummary rate={data.rate} />
      <Card title="Échéances ouvertes">
        {deadlines.data ? <DeadlineList pmeId={pmeId} deadlines={deadlines.data} canUpload={canUpload} /> : <LoadingBlock />}
      </Card>
      {data.categories.length === 0 ? (
        <EmptyState title="Dossier vide">
          Les documents demandés apparaîtront après le diagnostic et l'activation des obligations.
        </EmptyState>
      ) : (
        data.categories.map((category) => (
          <Card key={category.code} title={category.name}>
            <ul className="divide-y divide-line">
              {category.items.map((item) => {
                const type = item.document_type as { code: string; name: string; guidance: string };
                const state = FOLDER_STATE[item.state];
                const key = `${category.code}-${type.code}`;
                return (
                  <li key={key} className="py-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <button className="text-left text-sm font-medium hover:text-brand-700" onClick={() => setOpen(open === key ? null : key)}>
                          {type.name}
                        </button>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {item.required && <Badge tone="warning">Exigé · {item.criteria.join(", ")}</Badge>}
                          {item.obligation && <Badge tone="info">{item.obligation}</Badge>}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge tone={state?.tone}>{state?.label ?? item.state}</Badge>
                        {canUpload && <UploadButton pmeId={pmeId} compact fields={{ document_type: type.code }} />}
                      </div>
                    </div>
                    {(open === key || item.documents.length > 0) && (
                      <div className="mt-2 space-y-1.5 pl-1">
                        {type.guidance && open === key && <p className="text-xs text-muted">{type.guidance}</p>}
                        {item.documents.map((document) => {
                          const status = DOCUMENT_STATUS[document.status];
                          return (
                            <div key={document.id} className="flex flex-wrap items-center gap-2 text-xs text-muted">
                              <Badge tone={status?.tone}>{status?.label ?? document.status}</Badge>
                              <span>
                                v{document.current_version_no} · déposé le {formatDate(document.created_at)}
                                {document.expires_at && ` · valable jusqu'au ${formatDate(document.expires_at)}`}
                              </span>
                              {document.decision_reason && <span className="text-ink">« {document.decision_reason} »</span>}
                              {canVerify && (
                                <Link href={`/verifications/${document.id}`} className="font-medium text-brand-700 hover:underline">
                                  {document.status === "A_VERIFIER" ? "Vérifier" : "Ouvrir"}
                                </Link>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </Card>
        ))
      )}
    </div>
  );
}
