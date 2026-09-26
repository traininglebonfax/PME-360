"use client";

/**
 * Éditeur de workflows (Document 7, § 2 ; Document 10, V1) : pour les actions du plan d'accompagnement, libellés des
 * états (équipe et PME), transitions manuelles autorisées, qui peut les déclencher, motif obligatoire, libellé des
 * boutons. Les états et les transitions automatiques restent gérés par le moteur (affichés, non modifiables).
 * On modifie un brouillon, contrôlé en direct, puis on l'active ; la version précédente est conservée.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Badge, Button, Card, cx, LoadingBlock, PageHeader, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { OrgName } from "@/components/OrgName";

type Admin = Schemas["WorkflowAdmin"];
type Transition = Schemas["WorkflowTransition"];
type States = Admin["active"]["states"];

const KEY = ["workflow-admin", "action"];
const ORDER = [
  "BLOQUE",
  "NON_COMMENCE",
  "EN_COURS",
  "DOCUMENT_DEMANDE",
  "DOCUMENT_RECU",
  "A_VERIFIER",
  "NON_CONFORME",
  "CONFORME",
  "EN_ATTENTE_PME",
  "EN_ATTENTE_GUDE",
  "TERMINE",
  "ABANDONNE",
];
const path = { params: { path: { target: "action" } } };

/** Code technique affiché : neutre, quelle que soit l'organisation (la valeur stockée ne change pas). */
function displayCode(code: string) {
  return code === "EN_ATTENTE_GUDE" ? "EN_ATTENTE_EQUIPE" : code;
}

export default function WorkflowsPage() {
  const queryClient = useQueryClient();
  const admin = useQuery({ queryKey: KEY, queryFn: () => unwrap(api.GET("/api/v1/config/workflows/{target}", path)) });
  const onData = (data: Admin) => {
    queryClient.setQueryData(KEY, data);
    queryClient.invalidateQueries({ queryKey: ["workflow", "action"] });
  };
  const createDraft = useMutation({ mutationFn: () => unwrap(api.POST("/api/v1/config/workflows/{target}/draft", path)), onSuccess: onData });

  if (admin.isLoading) return <LoadingBlock />;
  if (admin.error) return <Alert>{errorMessage(admin.error)}</Alert>;
  const data = admin.data!;

  return (
    <>
      <PageHeader
        title="Workflows"
        subtitle="Étapes des actions du plan d'accompagnement : libellés, passages autorisés, qui les déclenche et quand un motif est exigé."
      />
      <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
        <aside className="space-y-4">
          <Card title="Workflow des actions">
            <p className="text-sm">
              En vigueur : <span className="font-medium">{data.active.version ? `version ${data.active.version}` : "version par défaut"}</span>
            </p>
            {data.history.length > 0 && (
              <ul className="mt-3 space-y-1.5 text-xs text-muted" aria-label="Historique des versions">
                {data.history.map((item) => (
                  <li key={item.id}>
                    <Badge tone={item.status === "ACTIVE" ? "brand" : "muted"}>v{item.version}</Badge>{" "}
                    {item.activated_at && `activée le ${formatDateTime(item.activated_at)}`}
                    {item.activated_by_name && ` par ${item.activated_by_name}`}
                    {item.notes && <span className="block">{item.notes}</span>}
                  </li>
                ))}
              </ul>
            )}
            {!data.draft && (
              <div className="mt-4">
                <Button className="w-full" loading={createDraft.isPending} onClick={() => createDraft.mutate()}>
                  Modifier (créer un brouillon)
                </Button>
                {createDraft.error && <Alert>{errorMessage(createDraft.error)}</Alert>}
              </div>
            )}
          </Card>
          <Card title="Ce qui ne change pas">
            <ul className="list-disc space-y-1 pl-4 text-xs text-muted">
              <li>Les états eux-mêmes et les passages automatiques (dépôt, analyse, vérification, déblocage).</li>
              <li>Une action se termine seulement si tous ses livrables sont conformes.</li>
              <li>L'équipe peut toujours abandonner une action, avec motif.</li>
              <li>La PME peut seulement démarrer ou reprendre, ou signaler qu'elle attend son conseiller.</li>
            </ul>
          </Card>
        </aside>
        <section>
          {data.draft ? (
            <DraftEditor key={data.draft.updated_at} data={data} onData={onData} />
          ) : (
            <WorkflowView states={data.active.states} transitions={data.active.transitions} system={data.system_transitions} />
          )}
        </section>
      </div>
    </>
  );
}

