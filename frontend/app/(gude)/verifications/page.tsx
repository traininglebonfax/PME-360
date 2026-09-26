"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Alert, Badge, EmptyState, LoadingBlock, PageHeader } from "@/components/ui";
import { confidenceTone, EXTRACTION_STATUS, formatConfidence } from "@/lib/ai";
import { api, errorMessage, unwrap } from "@/lib/api";
import { SEVERITY } from "@/lib/documents";
import { formatRelative } from "@/lib/format";

/**
 * File de vérification priorisée (Document 4, § 7) : anomalies graves d'abord, puis confiance IA faible, puis
 * ancienneté. L'IA prépare la revue ; la décision reste humaine.
 */
export default function VerificationQueuePage() {
  const queue = useQuery({ queryKey: ["verifications"], queryFn: () => unwrap(api.GET("/api/v1/verifications")) });
  return (
    <>
      <PageHeader title="Documents à vérifier" subtitle="Un document déposé n'est jamais conforme d'office : l'IA lit et contrôle, chaque décision reste humaine et motivée." />
      {queue.isLoading ? (
        <LoadingBlock />
      ) : queue.error ? (
        <Alert>{errorMessage(queue.error)}</Alert>
      ) : queue.data!.length === 0 ? (
        <EmptyState title="Aucun document en attente">Les nouveaux dépôts de vos PME apparaîtront ici.</EmptyState>
      ) : (
        <ul className="divide-y divide-line rounded-xl border border-line bg-white">
          {queue.data!.map((document) => (
            <li key={document.id}>
              <Link href={`/verifications/${document.id}`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50">
                <div className="min-w-0">
                  <p className="font-medium text-ink">{document.document_type.name}</p>
                  <p className="text-sm text-muted">
                    {document.pme.name} · déposé {formatRelative(document.created_at)}
                    {document.uploaded_by_name && ` par ${document.uploaded_by_name}`}
                    {document.deadline && ` · échéance ${document.deadline.period_label}`}
                  </p>
                  {document.ai?.reason && <p className="mt-0.5 text-xs text-muted">IA : {document.ai.reason}</p>}
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {document.ai ? (
                    <>
                      {document.ai.anomalies > 0 && (
                        <Badge tone={SEVERITY[document.ai.max_severity ?? "MOYENNE"]?.tone ?? "warning"}>
                          {document.ai.anomalies} anomalie{document.ai.anomalies > 1 ? "s" : ""}
                        </Badge>
                      )}
                      <Badge tone={EXTRACTION_STATUS[document.ai.status]?.tone}>IA : {EXTRACTION_STATUS[document.ai.status]?.label ?? document.ai.status}</Badge>
                      {document.ai.confidence !== null && (
                        <Badge tone={confidenceTone(document.ai.confidence)}>confiance {formatConfidence(document.ai.confidence)}</Badge>
                      )}
                    </>
                  ) : (
                    <Badge tone="warning">À vérifier</Badge>
                  )}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
