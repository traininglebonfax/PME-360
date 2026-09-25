"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Badge, Button, Card, LoadingBlock, PageHeader, TextInput } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

/** Journal d'audit de l'organisation (lecture seule) et vérification de la chaîne de hash. */
export default function AuditPage() {
  const [action, setAction] = useState("");
  const logs = useQuery({
    queryKey: ["audit", action],
    queryFn: () => unwrap(api.GET("/api/v1/audit-logs", { params: { query: { action: action || undefined } } })),
  });
  const verification = useQuery({
    queryKey: ["audit-verify"],
    queryFn: () => unwrap(api.GET("/api/v1/audit-logs/verify")),
    enabled: false,
  });

  return (
    <>
      <PageHeader
        title="Journal d'audit"
        subtitle="Toutes les actions sont enregistrées, horodatées et chaînées : aucune entrée ne peut être modifiée ni supprimée."
        actions={
          <Button variant="secondary" loading={verification.isFetching} onClick={() => verification.refetch()}>
            Vérifier l'intégrité
          </Button>
        }
      />
      {verification.data && (
        <div className="mb-4">
          {verification.data.valid ? (
            <Alert tone="success">Chaîne intègre : {verification.data.entries_checked} entrées vérifiées.</Alert>
          ) : (
            <Alert title="Altération détectée">Première entrée invalide : n° {verification.data.first_invalid_id}.</Alert>
          )}
        </div>
      )}
      <Card>
        <div className="mb-4 max-w-sm">
          <TextInput label="Filtrer par action" placeholder="ex. pme.updated" value={action} onChange={(e) => setAction(e.target.value)} />
        </div>
        {logs.isLoading ? (
          <LoadingBlock />
        ) : logs.error ? (
          <Alert>{errorMessage(logs.error)}</Alert>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="py-2 pr-4">Date</th>
                  <th className="py-2 pr-4">Action</th>
                  <th className="py-2 pr-4">Acteur</th>
                  <th className="py-2 pr-4">Objet</th>
                  <th className="hidden py-2 pr-4 lg:table-cell">Empreinte</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {logs.data!.map((entry) => (
                  <tr key={entry.id}>
                    <td className="whitespace-nowrap py-2 pr-4 text-muted">{formatDateTime(entry.at)}</td>
                    <td className="py-2 pr-4">
                      <p>{entry.label}</p>
                      <p className="font-mono text-xs text-muted">{entry.action}</p>
                    </td>
                    <td className="py-2 pr-4">
                      {entry.actor_name ?? <Badge tone="muted">{entry.actor_type === "SYSTEM" ? "Système" : entry.actor_type}</Badge>}
                    </td>
                    <td className="py-2 pr-4 text-muted">
                      {entry.entity_type}
                      {entry.entity_id && <span className="font-mono text-xs"> {entry.entity_id.slice(0, 8)}…</span>}
                    </td>
                    <td className="hidden py-2 pr-4 font-mono text-xs text-muted lg:table-cell">{entry.hash.slice(0, 12)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
