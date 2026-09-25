"use client";

/** Alertes (Document 7, § 8) : prise en compte, résolution, ou ignorée avec motif obligatoire. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Alert as Notice, Badge, Button, EmptyState, LoadingBlock, TextInput } from "@/components/ui";
import { api, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { SEVERITY } from "@/lib/documents";
import { formatRelative } from "@/lib/format";

type AlertItem = Schemas["Alert"];

export function AlertList({ pmeId, showPme = false, scope = "open" }: { pmeId?: string; showPme?: boolean; scope?: "open" | "all" }) {
  const alerts = useQuery({
    queryKey: ["alerts", pmeId ?? "all", scope],
    queryFn: () => unwrap(api.GET("/api/v1/alerts", { params: { query: { pme: pmeId, status: scope } } })),
  });
  if (alerts.isLoading) return <LoadingBlock />;
  if (alerts.error) return <Notice>{errorMessage(alerts.error)}</Notice>;
  if (alerts.data!.length === 0) return <EmptyState title="Aucune alerte ouverte">Les alertes se résolvent automatiquement quand leur cause disparaît.</EmptyState>;
  return (
    <ul className="divide-y divide-line rounded-xl border border-line bg-white">
      {alerts.data!.map((alert) => (
        <AlertRow key={alert.id} alert={alert} showPme={showPme} />
      ))}
    </ul>
  );
}

function AlertRow({ alert, showPme }: { alert: AlertItem; showPme: boolean }) {
  const queryClient = useQueryClient();
  const [ignoring, setIgnoring] = useState(false);
  const [note, setNote] = useState("");
  const transition = useMutation({
    mutationFn: (status: Schemas["AlertTransitionStatusEnum"]) =>
      unwrap(api.POST("/api/v1/alerts/{alert_id}/transition", { params: { path: { alert_id: alert.id } }, body: { status, note } })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  const severity = SEVERITY[alert.severity];
  const open = alert.status === "OUVERTE" || alert.status === "PRISE_EN_COMPTE";
  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={severity.tone}>{severity.label}</Badge>
            <p className="font-medium text-ink">{alert.title}</p>
          </div>
          <p className="mt-1 text-sm text-muted">{alert.message}</p>
          <p className="mt-1 text-xs text-muted">
            {showPme && (
              <>
                <Link href={`/pme/${alert.pme.id}?onglet=alertes`} className="text-brand-700 hover:underline">
                  {alert.pme.name}
                </Link>{" "}
                ·{" "}
              </>
            )}
            {formatRelative(alert.created_at)}
            {alert.status === "PRISE_EN_COMPTE" && " · prise en compte"}
            {!open && ` · ${alert.status === "RESOLUE" ? "résolue" : "ignorée"}${alert.resolution_note ? ` : ${alert.resolution_note}` : ""}`}
          </p>
        </div>
        {open && (
          <div className="flex flex-wrap gap-1">
            {alert.status === "OUVERTE" && (
              <Button variant="secondary" onClick={() => transition.mutate("PRISE_EN_COMPTE")} loading={transition.isPending}>
                Prendre en compte
              </Button>
            )}
            <Button variant="ghost" onClick={() => transition.mutate("RESOLUE")}>
              Résolue
            </Button>
            <Button variant="ghost" onClick={() => setIgnoring(!ignoring)}>
              Ignorer
            </Button>
          </div>
        )}
      </div>
      {ignoring && (
        <form
          className="mt-2 flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            transition.mutate("IGNOREE");
          }}
        >
          <div className="min-w-64 flex-1">
            <TextInput label="Motif (obligatoire)" value={note} onChange={(e) => setNote(e.target.value)} required />
          </div>
          <Button type="submit" variant="secondary">
            Confirmer
          </Button>
        </form>
      )}
      {transition.error && <Notice>{errorMessage(transition.error)}</Notice>}
    </li>
  );
}