function stateLabel(states: States, code: string) {
  return states[code]?.label ?? code;
}

function WorkflowView({ states, transitions, system }: { states: States; transitions: Transition[]; system: Admin["system_transitions"] }) {
  return (
    <div className="space-y-4">
      <Card title="États">
        <table className="min-w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="py-1.5 pr-3">État</th>
              <th className="py-1.5 pr-3">Libellé équipe</th>
              <th className="py-1.5">Libellé PME</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {ORDER.map((code) => (
              <tr key={code}>
                <td className="py-2 pr-3 font-mono text-xs text-muted">{displayCode(code)}</td>
                <td className="py-2 pr-3">{states[code]?.label}</td>
                <td className="py-2">{states[code]?.pme_label}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {ORDER.filter((code) => transitions.some((t) => t.from === code) || system.some((t) => t.from === code)).map((code) => (
        <Card key={code} title={`Depuis « ${stateLabel(states, code)} »`}>
          <ul className="space-y-1.5 text-sm">
            {transitions
              .filter((t) => t.from === code)
              .map((t) => (
                <li key={t.to}>
                  → <span className="font-medium">{stateLabel(states, t.to)}</span>{" "}
                  <span className="text-xs text-muted">
                    · bouton « {t.button} » · {t.actors.map((a) => (a === "PME" ? "PME" : "l'équipe")).join(" et ")}
                    {t.reason_required && " · motif obligatoire"}
                  </span>
                </li>
              ))}
            {system
              .filter((t) => t.from === code)
              .map((t) => (
                <li key={`sys-${t.to}`} className="text-muted">
                  → {stateLabel(states, t.to)} <span className="text-xs">· automatique : {t.trigger}</span>
                </li>
              ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}

function DraftEditor({ data, onData }: { data: Admin; onData: (data: Admin) => void }) {
  const draft = data.draft!;
  const rules = data.rules;
  const [states, setStates] = useState<States>(draft.states);
  const [transitions, setTransitions] = useState<Transition[]>(draft.transitions);
  const [notes, setNotes] = useState(draft.notes);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const dirty =
    JSON.stringify(states) !== JSON.stringify(draft.states) || JSON.stringify(transitions) !== JSON.stringify(draft.transitions) || notes !== draft.notes;

  const save = useMutation({
    mutationFn: () => unwrap(api.PATCH("/api/v1/config/workflows/{target}/draft", { ...path, body: { states, transitions, notes } })),
    onSuccess: onData,
  });
  const activate = useMutation({
    mutationFn: async () => {
      if (dirty) await unwrap(api.PATCH("/api/v1/config/workflows/{target}/draft", { ...path, body: { states, transitions, notes } }));
      return unwrap(api.POST("/api/v1/config/workflows/{target}/draft/activate", path));
    },
    onSuccess: onData,
  });
  const remove = useMutation({ mutationFn: () => unwrap(api.DELETE("/api/v1/config/workflows/{target}/draft", path)), onSuccess: onData });

  const update = (from: string, to: string, patch: Partial<Transition>) =>
    setTransitions(transitions.map((t) => (t.from === from && t.to === to ? { ...t, ...patch } : t)));
  const toggleActor = (t: Transition, actor: "STAFF" | "PME") =>
    update(t.from, t.to, { actors: t.actors.includes(actor) ? t.actors.filter((a) => a !== actor) : [...t.actors, actor].sort() });
  const issues = data.issues ?? { errors: [], warnings: [] };
  const activateErrors = activate.error instanceof ApiError ? Object.values(activate.error.fieldErrors()) : [];

  return (
    <div className="space-y-4">
      <Card
        title={`Brouillon v${draft.version}`}
        action={dirty ? <Badge tone="warning">Modifications non enregistrées</Badge> : issues.errors.length ? <Badge tone="danger">{issues.errors.length} anomalie(s)</Badge> : <Badge tone="brand">Prêt à activer</Badge>}
      >
        <div className="space-y-3" data-testid="workflow-status">
          {issues.errors.length > 0 && (
            <Alert title="À corriger avant activation">
              <ul className="list-disc pl-4">
                {issues.errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </Alert>
          )}
          {issues.warnings.length > 0 && (
            <Alert tone="warning" title="Points d'attention">
              <ul className="list-disc pl-4">
                {issues.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </Alert>
          )}
          <TextInput label="Notes (ce qui change et pourquoi)" value={notes} onChange={(e) => setNotes(e.target.value)} />
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
              Enregistrer le brouillon
            </Button>
            <Button loading={activate.isPending} onClick={() => activate.mutate()}>
              Activer cette version
            </Button>
            {confirmDelete ? (
              <span className="text-sm">
                Supprimer le brouillon ?{" "}
                <button className="text-red-700 hover:underline" onClick={() => remove.mutate()}>
                  Oui
                </button>{" "}
                <button className="hover:underline" onClick={() => setConfirmDelete(false)}>
                  Non
                </button>
              </span>
            ) : (
              <button className="ml-auto text-xs text-red-700 hover:underline" onClick={() => setConfirmDelete(true)}>
                Supprimer le brouillon
              </button>
            )}
          </div>
          <p className="text-xs text-muted">
            À l'activation, le nouveau workflow s'applique immédiatement aux actions en cours pour leurs prochains passages ; l'historique des actions
            n'est pas modifié.
          </p>
          {activateErrors.length > 0 && (
            <Alert title="Activation impossible">
              <ul className="list-disc pl-4">
                {activateErrors.flatMap((e) => e.split(/(?<=\.) /)).map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </Alert>
          )}
          {[save.error, remove.error, activateErrors.length ? null : activate.error].filter(Boolean).map((err, i) => (
            <Alert key={i}>{errorMessage(err)}</Alert>
          ))}
        </div>
      </Card>

      <Card title="États et libellés">
        <p className="mb-3 text-sm text-muted">Le libellé PME s'affiche dans l'espace de la PME : écrivez simplement, du point de vue du dirigeant.</p>
        <table className="min-w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="py-1.5 pr-3">État</th>
              <th className="py-1.5 pr-3">Libellé équipe</th>
              <th className="py-1.5">Libellé PME</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {ORDER.map((code) => (
              <tr key={code}>
                <td className="py-2 pr-3">
                  <span className="font-mono text-xs text-muted">{displayCode(code)}</span>
                  {rules.terminal.includes(code) && (
                    <span className="ml-1">
                      <Badge tone="muted">final</Badge>
                    </span>
                  )}
                </td>
                <td className="py-2 pr-3">
                  <input
                    aria-label={`Libellé équipe ${code}`}
                    className="w-full rounded-md border border-line px-2 py-1"
                    maxLength={60}
                    value={states[code]?.label ?? ""}
                    onChange={(e) => setStates({ ...states, [code]: { ...states[code], label: e.target.value } })}
                  />
                </td>
                <td className="py-2">
                  <input
                    aria-label={`Libellé PME ${code}`}
                    className="w-full rounded-md border border-line px-2 py-1"
                    maxLength={60}
                    value={states[code]?.pme_label ?? ""}
                    onChange={(e) => setStates({ ...states, [code]: { ...states[code], pme_label: e.target.value } })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {ORDER.filter((code) => !rules.terminal.includes(code)).map((code) => {
        const outgoing = transitions.filter((t) => t.from === code);
        const automatic = data.system_transitions.filter((t) => t.from === code);
        const candidates = ORDER.filter(
          (to) => to !== code && !rules.system_only_targets.includes(to) && !outgoing.some((t) => t.to === to),
        );
        return (
          <Card key={code} title={`Depuis « ${stateLabel(states, code)} »`}>
            <ul className="space-y-3" aria-label={`Transitions depuis ${code}`}>
              {outgoing.map((t) => {
                const mandatory = t.to === rules.mandatory_target;
                const pmeAllowed = rules.pme_targets.includes(t.to);
                return (
                  <li key={t.to} className="rounded-lg border border-line p-3" data-testid={`transition-${code}-${t.to}`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm">
                        → <span className="font-medium">{stateLabel(states, t.to)}</span>
                        {mandatory && (
                          <span className="ml-2">
                            <Badge tone="muted">obligatoire</Badge>
                          </span>
                        )}
                      </p>
                      {!mandatory && (
                        <button className="text-xs text-red-700 hover:underline" onClick={() => setTransitions(transitions.filter((x) => !(x.from === code && x.to === t.to)))}>
                          Retirer ce passage
                        </button>
                      )}
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                      <span className="text-xs text-muted">Déclenché par :</span>
                      <label className="flex items-center gap-1.5">
                        <input type="checkbox" className="accent-brand-600" checked={t.actors.includes("STAFF")} disabled={mandatory} onChange={() => toggleActor(t, "STAFF")} />
                        <OrgName fallback="Équipe" />
                      </label>
                      <label className={cx("flex items-center gap-1.5", !pmeAllowed && "text-muted")} title={pmeAllowed ? undefined : "La PME ne peut pas déclencher ce passage."}>
                        <input
                          type="checkbox"
                          className="accent-brand-600"
                          checked={t.actors.includes("PME")}
                          disabled={!pmeAllowed && !t.actors.includes("PME")}
                          onChange={() => toggleActor(t, "PME")}
                        />
                        PME
                      </label>
                      <label className="flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          className="accent-brand-600"
                          checked={t.reason_required}
                          disabled={mandatory}
                          onChange={(e) => update(code, t.to, { reason_required: e.target.checked })}
                        />
                        Motif obligatoire
                      </label>
                    </div>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      <input
                        aria-label={`Bouton ${code} vers ${t.to}`}
                        className="rounded-md border border-line px-2 py-1 text-sm"
                        placeholder="Libellé du bouton (équipe)"
                        maxLength={60}
                        value={t.button}
                        onChange={(e) => update(code, t.to, { button: e.target.value })}
                      />
                      {t.actors.includes("PME") && (
                        <input
                          aria-label={`Bouton PME ${code} vers ${t.to}`}
                          className="rounded-md border border-line px-2 py-1 text-sm"
                          placeholder="Libellé du bouton côté PME (facultatif)"
                          maxLength={60}
                          value={t.pme_button ?? ""}
                          onChange={(e) => update(code, t.to, { pme_button: e.target.value })}
                        />
                      )}
                    </div>
                  </li>
                );
              })}
              {automatic.map((t) => (
                <li key={`sys-${t.to}`} className="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2 text-sm text-muted">
                  <span aria-hidden>⚙</span> → {stateLabel(states, t.to)} <span className="text-xs">· automatique : {t.trigger}</span>
                </li>
              ))}
            </ul>
            {candidates.length > 0 && (
              <select
                aria-label={`Ajouter un passage depuis ${code}`}
                className="mt-3 rounded-md border border-line px-2 py-1 text-sm"
                value=""
                onChange={(e) =>
                  e.target.value &&
                  setTransitions([
                    ...transitions,
                    { from: code, to: e.target.value, actors: ["STAFF"], reason_required: false, button: stateLabel(states, e.target.value), pme_button: "" },
                  ])
                }
              >
                <option value="">+ Autoriser un passage vers…</option>
                {candidates.map((to) => (
                  <option key={to} value={to}>
                    {stateLabel(states, to)}
                  </option>
                ))}
              </select>
            )}
          </Card>
        );
      })}
    </div>
  );
}
