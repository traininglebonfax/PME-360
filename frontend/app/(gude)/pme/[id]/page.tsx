"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";

import { LifecycleBadge } from "@/components/LifecycleBadge";
import { DiagnosticTab } from "@/components/scoring/DiagnosticTab";
import { Alert, Badge, Button, Card, cx, EmptyState, Kpi, LoadingBlock, PendingKpi, SelectInput, TextInput } from "@/components/ui";
import { formatPercent, formatScore, PRIORITY_LABELS } from "@/lib/scoring";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatDate, formatDateTime, formatRelative } from "@/lib/format";
import { EXIT_REASON_LABELS, LIFECYCLE_LABELS, LIFECYCLE_NEXT, PERSON_ROLE_LABELS, ROLE_IN_PME_LABELS, SIZE_LABELS } from "@/lib/labels";
import { toOptions, useReference } from "@/lib/references";
import { hasPermission, useMe } from "@/lib/session";

type Pme = Schemas["Pme"];

const TABS = [
  { key: "synthese", label: "Synthèse" },
  { key: "identite", label: "Identité" },
  { key: "dirigeants", label: "Dirigeants" },
  { key: "suivi", label: "Suivi" },
  { key: "historique", label: "Historique" },
  { key: "diagnostic", label: "Diagnostic & scores" },
  { key: "documents", label: "Documents", phase: 3 },
  { key: "plan", label: "Plan & actions", phase: 5 },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function PmeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const initialTab = useSearchParams().get("onglet");
  const [tab, setTab] = useState<TabKey>(TABS.some((t) => t.key === initialTab) ? (initialTab as TabKey) : "synthese");
  const pme = useQuery({
    queryKey: ["pme", id],
    queryFn: () => unwrap(api.GET("/api/v1/pmes/{id}", { params: { path: { id } } })),
  });

  if (pme.isLoading) return <LoadingBlock />;
  if (pme.error)
    return (
      <Alert title="PME introuvable">
        {pme.error instanceof ApiError && pme.error.status === 404
          ? "Cette PME n'existe pas ou n'est pas dans votre périmètre."
          : errorMessage(pme.error)}
      </Alert>
    );
  const data = pme.data!;

  return (
    <>
      <nav className="mb-2 text-sm text-muted">
        <Link href="/pme" className="hover:text-brand-700">
          PME
        </Link>{" "}
        / {data.legal_name}
      </nav>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{data.legal_name}</h1>
          <p className="mt-1 text-sm text-muted">
            {[data.trade_name, data.legal_form?.name, data.sector?.name, data.region?.name].filter(Boolean).join(" · ") || "Fiche à compléter"}
          </p>
        </div>
        <LifecycleBadge status={data.lifecycle_status} />
      </div>

      <div className="mb-6 overflow-x-auto border-b border-line" role="tablist" aria-label="Fiche PME 360°">
        <div className="flex gap-1">
          {TABS.map((item) => (
            <button
              key={item.key}
              role="tab"
              aria-selected={tab === item.key}
              onClick={() => setTab(item.key)}
              className={cx(
                "whitespace-nowrap border-b-2 px-3 py-2.5 text-sm",
                tab === item.key ? "border-brand-600 font-medium text-brand-800" : "border-transparent text-muted hover:text-ink",
              )}
            >
              {item.label}
              {"phase" in item && <span className="ml-1.5 text-xs text-gray-400">P{item.phase}</span>}
            </button>
          ))}
        </div>
      </div>

      {tab === "synthese" && <Synthesis pme={data} />}
      {tab === "identite" && <Identity pme={data} />}
      {tab === "dirigeants" && <Persons pme={data} />}
      {tab === "suivi" && <FollowUp pme={data} />}
      {tab === "historique" && <Timeline pmeId={data.id} />}
      {tab === "diagnostic" && <DiagnosticTab pmeId={data.id} />}
      {(tab === "documents" || tab === "plan") && (
        <EmptyState title="Module en cours de construction">
          {tab === "documents" && "Le dossier numérique de conformité et les échéances arrivent en phase 3."}
          {tab === "plan" && "Le plan d'accompagnement 90 jours et les actions arrivent en phase 5."}
        </EmptyState>
      )}
    </>
  );
}

