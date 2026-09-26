"use client";

/**
 * Administration de la conformité (Document 8) : registre réglementaire sourcé (RM-08), obligations (création et
 * règles de profil sans code), types de documents (V1), règles d'alerte (Document 7, § 8) et planificateur quotidien.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { DocumentTypesAdmin } from "@/components/compliance/DocumentTypesAdmin";
import { NATURES, ObligationForm } from "@/components/compliance/ObligationForm";
import { Alert, Badge, Button, Card, cx, LoadingBlock, PageHeader, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { SEVERITY } from "@/lib/documents";
import { formatDate } from "@/lib/format";

const RULE_STATUS: Record<string, { label: string; tone: "brand" | "warning" | "danger" | "muted" | "info" }> = {
  VERIFIE: { label: "Vérifiée", tone: "brand" },
  PRE_VERIFIE: { label: "Pré-vérifiée", tone: "info" },
  A_VERIFIER: { label: "À vérifier", tone: "warning" },
  OBSOLETE: { label: "Obsolète", tone: "muted" },
  HORS_PERIMETRE: { label: "Hors périmètre", tone: "muted" },
};
const TABS = [
  { key: "registre", label: "Registre réglementaire" },
  { key: "obligations", label: "Obligations" },
  { key: "documents", label: "Types de documents" },
  { key: "alertes", label: "Règles d'alerte" },
] as const;

export default function CompliancePage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("registre");
  const run = useMutation({ mutationFn: () => unwrap(api.POST("/api/v1/compliance/run")) });
  return (
    <>
      <PageHeader
        title="Conformité et obligations"
        subtitle="Aucune règle réglementaire n'est codée en dur : chaque obligation légale s'appuie sur une source vérifiée et datée."
        actions={
          <Button variant="secondary" loading={run.isPending} onClick={() => run.mutate()}>
            Exécuter le planificateur maintenant
          </Button>
        }
      />
      {run.data && (
        <div className="mb-4">
          <Alert tone="success">
            {run.data.pmes} PME traitées · {run.data.deadlines_created} échéance(s) créée(s) · {run.data.reminders} relance(s) envoyée(s).
          </Alert>
        </div>
      )}
      <div className="mb-6 flex gap-1 border-b border-line" role="tablist">
        {TABS.map((item) => (
          <button
            key={item.key}
            role="tab"
            aria-selected={tab === item.key}
            onClick={() => setTab(item.key)}
            className={cx("border-b-2 px-3 py-2.5 text-sm", tab === item.key ? "border-brand-600 font-medium text-brand-800" : "border-transparent text-muted")}
          >
            {item.label}
          </button>
        ))}
      </div>
      {tab === "registre" && <Registry />}
      {tab === "obligations" && <Obligations />}
      {tab === "documents" && <DocumentTypesAdmin />}
      {tab === "alertes" && <AlertRules />}
    </>
  );
}

function Registry() {
  const rules = useQuery({ queryKey: ["regulatory-rules"], queryFn: () => unwrap(api.GET("/api/v1/regulatory-rules")) });
  const [open, setOpen] = useState<string | null>(null);
  if (rules.isLoading) return <LoadingBlock />;
  if (rules.error) return <Alert>{errorMessage(rules.error)}</Alert>;
  return (
    <div className="space-y-3">
      <Alert tone="info">
        Les contenus ci-dessous proviennent de recherches documentaires. Ils doivent être confirmés par un juriste ou un expert-comptable
        ivoirien avant l'activation des obligations qui en dépendent (décision D-06).
      </Alert>
      {rules.data!.map((rule) => (
        <Card key={rule.id}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-medium">
                <span className="font-mono text-xs text-muted">{rule.code}</span> {rule.title}
              </p>
              <p className="mt-1 text-sm text-muted">{rule.content}</p>
              <ul className="mt-2 space-y-0.5 text-xs">
                {rule.sources.map((source) => (
                  <li key={source.url}>
                    <a href={source.url} target="_blank" rel="noopener noreferrer" className="text-brand-700 hover:underline">
                      {source.title}
                    </a>
                  </li>
                ))}
              </ul>
              {rule.status === "VERIFIE" && (
                <p className="mt-2 text-xs text-muted">
                  Vérifiée le {formatDate(rule.verified_at)} par {rule.verified_by_name} · {rule.source_reference}
                  {rule.review_due_at && ` · revue avant le ${formatDate(rule.review_due_at)}`}
                </p>
              )}
              {rule.obligations.length > 0 && <p className="mt-1 text-xs text-muted">Obligations liées : {rule.obligations.join(", ")}</p>}
            </div>
            <div className="flex flex-col items-end gap-2">
              <Badge tone={RULE_STATUS[rule.status].tone}>{RULE_STATUS[rule.status].label}</Badge>
              <button className="text-xs text-brand-700 hover:underline" onClick={() => setOpen(open === rule.id ? null : rule.id)}>
                {rule.status === "VERIFIE" ? "Modifier le statut" : "Marquer comme vérifiée"}
              </button>
            </div>
          </div>
          {open === rule.id && <RuleForm rule={rule} onDone={() => setOpen(null)} />}
        </Card>
      ))}
    </div>
  );
}

function RuleForm({ rule, onDone }: { rule: Schemas["RegulatoryRule"]; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ source_reference: rule.source_reference, verified_at: new Date().toISOString().slice(0, 10), note: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["regulatory-rules"] });
    queryClient.invalidateQueries({ queryKey: ["obligation-templates"] });
    onDone();
  };
  const verify = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/regulatory-rules/{rule_id}/verify", { params: { path: { rule_id: rule.id } }, body: form })),
    onSuccess: refresh,
    onError: (err) => setErrors(err instanceof ApiError ? err.fieldErrors() : {}),
  });
  const reset = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/api/v1/regulatory-rules/{rule_id}/status", { params: { path: { rule_id: rule.id } }, body: { status: "A_VERIFIER", note: form.note } })),
    onSuccess: refresh,
  });
  return (
    <form
      className="mt-4 grid gap-3 border-t border-line pt-4 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        verify.mutate();
      }}
    >
      <div className="sm:col-span-2">
        <TextInput
          label="Texte et article vérifiés (source officielle)"
          value={form.source_reference}
          onChange={(e) => setForm({ ...form, source_reference: e.target.value })}
          error={errors.source_reference}
          required
        />
      </div>
      <TextInput label="Date de vérification" type="date" value={form.verified_at} onChange={(e) => setForm({ ...form, verified_at: e.target.value })} error={errors.verified_at} />
      <TextInput label="Note (vérificateur, réserves)" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
      <div className="flex flex-wrap gap-2 sm:col-span-2">
        <Button type="submit" loading={verify.isPending}>
          Enregistrer la vérification
        </Button>
        {rule.status === "VERIFIE" && (
          <Button type="button" variant="ghost" onClick={() => reset.mutate()}>
            Repasser « à vérifier » (désactive les obligations liées)
          </Button>
        )}
      </div>
      {verify.error && !(verify.error instanceof ApiError && verify.error.code === "validation_error") && <Alert>{errorMessage(verify.error)}</Alert>}
    </form>
  );
}

function Obligations() {
  const queryClient = useQueryClient();
  const templates = useQuery({ queryKey: ["obligation-templates"], queryFn: () => unwrap(api.GET("/api/v1/obligation-templates")) });
  const [editing, setEditing] = useState<Schemas["ObligationTemplate"] | "new" | null>(null);
  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      unwrap(api.POST("/api/v1/obligation-templates/{template_id}/activation", { params: { path: { template_id: id } }, body: { active } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["obligation-templates"] }),
  });
  if (templates.isLoading) return <LoadingBlock />;
  if (templates.error) return <Alert>{errorMessage(templates.error)}</Alert>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          Une obligation réglementaire ne peut être active que si sa règle du registre est vérifiée (RM-08). Les modifications valent pour les
          prochaines échéances.
        </p>
        {editing === null && <Button onClick={() => setEditing("new")}>Nouvelle obligation</Button>}
      </div>
      {editing !== null && (
        <Card title={editing === "new" ? "Nouvelle obligation" : `Modifier « ${editing.name} »`}>
          <ObligationForm key={editing === "new" ? "new" : editing.id} initial={editing === "new" ? null : editing} onDone={() => setEditing(null)} />
        </Card>
      )}
      <Card>
        {toggle.error && (
          <div className="mb-3">
            <Alert>{errorMessage(toggle.error)}</Alert>
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-line text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="py-2 pr-4">Obligation</th>
                <th className="py-2 pr-4">Nature</th>
                <th className="py-2 pr-4">S'applique à</th>
                <th className="py-2 pr-4">Périodicité</th>
                <th className="py-2 pr-4">Règle</th>
                <th className="py-2 pr-4 text-right">PME</th>
                <th className="py-2 pr-4">Active</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line align-top">
              {templates.data!.map((t) => (
                <tr key={t.id}>
                  <td className="py-2.5 pr-4">
                    <p className="font-medium">{t.name}</p>
                    <p className="text-xs text-muted">
                      {t.document_type_name} · échéance {t.due_days_after_period_end} j après la période
                      {t.is_critical && " · critique"}
                    </p>
                    {t.description && <p className="mt-0.5 text-xs text-muted">{t.description}</p>}
                  </td>
                  <td className="py-2.5 pr-4 text-muted">{NATURES[t.nature]}</td>
                  <td className="max-w-xs py-2.5 pr-4 text-xs text-muted">{t.applicability_text}</td>
                  <td className="max-w-xs py-2.5 pr-4 text-xs text-muted">{t.frequency_text}</td>
                  <td className="py-2.5 pr-4">
                    {t.regulatory_rule ? <Badge tone={RULE_STATUS[t.regulatory_status ?? "A_VERIFIER"].tone}>{t.regulatory_rule}</Badge> : <span className="text-muted">—</span>}
                  </td>
                  <td className="py-2.5 pr-4 text-right tabular-nums">{t.pmes}</td>
                  <td className="py-2.5 pr-4">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-brand-600"
                      aria-label={`Activer ${t.name}`}
                      checked={t.is_active}
                      disabled={toggle.isPending}
                      onChange={() => toggle.mutate({ id: t.id, active: !t.is_active })}
                    />
                  </td>
                  <td className="py-2.5 text-right">
                    <button className="text-xs text-brand-700 hover:underline" onClick={() => setEditing(t)} aria-label={`Modifier ${t.name}`}>
                      Modifier
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function AlertRules() {
  const queryClient = useQueryClient();
  const rules = useQuery({ queryKey: ["alert-rules"], queryFn: () => unwrap(api.GET("/api/v1/alert-rules")) });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Schemas["PatchedAlertRuleRequest"] }) =>
      unwrap(api.PATCH("/api/v1/alert-rules/{rule_id}", { params: { path: { rule_id: id } }, body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alert-rules"] }),
  });
  if (rules.isLoading) return <LoadingBlock />;
  if (rules.error) return <Alert>{errorMessage(rules.error)}</Alert>;
  return (
    <Card>
      {update.error && <Alert>{errorMessage(update.error)}</Alert>}
      <ul className="divide-y divide-line">
        {rules.data!.map((rule) => (
          <li key={rule.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div>
              <p className="font-medium">
                <span className="font-mono text-xs text-muted">{rule.code}</span> {rule.name}
              </p>
              <p className="text-xs text-muted">
                Seuils : {Object.keys(rule.params ?? {}).length ? JSON.stringify(rule.params) : "—"} · destinataires : {rule.recipients.join(", ")}
                {rule.available_in_phase && ` · disponible en phase ${rule.available_in_phase}`}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <select
                aria-label={`Sévérité de ${rule.name}`}
                className="rounded-md border border-line px-2 py-1 text-sm"
                value={rule.severity}
                onChange={(e) => update.mutate({ id: rule.id, body: { severity: e.target.value as Schemas["SeverityEnum"] } })}
              >
                {Object.entries(SEVERITY).map(([value, { label }]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-brand-600"
                  checked={rule.is_active}
                  disabled={Boolean(rule.available_in_phase)}
                  onChange={() => update.mutate({ id: rule.id, body: { is_active: !rule.is_active } })}
                />
                Active
              </label>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
