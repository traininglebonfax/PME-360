"use client";

/**
 * Onglet « Plan & actions » de la fiche PME (Document 7, § 4) : recommandations notées à revoir, génération du
 * plan (horizons, dépendances, livrables), cycle de validation (conseiller → GUDE → acceptation PME), suivi.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Button, Card, cx, EmptyState, LoadingBlock, SelectInput, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { useActionStatus } from "@/lib/actionWorkflow";
import { AXES, DIMENSIONS, PHASES, PLAN_STATUS, priorityLabel, RECOMMENDATION_STATUS, SOURCE_LABELS } from "@/lib/plans";
import { hasPermission, useMe } from "@/lib/session";
import { OrgName } from "@/components/OrgName";

type Recommendation = Schemas["Recommendation"];
type Plan = Schemas["PlanDetail"];

export function PlanTab({ pmeId }: { pmeId: string }) {
  const { data: me } = useMe();
  const canEdit = hasPermission(me, "plan.edit");
  const plan = useQuery({
    queryKey: ["plan", pmeId],
    queryFn: async () => {
      const { data, response } = await api.GET("/api/v1/pmes/{pme_id}/plan", { params: { path: { pme_id: pmeId } } });
      if (response.status === 204) return null;
      if (!response.ok) throw new ApiError(response.status, { detail: "Plan indisponible." });
      return data as Plan;
    },
  });
  if (plan.isLoading) return <LoadingBlock />;
  if (plan.error) return <Alert>{errorMessage(plan.error)}</Alert>;
  const current = plan.data;
  const reviewing = !current || current.status === "BROUILLON" || current.status === "CLOS";

  return (
    <div className="space-y-6">
      {current && <PlanPanel plan={current} pmeId={pmeId} canEdit={canEdit} />}
      {reviewing && <RecommendationsPanel pmeId={pmeId} canEdit={canEdit} hasDraft={current?.status === "BROUILLON"} />}
    </div>
  );
}

// --- Recommandations ---------------------------------------------------------------------------------------------

function RecommendationsPanel({ pmeId, canEdit, hasDraft }: { pmeId: string; canEdit: boolean; hasDraft: boolean }) {
  const queryClient = useQueryClient();
  const key = ["recommendations", pmeId];
  const recommendations = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/v1/pmes/{pme_id}/recommendations", { params: { path: { pme_id: pmeId } } })),
    retry: false,
  });
  const refresh = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/pmes/{pme_id}/recommendations", { params: { path: { pme_id: pmeId } } })),
    onSuccess: (data) => queryClient.setQueryData(key, data),
  });
  const generate = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/pmes/{pme_id}/plan/generate", { params: { path: { pme_id: pmeId } }, body: { title: "" } })),
    onSuccess: (plan) => {
      queryClient.setQueryData(["plan", pmeId], plan);
      queryClient.invalidateQueries({ queryKey: key });
    },
  });

  if (recommendations.isLoading) return <LoadingBlock />;
  if (recommendations.error)
    return (
      <EmptyState title="Pas encore de recommandations">
        {recommendations.error instanceof ApiError && recommendations.error.code === "no_validated_diagnostic"
          ? "Les recommandations s'appuient sur un diagnostic validé : validez d'abord le diagnostic de la PME."
          : errorMessage(recommendations.error)}
      </EmptyState>
    );
  const items = [...recommendations.data!].sort((a, b) => b.priority_final - a.priority_final);
  const accepted = items.filter((r) => r.status === "ACCEPTEE").length;
  const pending = items.filter((r) => r.status === "PROPOSEE").length;

  return (
    <Card
      title="Recommandations"
      action={
        canEdit && (
          <Button variant="secondary" loading={refresh.isPending} onClick={() => refresh.mutate()}>
            {items.length ? "Actualiser" : "Calculer les recommandations"}
          </Button>
        )
      }
    >
      <p className="mb-4 text-sm text-muted">
        Proposées par les règles à partir du score courant, notées Impact × Urgence × Risque × Effort. Vous acceptez, rejetez (motif) ou
        ajustez la priorité (motif) ; les recommandations acceptées deviennent les actions du plan.
      </p>
      {refresh.error && <Alert>{errorMessage(refresh.error)}</Alert>}
      {items.length === 0 ? (
        <EmptyState title="Aucune recommandation">Calculez les recommandations pour cette PME.</EmptyState>
      ) : (
        <ul className="divide-y divide-line" aria-label="Recommandations">
          {items.map((rec) => (
            <RecommendationRow key={rec.id} rec={rec} canEdit={canEdit} onChange={(updated) => queryClient.setQueryData<Recommendation[]>(key, (old) => old?.map((r) => (r.id === updated.id ? updated : r)))} />
          ))}
        </ul>
      )}
      {canEdit && (
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
          <ManualRecommendation pmeId={pmeId} onAdded={() => queryClient.invalidateQueries({ queryKey: key })} />
          <div className="ml-auto flex items-center gap-3">
            <span className="text-sm text-muted">
              {accepted} acceptée(s){pending ? ` · ${pending} à revoir` : ""}
            </span>
            <Button disabled={accepted === 0} loading={generate.isPending} onClick={() => generate.mutate()}>
              {hasDraft ? "Régénérer le plan" : "Générer le plan"}
            </Button>
          </div>
        </div>
      )}
      {generate.error && (
        <div className="mt-3">
          <Alert>{errorMessage(generate.error)}</Alert>
        </div>
      )}
    </Card>
  );
}

function RecommendationRow({ rec, canEdit, onChange }: { rec: Recommendation; canEdit: boolean; onChange: (r: Recommendation) => void }) {
  const [mode, setMode] = useState<"view" | "reject" | "adjust">("view");
  const [reason, setReason] = useState("");
  const [axes, setAxes] = useState({ impact: rec.impact, urgency: rec.urgency, risk: rec.risk, effort: rec.effort });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const decide = useMutation({
    mutationFn: (body: Schemas["RecommendationDecisionRequest"]) =>
      unwrap(api.POST("/api/v1/recommendations/{recommendation_id}/decision", { params: { path: { recommendation_id: rec.id } }, body })),
    onSuccess: (updated) => {
      setMode("view");
      setErrors({});
      onChange(updated);
    },
    onError: (error) => setErrors(error instanceof ApiError ? error.fieldErrors() : {}),
  });
  const status = RECOMMENDATION_STATUS[rec.status];
  const priority = priorityLabel(rec.priority_final);
  const details = (rec.scoring_details ?? {}) as Record<string, string>;
  const editable = canEdit && rec.status !== "CONVERTIE";

  return (
    <li className="py-4" data-testid="recommendation">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-medium text-ink">{rec.offer.title}</p>
          <p className="text-sm text-ink">{rec.problem}</p>
          <p className="mt-1 text-sm text-muted">{rec.rationale}</p>
          <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
            <Badge tone="muted">{DIMENSIONS[rec.offer.dimension_code] ?? rec.offer.dimension_code}</Badge>
            <Badge tone="muted">{SOURCE_LABELS[rec.source] ?? rec.source}</Badge>
            {AXES.map((axis) => (
              <span key={axis.key} title={details[axis.key]} className="rounded bg-gray-100 px-1.5 py-0.5 text-gray-700">
                {axis.label} {rec[axis.key]}/5
              </span>
            ))}
          </div>
          {rec.priority_override_reason && <p className="mt-1 text-xs text-muted">Priorité ajustée : {rec.priority_override_reason}</p>}
          {rec.status === "REJETEE" && rec.decision_reason && <p className="mt-1 text-xs text-muted">Motif du rejet : {rec.decision_reason}</p>}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <span className="text-lg font-semibold tabular-nums">
            {rec.priority_final.toFixed(0)}
            <span className="text-xs font-normal text-muted"> PS</span>
          </span>
          <div className="flex gap-1">
            <Badge tone={priority.tone}>{priority.label}</Badge>
            <Badge tone={status?.tone}>{status?.label ?? rec.status}</Badge>
          </div>
        </div>
      </div>
      {editable && mode === "view" && (
        <div className="mt-3 flex flex-wrap gap-2">
          {rec.status !== "ACCEPTEE" && (
            <Button className="px-3 py-1.5" loading={decide.isPending} onClick={() => decide.mutate({ status: "ACCEPTEE", reason: "", priority_reason: "" })}>
              Accepter
            </Button>
          )}
          {rec.status !== "REJETEE" && (
            <Button variant="secondary" className="px-3 py-1.5" onClick={() => setMode("reject")}>
              Rejeter
            </Button>
          )}
          <Button variant="ghost" className="px-3 py-1.5" onClick={() => setMode("adjust")}>
            Ajuster la priorité
          </Button>
          {rec.status !== "PROPOSEE" && (
            <Button variant="ghost" className="px-3 py-1.5" onClick={() => decide.mutate({ status: "PROPOSEE", reason: "", priority_reason: "" })}>
              Remettre en proposition
            </Button>
          )}
        </div>
      )}
      {mode === "reject" && (
        <form
          className="mt-3 flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            decide.mutate({ status: "REJETEE", reason, priority_reason: "" });
          }}
        >
          <div className="min-w-64 flex-1">
            <TextInput label="Motif du rejet" required value={reason} onChange={(e) => setReason(e.target.value)} error={errors.reason} />
          </div>
          <Button type="submit" variant="danger" loading={decide.isPending}>
            Rejeter
          </Button>
          <Button type="button" variant="ghost" onClick={() => setMode("view")}>
            Annuler
          </Button>
        </form>
      )}
      {mode === "adjust" && (
        <form
          className="mt-3 space-y-2 rounded-lg bg-gray-50 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            decide.mutate({ status: rec.status === "REJETEE" ? "PROPOSEE" : (rec.status as "PROPOSEE" | "ACCEPTEE"), reason: "", priority_reason: reason, ...axes });
          }}
        >
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {AXES.map((axis) => (
              <SelectInput
                key={axis.key}
                label={`${axis.label} (1 à 5)`}
                value={String(axes[axis.key])}
                placeholder="—"
                onChange={(e) => setAxes({ ...axes, [axis.key]: Number(e.target.value) })}
                options={[1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: String(n) }))}
              />
            ))}
          </div>
          <TextInput label="Motif de l'ajustement" required value={reason} onChange={(e) => setReason(e.target.value)} error={errors.priority_reason} />
          <div className="flex gap-2">
            <Button type="submit" loading={decide.isPending}>
              Enregistrer
            </Button>
            <Button type="button" variant="ghost" onClick={() => setMode("view")}>
              Annuler
            </Button>
          </div>
        </form>
      )}
      {decide.error && !(decide.error instanceof ApiError && decide.error.code === "validation_error") && (
        <div className="mt-2">
          <Alert>{errorMessage(decide.error)}</Alert>
        </div>
      )}
    </li>
  );
}

function ManualRecommendation({ pmeId, onAdded }: { pmeId: string; onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ offer_code: "", problem: "", rationale: "" });
  const offers = useQuery({ queryKey: ["support-offers"], queryFn: () => unwrap(api.GET("/api/v1/support-offers")), enabled: open });
  const add = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/pmes/{pme_id}/recommendations/manual", { params: { path: { pme_id: pmeId } }, body: form })),
    onSuccess: () => {
      setOpen(false);
      setForm({ offer_code: "", problem: "", rationale: "" });
      onAdded();
    },
  });
  if (!open)
    return (
      <Button variant="ghost" onClick={() => setOpen(true)}>
        + Ajouter une recommandation
      </Button>
    );
  return (
    <form
      className="w-full space-y-2 rounded-lg bg-gray-50 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        add.mutate();
      }}
    >
      <SelectInput
        label="Offre d'accompagnement"
        required
        value={form.offer_code}
        onChange={(e) => setForm({ ...form, offer_code: e.target.value })}
        options={(offers.data ?? []).filter((o) => o.is_active).map((o) => ({ value: o.code, label: `${o.title} (${DIMENSIONS[o.dimension_code] ?? o.dimension_code})` }))}
      />
      <TextInput label="Problème constaté" required value={form.problem} onChange={(e) => setForm({ ...form, problem: e.target.value })} />
      <TextInput label="Justification" required value={form.rationale} onChange={(e) => setForm({ ...form, rationale: e.target.value })} />
      {add.error && <Alert>{errorMessage(add.error)}</Alert>}
      <div className="flex gap-2">
        <Button type="submit" loading={add.isPending}>
          Ajouter
        </Button>
        <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
          Annuler
        </Button>
      </div>
    </form>
  );
}

// --- Plan --------------------------------------------------------------------------------------------------------

function PlanPanel({ plan, pmeId, canEdit }: { plan: Plan; pmeId: string; canEdit: boolean }) {
  const queryClient = useQueryClient();
  const [pendingReason, setPendingReason] = useState<null | "reopen" | "close" | "version" | "accept_offline">(null);
  const [reason, setReason] = useState("");
  const onPlan = (updated: Plan) => {
    queryClient.setQueryData(["plan", pmeId], updated);
    queryClient.invalidateQueries({ queryKey: ["recommendations", pmeId] });
    setPendingReason(null);
    setReason("");
  };
  const transition = useMutation({
    mutationFn: (body: Schemas["PlanTransitionRequest"]) =>
      unwrap(api.POST("/api/v1/plans/{plan_id}/transition", { params: { path: { plan_id: plan.id } }, body })),
    onSuccess: onPlan,
  });
  const newVersion = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/plans/{plan_id}/new-version", { params: { path: { plan_id: plan.id } }, body: { reason } })),
    onSuccess: onPlan,
  });
  const status = PLAN_STATUS[plan.status];
  const progress = plan.progress as { total: number; done: number; rate: number | null };
  const awaitingPme = plan.status === "EN_VALIDATION" && plan.validated_at;

  return (
    <Card
      title={`${plan.title} · v${plan.version}`}
      action={<Badge tone={status?.tone}>{awaitingPme ? "En attente d'acceptation par la PME" : status?.label}</Badge>}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-muted">
          <p>
            Démarrage le {formatDate(plan.horizon_start)} · {progress.done}/{progress.total} action(s) terminée(s)
            {plan.validated_by_name && ` · validé par ${plan.validated_by_name} le ${formatDateTime(plan.validated_at)}`}
            {plan.accepted_by_name &&
              ` · ${plan.accepted_offline ? "acceptation de la PME enregistrée par" : "accepté par"} ${plan.accepted_by_name} le ${formatDateTime(plan.accepted_at)}`}
          </p>
          {plan.close_reason && <p>Clos : {plan.close_reason}</p>}
        </div>
        {canEdit && (
          <div className="flex flex-wrap gap-2">
            {plan.status === "BROUILLON" && (
              <Button loading={transition.isPending} onClick={() => transition.mutate({ action: "submit", reason: "" })}>
                Soumettre à validation
              </Button>
            )}
            {plan.status === "EN_VALIDATION" && !plan.validated_at && (
              <Button loading={transition.isPending} onClick={() => transition.mutate({ action: "validate", reason: "" })}>
                Valider (<OrgName />)
              </Button>
            )}
            {awaitingPme && (
              <Button variant="secondary" onClick={() => setPendingReason("accept_offline")}>
                Enregistrer l'acceptation de la PME
              </Button>
            )}
            {plan.status === "EN_VALIDATION" && (
              <Button variant="secondary" onClick={() => setPendingReason("reopen")}>
                Renvoyer en brouillon
              </Button>
            )}
            {["EN_VALIDATION", "VALIDE", "EN_COURS"].includes(plan.status) && (
              <Button variant="secondary" onClick={() => setPendingReason("version")}>
                Nouvelle version
              </Button>
            )}
            {["VALIDE", "EN_COURS"].includes(plan.status) && (
              <Button variant="ghost" onClick={() => setPendingReason("close")}>
                Clore le plan
              </Button>
            )}
          </div>
        )}
      </div>
      {progress.rate !== null && (
        <div className="mb-4 h-2 overflow-hidden rounded-full bg-gray-100" role="progressbar" aria-valuenow={Math.round(progress.rate * 100)} aria-label="Avancement du plan">
          <div className="h-full bg-brand-600" style={{ width: `${Math.round(progress.rate * 100)}%` }} />
        </div>
      )}
      {pendingReason && (
        <form
          className="mb-4 flex flex-wrap items-end gap-2 rounded-lg bg-gray-50 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (pendingReason === "version") newVersion.mutate();
            else transition.mutate({ action: pendingReason, reason });
          }}
        >
          <div className="min-w-64 flex-1">
            <TextInput
              label={
                pendingReason === "version"
                  ? "Motif de la nouvelle version"
                  : pendingReason === "close"
                    ? "Motif de clôture"
                    : pendingReason === "accept_offline"
                      ? "Comment la PME a-t-elle accepté le plan ? (entretien, PV signé…)"
                      : "Motif du renvoi"
              }
              required
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
          <Button type="submit" loading={transition.isPending || newVersion.isPending}>
            Confirmer
          </Button>
          <Button type="button" variant="ghost" onClick={() => setPendingReason(null)}>
            Annuler
          </Button>
        </form>
      )}
      {(transition.error || newVersion.error) && (
        <div className="mb-4">
          <Alert>{errorMessage(transition.error ?? newVersion.error)}</Alert>
        </div>
      )}
      <PhaseBoard actions={plan.actions} actionHref={(id) => `/actions/${id}`} />
    </Card>
  );
}

export function PhaseBoard({ actions, actionHref, pmeView = false }: { actions: Schemas["Action"][]; actionHref: (id: string) => string; pmeView?: boolean }) {
  const statusOf = useActionStatus();
  const phases = PHASES.filter((phase) => actions.some((a) => a.phase === phase.key));
  if (actions.length === 0) return <EmptyState title="Aucune action" />;
  return (
    <div className="space-y-5">
      {phases.map((phase) => (
        <section key={phase.key} aria-label={phase.label}>
          <h3 className="mb-2 text-sm font-semibold text-ink">
            {phase.label} <span className="font-normal text-muted">· {phase.hint}</span>
          </h3>
          <ul className="grid gap-2 md:grid-cols-2">
            {actions
              .filter((a) => a.phase === phase.key)
              .map((action) => {
                const status = statusOf(action.status);
                const deps = action.depends_on as { human_ref: string; title: string }[];
                return (
                  <li key={action.id}>
                    <Link
                      href={actionHref(action.id)}
                      className={cx(
                        "block h-full rounded-lg border bg-white p-3 hover:border-brand-600",
                        action.overdue ? "border-red-300" : "border-line",
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="font-medium text-ink">{action.title}</p>
                        <Badge tone={status.tone}>{pmeView ? status.pme : status.label}</Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted">
                        {action.human_ref} · {DIMENSIONS[action.dimension_code] ?? action.dimension_code} · échéance {formatDate(action.due_date)}
                        {!pmeView && ` · PS ${action.priority_score.toFixed(0)}`}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                        {action.overdue && <Badge tone="danger">En retard</Badge>}
                        {action.deliverables_total > 0 && (
                          <Badge tone={action.deliverables_conform === action.deliverables_total ? "brand" : "neutral"}>
                            Documents {action.deliverables_conform}/{action.deliverables_total}
                          </Badge>
                        )}
                        {action.status === "BLOQUE" && deps.length > 0 && <span className="text-muted">Disponible après : {deps.map((d) => d.title).join(", ")}</span>}
                      </div>
                    </Link>
                  </li>
                );
              })}
          </ul>
        </section>
      ))}
    </div>
  );
}