function Synthesis({ pme }: { pme: Pme }) {
  const primary = pme.persons.find((p) => p.is_primary_contact);
  const health = useQuery({
    queryKey: ["health", pme.id],
    queryFn: () => unwrap(api.GET("/api/v1/pmes/{pme_id}/health-check", { params: { path: { pme_id: pme.id } } })),
  });
  const snapshot = health.data?.snapshot;
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="grid grid-cols-2 gap-3 lg:col-span-2">
        <Kpi
          label="Score global 360"
          value={snapshot ? `${formatScore(snapshot.global_score)}/100` : "—"}
          hint={snapshot ? `Confiance ${formatPercent(snapshot.confidence)} · ${formatDate(snapshot.reference_date)}` : "Aucun diagnostic validé"}
        />
        <Kpi
          label="Niveau de maturité"
          value={snapshot?.maturity_level ? `N${snapshot.maturity_level} · ${snapshot.maturity_label}` : "—"}
          hint={snapshot ? PRIORITY_LABELS[snapshot.intervention_priority] : undefined}
        />
        <PendingKpi label="Conformité documentaire" phase={3} />
        <PendingKpi label="Actions du plan" phase={5} />
      </div>
      <Card title="En bref">
        <dl className="space-y-3 text-sm">
          <Row label="Conseiller principal" value={pme.principal_advisor?.full_name ?? "Non assigné"} />
          <Row label="Contact principal" value={primary ? `${primary.full_name} (${PERSON_ROLE_LABELS[primary.role]})` : "—"} />
          <Row label="Effectif déclaré" value={pme.headcount ?? "—"} />
          <Row label="Intégration" value={formatDate(pme.onboarding_started_at)} />
          <Row label="Dernière activité" value={formatRelative(pme.last_activity_at)} />
        </dl>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-medium text-ink">{value}</dd>
    </div>
  );
}

function useInvalidatePme(id: string) {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["pme", id] });
    queryClient.invalidateQueries({ queryKey: ["timeline", id] });
    queryClient.invalidateQueries({ queryKey: ["pmes"] });
  };
}

const IDENTITY_FIELDS = new Set(["trade_name", "phone", "email", "website", "address", "commune"]);

