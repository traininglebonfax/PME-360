"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Alert, Badge, cx, EmptyState, LoadingBlock, PageHeader } from "@/components/ui";
import { confidenceTone, EXTRACTION_STATUS, formatConfidence } from "@/lib/ai";
import { api, errorMessage, unwrap } from "@/lib/api";
import { DOCUMENT_STATUS, SEVERITY } from "@/lib/documents";
import { formatDateTime, formatRelative } from "@/lib/format";

/**
 * File de vérification priorisée (Document 4, § 7) : anomalies graves d'abord, puis confiance IA faible, puis
 * ancienneté. L'IA prépare la revue ; la décision reste humaine.
 */
const TABS = [
  { key: "a-verifier", label: "À vérifier" },
  { key: "verifies", label: "Déjà vérifiés" },
] as const;

export default function VerificationQueuePage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <Verifications />
    </Suspense>
  );
}

function Verifications() {
  const initialTab = useSearchParams().get("onglet");
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>(initialTab === "verifies" ? "verifies" : "a-verifier");
  return (
    <>
      <PageHeader title="Documents à vérifier" subtitle="Un document déposé n'est jamais conforme d'office : l'IA lit et contrôle, chaque décision reste humaine et motivée." />
      <div className="mb-6 border-b border-line" role="tablist" aria-label="Vérification des documents">
        {TABS.map((item) => (
          <button
            key={item.key}
            role="tab"
            aria-selected={tab === item.key}
            onClick={() => setTab(item.key)}
            className={cx(
              "border-b-2 px-3 py-2.5 text-sm",
              tab === item.key ? "border-brand-600 font-medium text-brand-800" : "border-transparent text-muted hover:text-ink",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      {tab === "a-verifier" ? <PendingList /> : <VerifiedList />}
    </>
  );
}

/** Documents déjà examinés (200 décisions les plus récentes) : la décision se relit depuis l'écran du document. */
function VerifiedList() {
  const [mine, setMine] = useState(false);
  const history = useQuery({
    queryKey: ["verifications", "history", mine],
    queryFn: () => unwrap(api.GET("/api/v1/verifications/history", { params: { query: mine ? { mine: true } : {} } })),
  });
  return (
    <>
      <label className="mb-3 flex items-center gap-2 text-sm text-muted">
        <input type="checkbox" className="accent-brand-600" checked={mine} onChange={(e) => setMine(e.target.checked)} />
        Seulement mes décisions
      </label>
      {history.isLoading ? (
        <LoadingBlock />
      ) : history.error ? (
        <Alert>{errorMessage(history.error)}</Alert>
      ) : history.data!.length === 0 ? (
        <EmptyState title="Aucun document vérifié">Les documents examinés apparaîtront ici, la décision la plus récente en premier.</EmptyState>
      ) : (
        <ul className="divide-y divide-line rounded-xl border border-line bg-white">
          {history.data!.map((document) => {
            const status = DOCUMENT_STATUS[document.conformity_status];
            return (
              <li key={document.id}>
                <Link href={`/verifications/${document.id}`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50">
                  <div className="min-w-0">
                    <p className="font-medium text-ink">{document.document_type.name}</p>
                    <p className="text-sm text-muted">
                      {document.pme.name} · examiné le {formatDateTime(document.verified_at)}
                      {document.verified_by_name && ` par ${document.verified_by_name}`}
                    </p>
                    {document.decision_reason && <p className="mt-0.5 text-xs text-muted">Motif : {document.decision_reason}</p>}
                  </div>
                  <Badge tone={status?.tone}>{status?.label ?? document.conformity_status}</Badge>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}

function PendingList() {
  const queue = useQuery({ queryKey: ["verifications"], queryFn: () => unwrap(api.GET("/api/v1/verifications")) });
  return (
    <>
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
