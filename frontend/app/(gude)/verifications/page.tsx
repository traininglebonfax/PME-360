"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Alert, Badge, EmptyState, LoadingBlock, PageHeader } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import { formatRelative } from "@/lib/format";

/** File de vérification : documents du périmètre en attente d'une décision humaine, les plus anciens d'abord. */
export default function VerificationQueuePage() {
  const queue = useQuery({ queryKey: ["verifications"], queryFn: () => unwrap(api.GET("/api/v1/verifications")) });
  return (
    <>
      <PageHeader title="Documents à vérifier" subtitle="Un document déposé n'est jamais conforme d'office : chaque décision est humaine et motivée." />
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
                </div>
                <Badge tone="warning">À vérifier</Badge>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