function Identity({ pme }: { pme: Pme }) {
  const { data: me } = useMe();
  const invalidate = useInvalidatePme(pme.id);
  const legalForms = useReference("legal-forms");
  const sectors = useReference("sectors");
  const regions = useReference("regions");
  const fullEdit = hasPermission(me, "pme.update");
  const canEdit = fullEdit || hasPermission(me, "pme.update_identity");
  const initial = {
    legal_name: pme.legal_name,
    trade_name: pme.trade_name ?? "",
    legal_form: pme.legal_form?.id ?? "",
    rccm_number: pme.rccm_number ?? "",
    ncc: pme.ncc ?? "",
    cnps_employer_number: pme.cnps_employer_number ?? "",
    creation_date: pme.creation_date ?? "",
    sector: pme.sector?.id ?? "",
    region: pme.region?.id ?? "",
    commune: pme.commune ?? "",
    address: pme.address ?? "",
    phone: pme.phone ?? "",
    email: pme.email ?? "",
    website: pme.website ?? "",
    headcount: pme.headcount?.toString() ?? "",
    size_category: pme.size_category ?? "NON_DETERMINEE",
  };
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  const save = useMutation({
    mutationFn: () => {
      const changed = Object.fromEntries(
        Object.entries(form).filter(([key, value]) => value !== initial[key as keyof typeof initial]),
      ) as Record<string, string>;
      const body: Record<string, unknown> = { ...changed };
      for (const key of ["legal_form", "sector", "region", "creation_date"]) if (key in body) body[key] = body[key] || null;
      if ("headcount" in body) body.headcount = body.headcount === "" ? null : Number(body.headcount);
      return unwrap(api.PATCH("/api/v1/pmes/{id}", { params: { path: { id: pme.id } }, body: body as Schemas["PatchedPmeRequest"] }));
    },
    onSuccess: () => {
      setSaved(true);
      setErrors({});
      invalidate();
    },
    onError: (err) => setErrors(err instanceof ApiError ? err.fieldErrors() : {}),
  });

  const editable = (key: string) => canEdit && (fullEdit || IDENTITY_FIELDS.has(key));
  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setSaved(false);
    setForm((current) => ({ ...current, [key]: event.target.value }));
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };

  return (
    <Card title="Identité de l'entreprise">
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {save.error && !(save.error instanceof ApiError && save.error.code === "validation_error") && (
          <div className="sm:col-span-2 lg:col-span-3">
            <Alert>{errorMessage(save.error)}</Alert>
          </div>
        )}
        {saved && (
          <div className="sm:col-span-2 lg:col-span-3">
            <Alert tone="success">Modifications enregistrées.</Alert>
          </div>
        )}
        <TextInput label="Raison sociale" value={form.legal_name} onChange={set("legal_name")} disabled={!editable("legal_name")} error={errors.legal_name} />
        <TextInput label="Sigle ou nom commercial" value={form.trade_name} onChange={set("trade_name")} disabled={!editable("trade_name")} />
        <SelectInput label="Forme juridique" value={form.legal_form} onChange={set("legal_form")} options={toOptions(legalForms.data)} disabled={!editable("legal_form")} />
        <TextInput label="N° RCCM" value={form.rccm_number} onChange={set("rccm_number")} disabled={!editable("rccm_number")} error={errors.rccm_number} />
        <TextInput label="N° compte contribuable" value={form.ncc} onChange={set("ncc")} disabled={!editable("ncc")} error={errors.ncc} />
        <TextInput label="N° employeur CNPS" value={form.cnps_employer_number} onChange={set("cnps_employer_number")} disabled={!editable("cnps_employer_number")} />
        <TextInput label="Date de création" type="date" value={form.creation_date} onChange={set("creation_date")} disabled={!editable("creation_date")} error={errors.creation_date} />
        <SelectInput label="Secteur" value={form.sector} onChange={set("sector")} options={toOptions(sectors.data)} disabled={!editable("sector")} />
        <TextInput label="Effectif déclaré" type="number" min={0} value={form.headcount} onChange={set("headcount")} disabled={!editable("headcount")} error={errors.headcount} />
        <SelectInput
          label="Taille (déclarée)"
          value={form.size_category}
          onChange={set("size_category")}
          placeholder="Non déterminée"
          options={Object.entries(SIZE_LABELS).filter(([v]) => v !== "NON_DETERMINEE").map(([value, label]) => ({ value, label }))}
          disabled={!editable("size_category")}
        />
        <SelectInput label="Région ou district" value={form.region} onChange={set("region")} options={toOptions(regions.data)} disabled={!editable("region")} />
        <TextInput label="Commune" value={form.commune} onChange={set("commune")} disabled={!editable("commune")} />
        <TextInput label="Adresse" value={form.address} onChange={set("address")} disabled={!editable("address")} />
        <TextInput label="Téléphone" type="tel" value={form.phone} onChange={set("phone")} disabled={!editable("phone")} />
        <TextInput label="E-mail" type="email" value={form.email} onChange={set("email")} disabled={!editable("email")} error={errors.email} />
        <TextInput label="Site web" type="url" value={form.website} onChange={set("website")} disabled={!editable("website")} error={errors.website} />
        {canEdit && (
          <div className="flex justify-end sm:col-span-2 lg:col-span-3">
            <Button type="submit" loading={save.isPending}>
              Enregistrer
            </Button>
          </div>
        )}
      </form>
    </Card>
  );
}

