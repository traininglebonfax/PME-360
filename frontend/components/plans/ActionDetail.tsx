"use client";

/**
 * Fiche action (Document 7, § 4.1) : pourquoi, comment (étapes), documents à fournir (modèle, instructions,
 * points vérifiés), statut et transitions autorisées, dépendances, historique. Partagée conseiller / PME.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { UploadButton } from "@/components/documents/UploadButton";
import { Alert, Badge, Button, Card, LoadingBlock, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { ACTION_STATUS, type ActionStatus, DELIVERABLE_STATUS, DIMENSIONS, formatCost, PHASES, TRANSITION_LABELS } from "@/lib/plans";

type Action = Schemas["ActionDetail"];

export function ActionDetail({ actionId, pmeView = false }: { actionId: string; pmeView?: boolean }) {
  const queryClient = useQueryClient();
  const key = ["action", actionId];
  const action = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/v1/actions/{action_id}", { params: { path: { action_id: actionId } } })),
  });
  const onUpdated = (updated: Action) => {
    queryClient.setQueryData(key, updated);
    queryClient.invalidateQueries({ queryKey: ["plan", updated.pme] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };
  if (action.isLoading) return <LoadingBlock />;
  if (action.error) return <Alert>{errorMessage(action.error)}</Alert>;
  const data = action.data!;
  const status = ACTION_STATUS[data.status];
  const phase = PHASES.find((p) => p.key === data.phase);
  const steps = data.sub_actions as { title: string; done: boolean }[];

  return (
    <>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-muted">
            <Link href={pmeView ? "/espace/plan" : `/pme/${data.pme}?onglet=plan`} className="hover:text-brand-700">
              {pmeView ? "Mon plan" : data.pme_name}
            </Link>{" "}
            · {data.human_ref}
          </p>
          {pmeView ? <h2 className="text-lg font-semibold">{data.title}</h2> : <h1 className="text-2xl font-semibold">{data.title}</h1>}
          <p className="mt-1 text-sm text-muted">
            {DIMENSIONS[data.dimension_code] ?? data.dimension_code} · {phase?.label} · échéance {formatDate(data.due_date)}
            {data.advisor_name && ` · accompagnée par ${data.advisor_name}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {data.overdue && <Badge tone="danger">En retard</Badge>}
          <Badge tone={status.tone}>{pmeView ? status.pme : status.label}</Badge>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-4">
          <Card title="Pourquoi cette action ?">
            <p className="text-sm text-ink">{data.why || data.problem}</p>
            {!pmeView && data.rationale && <p className="mt-2 text-xs text-muted">Justification : {data.rationale}</p>}
            <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted">Objectif</dt>
                <dd>{data.objective}</dd>
              </div>
              <div>
                <dt className="text-muted">Résultat attendu</dt>
                <dd>{data.success_indicator || "—"}</dd>
              </div>
              <div>
                <dt className="text-muted">Coût estimatif</dt>
                <dd>{formatCost(data.estimated_cost_min, data.estimated_cost_max)}</dd>
              </div>
              {data.status === "BLOQUE" && (
                <div>
                  <dt className="text-muted">Disponible après</dt>
                  <dd>{(data.depends_on as { title: string }[]).map((d) => d.title).join(", ")}</dd>
                </div>
              )}
            </dl>
          </Card>

          {steps.length > 0 && <Steps action={data} steps={steps} onUpdated={onUpdated} />}

          <Card title="Documents à fournir">
            {data.deliverables.length === 0 ? (
              <p className="text-sm text-muted">Aucun document n'est demandé pour cette action.</p>
            ) : (
              <ul className="space-y-4">
                {data.deliverables.map((deliverable) => (
                  <DeliverableItem key={deliverable.id} action={data} deliverable={deliverable} pmeView={pmeView} onUploaded={() => queryClient.invalidateQueries({ queryKey: key })} />
                ))}
              </ul>
            )}
          </Card>
        </div>

        <aside className="space-y-4">
          <Transitions action={data} pmeView={pmeView} onUpdated={onUpdated} />
          {!pmeView && ((data.depends_on as unknown[]).length > 0 || (data.dependents as unknown[]).length > 0) && (
            <Card title="Dépendances">
              <DependencyList title="Après" items={data.depends_on as Schemas["ActionRef"][]} />
              <DependencyList title="Débloque" items={data.dependents as Schemas["ActionRef"][]} />
            </Card>
          )}
          <Card title="Historique">
            {data.transitions.length === 0 ? (
              <p className="text-sm text-muted">Aucun changement pour l'instant.</p>
            ) : (
              <ol className="space-y-2 text-sm">
                {data.transitions.map((t) => (
                  <li key={t.id}>
                    <p>
                      {ACTION_STATUS[t.to_status as ActionStatus]?.label ?? t.to_status}{" "}
                      <span className="text-xs text-muted">
                        · {formatDateTime(t.created_at)} · {t.actor_type === "SYSTEM" ? "automatique" : t.actor_name}
                      </span>
                    </p>
                    {t.reason && <p className="text-xs text-muted">{t.reason}</p>}
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </aside>
      </div>
    </>
  );
}

function DependencyList({ title, items }: { title: string; items: Schemas["ActionRef"][] }) {
  if (items.length === 0) return null;
  return (
    <div className="mb-2 text-sm">
      <p className="text-muted">{title}</p>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <Link href={`/actions/${item.id}`} className="text-brand-700 hover:underline">
              {item.human_ref} {item.title}
            </Link>{" "}
            <span className="text-xs text-muted">({ACTION_STATUS[item.status as ActionStatus]?.label})</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Steps({ action, steps, onUpdated }: { action: Action; steps: { title: string; done: boolean }[]; onUpdated: (a: Action) => void }) {
  const save = useMutation({
    mutationFn: (next: { title: string; done: boolean }[]) =>
      unwrap(api.PATCH("/api/v1/actions/{action_id}", { params: { path: { action_id: action.id } }, body: { sub_actions: next } })),
    onSuccess: onUpdated,
  });
  const locked = ["BLOQUE", "TERMINE", "ABANDONNE"].includes(action.status);
  return (
    <Card title="Comment faire ?">
      <ul className="space-y-1.5">
        {steps.map((step, index) => (
          <li key={index}>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5 accent-brand-600"
                checked={step.done}
                disabled={locked || save.isPending}
                onChange={(e) => save.mutate(steps.map((s, i) => (i === index ? { ...s, done: e.target.checked } : s)))}
              />
              <span className={step.done ? "text-muted line-through" : ""}>{step.title}</span>
            </label>
          </li>
        ))}
      </ul>
      {save.error && <p className="mt-2 text-sm text-red-700">{errorMessage(save.error)}</p>}
    </Card>
  );
}

function DeliverableItem({
  action,
  deliverable,
  pmeView,
  onUploaded,
}: {
  action: Action;
  deliverable: Schemas["Deliverable"];
  pmeView: boolean;
  onUploaded: () => void;
}) {
  const status = DELIVERABLE_STATUS[deliverable.status];
  const template = deliverable.template;
  const canUpload =
    !["BLOQUE", "TERMINE", "ABANDONNE"].includes(action.status) && ["ATTENDU", "NON_CONFORME"].includes(deliverable.status);
  return (
    <li className="rounded-lg border border-line p-3" data-testid="deliverable">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="font-medium">{deliverable.title}</p>
        <Badge tone={status?.tone}>{status?.label}</Badge>
      </div>
      {deliverable.status === "NON_CONFORME" && deliverable.reason && (
        <p className="mt-1 text-sm text-red-800">À reprendre : « {deliverable.reason} »</p>
      )}
      {template && (
        <details className="mt-2 text-sm">
          <summary className="cursor-pointer text-brand-700">Comment le préparer</summary>
          <p className="mt-1 text-ink">{template.instructions}</p>
          {(template.verification_criteria as string[]).length > 0 && (
            <>
              <p className="mt-2 text-xs font-medium text-muted">Ce que votre conseiller vérifiera :</p>
              <ul className="list-inside list-disc text-xs text-muted">
                {(template.verification_criteria as string[]).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
        </details>
      )}
      {deliverable.document && !pmeView && (
        <Link href={`/verifications/${deliverable.document}`} className="mt-2 inline-block text-sm text-brand-700 hover:underline">
          Voir le document déposé
        </Link>
      )}
      {canUpload && (
        <div className="mt-3">
          <UploadButton
            pmeId={action.pme}
            fields={{ deliverable_id: deliverable.id }}
            label={deliverable.status === "NON_CONFORME" ? "Déposer une nouvelle version" : "Déposer le document"}
            compact={!pmeView}
            onDone={onUploaded}
          />
        </div>
      )}
    </li>
  );
}

function Transitions({ action, pmeView, onUpdated }: { action: Action; pmeView: boolean; onUpdated: (a: Action) => void }) {
  const [target, setTarget] = useState<ActionStatus | null>(null);
  const [reason, setReason] = useState("");
  const move = useMutation({
    mutationFn: ({ to, why }: { to: ActionStatus; why: string }) =>
      unwrap(api.POST("/api/v1/actions/{action_id}/transition", { params: { path: { action_id: action.id } }, body: { to, reason: why } })),
    onSuccess: (updated) => {
      setTarget(null);
      setReason("");
      onUpdated(updated);
    },
  });
  const order: ActionStatus[] = ["EN_COURS", "DOCUMENT_DEMANDE", "TERMINE", "EN_ATTENTE_PME", "EN_ATTENTE_GUDE", "ABANDONNE"];
  const allowed = (action.allowed_transitions as ActionStatus[])
    .filter((to) => !(to === "TERMINE" && action.deliverables.length > 0))
    .sort((a, b) => order.indexOf(a) - order.indexOf(b));
  const hint =
    action.status === "BLOQUE"
      ? "Cette action démarrera automatiquement quand les actions dont elle dépend seront terminées."
      : action.deliverables.length > 0 && !["TERMINE", "ABANDONNE"].includes(action.status)
        ? "L'action se termine automatiquement quand tous les documents sont vérifiés conformes."
        : null;

  return (
    <Card title={pmeView ? "Où en est cette action ?" : "Statut"}>
      {hint && <p className="mb-3 text-sm text-muted">{hint}</p>}
      {allowed.length === 0 ? (
        <p className="text-sm text-muted">{pmeView ? "Rien à faire de votre côté pour l'instant." : "Aucune transition manuelle possible."}</p>
      ) : (
        <div className="flex flex-col gap-2">
          {allowed.map((to) => (
            <Button
              key={to}
              variant={to === "ABANDONNE" ? "ghost" : to === "EN_COURS" ? "primary" : "secondary"}
              loading={move.isPending && move.variables?.to === to}
              onClick={() => (to === "ABANDONNE" || to === "EN_ATTENTE_PME" || to === "EN_ATTENTE_GUDE" ? setTarget(to) : move.mutate({ to, why: "" }))}
            >
              {pmeView && to === "EN_COURS" ? (action.started_at ? "Reprendre l'action" : "Je démarre cette action") : pmeView && to === "EN_ATTENTE_GUDE" ? "J'attends mon conseiller" : TRANSITION_LABELS[to] ?? to}
            </Button>
          ))}
        </div>
      )}
      {target && (
        <form
          className="mt-3 space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            move.mutate({ to: target, why: reason });
          }}
        >
          <TextInput label={target === "ABANDONNE" ? "Motif de l'abandon (obligatoire)" : "Précision (facultatif)"} required={target === "ABANDONNE"} value={reason} onChange={(e) => setReason(e.target.value)} />
          <div className="flex gap-2">
            <Button type="submit" variant={target === "ABANDONNE" ? "danger" : "primary"} loading={move.isPending}>
              Confirmer
            </Button>
            <Button type="button" variant="ghost" onClick={() => setTarget(null)}>
              Annuler
            </Button>
          </div>
        </form>
      )}
      {move.error && !(move.error instanceof ApiError && move.error.code === "validation_error") && (
        <div className="mt-2">
          <Alert>{errorMessage(move.error)}</Alert>
        </div>
      )}
      {action.started_at && <p className="mt-3 text-xs text-muted">Démarrée le {formatDate(action.started_at)}</p>}
      {action.abandon_reason && <p className="mt-1 text-xs text-muted">Abandon : {action.abandon_reason}</p>}
    </Card>
  );
}