function Persons({ pme }: { pme: Pme }) {
  const { data: me } = useMe();
  const invalidate = useInvalidatePme(pme.id);
  const canEdit = hasPermission(me, "pme.update") || hasPermission(me, "pme.update_identity");
  const [form, setForm] = useState({ full_name: "", role: "ASSOCIE", share_pct: "", phone: "", email: "", is_primary_contact: false });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const add = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/pmes/{pme_pk}/persons", {
          params: { path: { pme_pk: pme.id } },
          body: { ...form, role: form.role as Schemas["RoleEnum"], share_pct: form.share_pct || null },
        }),
      ),
    onSuccess: () => {
      setForm({ full_name: "", role: "ASSOCIE", share_pct: "", phone: "", email: "", is_primary_contact: false });
      setErrors({});
      invalidate();
    },
    onError: (err) => setErrors(err instanceof ApiError ? err.fieldErrors() : {}),
  });
  const remove = useMutation({
    mutationFn: (personId: string) => unwrap(api.DELETE("/api/v1/pmes/{pme_pk}/persons/{id}", { params: { path: { pme_pk: pme.id, id: personId } } })),
    onSuccess: invalidate,
  });

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card title="Dirigeants, associés et contacts" className="lg:col-span-2">
        {pme.persons.length === 0 ? (
          <p className="text-sm text-muted">Aucun dirigeant renseigné.</p>
        ) : (
          <ul className="divide-y divide-line">
            {pme.persons.map((person) => (
              <li key={person.id} className="flex items-center justify-between gap-3 py-3">
                <div>
                  <p className="font-medium">
                    {person.full_name} {person.is_primary_contact && <Badge tone="brand">Contact principal</Badge>}
                  </p>
                  <p className="text-sm text-muted">
                    {PERSON_ROLE_LABELS[person.role]}
                    {person.share_pct ? ` · ${Number(person.share_pct)} % du capital` : ""}
                    {person.phone ? ` · ${person.phone}` : ""}
                  </p>
                </div>
                {canEdit && (
                  <Button variant="ghost" onClick={() => remove.mutate(person.id)} loading={remove.isPending && remove.variables === person.id}>
                    Retirer
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      {canEdit && (
        <Card title="Ajouter une personne">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              add.mutate();
            }}
            className="flex flex-col gap-3"
          >
            {add.error && !(add.error instanceof ApiError && add.error.code === "validation_error") && <Alert>{errorMessage(add.error)}</Alert>}
            <TextInput label="Nom complet" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required error={errors.full_name} />
            <SelectInput
              label="Fonction"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
              options={Object.entries(PERSON_ROLE_LABELS).map(([value, label]) => ({ value, label }))}
            />
            <TextInput label="Part du capital (%)" type="number" min={0} max={100} step="0.01" value={form.share_pct} onChange={(e) => setForm({ ...form, share_pct: e.target.value })} error={errors.share_pct} />
            <TextInput label="Téléphone" type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            <TextInput label="E-mail" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} error={errors.email} />
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.is_primary_contact} onChange={(e) => setForm({ ...form, is_primary_contact: e.target.checked })} className="h-4 w-4 accent-brand-600" />
              Contact principal
            </label>
            <Button type="submit" loading={add.isPending}>
              Ajouter
            </Button>
          </form>
        </Card>
      )}
    </div>
  );
}

function FollowUp({ pme }: { pme: Pme }) {
  const { data: me } = useMe();
  const invalidate = useInvalidatePme(pme.id);
  const advisors = useQuery({ queryKey: ["advisors"], queryFn: () => unwrap(api.GET("/api/v1/users/advisors")), enabled: hasPermission(me, "pme.assign") });
  const [target, setTarget] = useState("");
  const [exitReason, setExitReason] = useState("");
  const [assignee, setAssignee] = useState({ user_id: "", role_in_pme: "CONSEILLER_PRINCIPAL" });
  const transition = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/pmes/{id}/transition", {
          params: { path: { id: pme.id } },
          body: { to: target as Schemas["LifecycleStatusEnum"], reason: "", exit_reason: (exitReason || "") as Schemas["ExitReasonEnum"] },
        }),
      ),
    onSuccess: () => {
      setTarget("");
      setExitReason("");
      invalidate();
    },
  });
  const assign = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/pmes/{id}/assignments", {
          params: { path: { id: pme.id } },
          body: { user_id: assignee.user_id, role_in_pme: assignee.role_in_pme as Schemas["RoleInPmeEnum"] },
        }),
      ),
    onSuccess: () => {
      setAssignee({ user_id: "", role_in_pme: "CONSEILLER_PRINCIPAL" });
      invalidate();
    },
  });
  const endAssignment = useMutation({
    mutationFn: (assignmentId: string) =>
      unwrap(api.POST("/api/v1/pmes/{id}/assignments/{assignment_id}/end", { params: { path: { id: pme.id, assignment_id: assignmentId } } })),
    onSuccess: invalidate,
  });
  const nextStatuses = LIFECYCLE_NEXT[pme.lifecycle_status];

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Cycle de vie">
        <p className="mb-4 text-sm text-muted">
          Statut actuel : <LifecycleBadge status={pme.lifecycle_status} />
          {pme.exit_reason && ` (${EXIT_REASON_LABELS[pme.exit_reason as Schemas["ExitReasonEnum"]] ?? pme.exit_reason})`}
        </p>
        {hasPermission(me, "pme.lifecycle") && nextStatuses.length > 0 ? (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              transition.mutate();
            }}
          >
            {transition.error && <Alert>{errorMessage(transition.error)}</Alert>}
            <SelectInput
              label="Nouveau statut"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              options={nextStatuses.map((status) => ({ value: status, label: LIFECYCLE_LABELS[status] }))}
              required
            />
            {target === "SORTIE" && (
              <SelectInput
                label="Motif de sortie"
                value={exitReason}
                onChange={(e) => setExitReason(e.target.value)}
                options={Object.entries(EXIT_REASON_LABELS).map(([value, label]) => ({ value, label }))}
                required
              />
            )}
            <Button type="submit" loading={transition.isPending} disabled={!target}>
              Changer le statut
            </Button>
          </form>
        ) : (
          <p className="text-sm text-muted">Aucun changement de statut possible depuis votre profil.</p>
        )}
        {pme.enrollments.length > 0 && (
          <div className="mt-6">
            <p className="mb-2 text-sm font-medium">Programmes</p>
            <ul className="space-y-1 text-sm text-muted">
              {pme.enrollments.map((enrollment) => (
                <li key={enrollment.id}>
                  {enrollment.cohort.programme} — {enrollment.cohort.name} (depuis le {formatDate(enrollment.enrolled_at)}
                  {enrollment.exited_at ? `, sortie le ${formatDate(enrollment.exited_at)}` : ""})
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>
      <Card title="Équipe de suivi">
        {pme.assignments.length === 0 ? (
          <p className="text-sm text-muted">Aucun conseiller ni expert assigné.</p>
        ) : (
          <ul className="divide-y divide-line">
            {pme.assignments.map((assignment) => (
              <li key={assignment.id} className="flex items-center justify-between gap-3 py-3">
                <div>
                  <p className="font-medium">{assignment.user.full_name}</p>
                  <p className="text-sm text-muted">
                    {ROLE_IN_PME_LABELS[assignment.role_in_pme]} · depuis le {formatDate(assignment.start_date)}
                  </p>
                </div>
                {hasPermission(me, "pme.assign") && (
                  <Button variant="ghost" onClick={() => endAssignment.mutate(assignment.id)}>
                    Mettre fin
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
        {hasPermission(me, "pme.assign") && (
          <form
            className="mt-4 grid gap-3 border-t border-line pt-4 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              assign.mutate();
            }}
          >
            {assign.error && (
              <div className="sm:col-span-2">
                <Alert>{errorMessage(assign.error)}</Alert>
              </div>
            )}
            <SelectInput
              label="Personne"
              value={assignee.user_id}
              onChange={(e) => setAssignee({ ...assignee, user_id: e.target.value })}
              options={(advisors.data ?? []).map((user) => ({ value: user.id, label: user.full_name }))}
              required
            />
            <SelectInput
              label="Rôle"
              value={assignee.role_in_pme}
              onChange={(e) => setAssignee({ ...assignee, role_in_pme: e.target.value })}
              options={Object.entries(ROLE_IN_PME_LABELS).map(([value, label]) => ({ value, label }))}
              placeholder="—"
            />
            <div className="sm:col-span-2">
              <Button type="submit" loading={assign.isPending}>
                Assigner
              </Button>
            </div>
          </form>
        )}
      </Card>
    </div>
  );
}

function Timeline({ pmeId }: { pmeId: string }) {
  const timeline = useQuery({
    queryKey: ["timeline", pmeId],
    queryFn: () => unwrap(api.GET("/api/v1/pmes/{id}/timeline", { params: { path: { id: pmeId } } })),
  });
  if (timeline.isLoading) return <LoadingBlock />;
  if (timeline.error) return <Alert>{errorMessage(timeline.error)}</Alert>;
  const entries = timeline.data ?? [];
  if (entries.length === 0) return <EmptyState title="Aucun événement">L'historique de la PME apparaîtra ici.</EmptyState>;
  return (
    <Card title="Historique (journal d'audit)">
      <ol className="relative space-y-5 border-l border-line pl-6">
        {entries.map((entry) => (
          <li key={entry.id}>
            <span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full border-2 border-white bg-brand-500" aria-hidden="true" />
            <p className="text-sm font-medium">{entry.label}</p>
            <p className="text-xs text-muted">
              {formatDateTime(entry.at)} · {entry.actor ?? "—"}
            </p>
            {isNonEmptyObject(entry.after) && (
              <ChangeList before={entry.before as Record<string, unknown> | null} after={entry.after as Record<string, unknown>} />
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
}

function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "∅";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function ChangeList({ before, after }: { before: Record<string, unknown> | null; after: Record<string, unknown> }) {
  return (
    <ul className="mt-1.5 space-y-0.5 text-xs text-muted">
      {Object.entries(after).map(([key, value]) => (
        <li key={key}>
          <span className="font-mono text-gray-500">{key}</span> :{" "}
          {before && key in before ? (
            <>
              <span className="line-through">{display(before[key])}</span> → <span className="text-ink">{display(value)}</span>
            </>
          ) : (
            <span className="text-ink">{display(value)}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

function isNonEmptyObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && Object.keys(value).length > 0;
}
