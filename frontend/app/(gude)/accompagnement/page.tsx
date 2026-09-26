"use client";

/**
 * Accompagnement (Document 7, § 3 et § 7) : catalogue d'offres, bibliothèque de livrables, règles de
 * recommandation versionnées. Une règle active n'est jamais modifiée : on crée une version, on la teste sur le
 * portefeuille, puis on l'active.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Badge, Button, Card, cx, LoadingBlock, PageHeader, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { DIMENSIONS, formatCost, RULE_STATUS } from "@/lib/plans";

type Tab = "regles" | "offres" | "livrables";
type Rule = Schemas["Rule"];

export default function SupportPage() {
  const [tab, setTab] = useState<Tab>("regles");
  return (
    <>
      <PageHeader
        title="Accompagnement"
        subtitle="Règles de recommandation, offres d'accompagnement et modèles de livrables de votre organisation."
      />
      <div className="mb-6 flex gap-1 border-b border-line" role="tablist">
        {(
          [
            ["regles", "Règles"],
            ["offres", "Offres"],
            ["livrables", "Modèles de livrables"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cx(
              "border-b-2 px-3 py-2.5 text-sm",
              tab === key ? "border-brand-600 font-medium text-brand-800" : "border-transparent text-muted hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "regles" && <Rules />}
      {tab === "offres" && <Offers />}
      {tab === "livrables" && <Templates />}
    </>
  );
}

function Offers() {
  const offers = useQuery({ queryKey: ["support-offers"], queryFn: () => unwrap(api.GET("/api/v1/support-offers")) });
  if (offers.isLoading) return <LoadingBlock />;
  if (offers.error) return <Alert>{errorMessage(offers.error)}</Alert>;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {offers.data!.map((offer) => (
        <Card key={offer.id} title={offer.title} action={<Badge tone="muted">{DIMENSIONS[offer.dimension_code] ?? offer.dimension_code}</Badge>}>
          <p className="text-sm text-ink">{offer.objective}</p>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div>
              <dt className="text-muted">Durée type</dt>
              <dd>{offer.typical_duration_days} jours · effort {offer.effort}/5</dd>
            </div>
            <div>
              <dt className="text-muted">Réussite</dt>
              <dd>{offer.success_indicator}</dd>
            </div>
            <div>
              <dt className="text-muted">Coût estimatif</dt>
              <dd>{formatCost(offer.estimated_cost_min, offer.estimated_cost_max)}</dd>
            </div>
            <div>
              <dt className="text-muted">Prérequis</dt>
              <dd>{(offer.depends_on as string[]).join(", ") || "—"}</dd>
            </div>
          </dl>
          <p className="mt-2 text-xs text-muted">
            <span className="font-mono">{offer.code}</span> · étapes : {(offer.sub_actions as string[]).join(" → ")}
          </p>
        </Card>
      ))}
    </div>
  );
}

function Templates() {
  const templates = useQuery({ queryKey: ["deliverable-templates"], queryFn: () => unwrap(api.GET("/api/v1/deliverable-templates")) });
  if (templates.isLoading) return <LoadingBlock />;
  if (templates.error) return <Alert>{errorMessage(templates.error)}</Alert>;
  return (
    <Card>
      <p className="mb-3 text-sm text-muted">
        Chaque modèle donne des instructions en langage simple et les points que le conseiller vérifie. Les fichiers modèles (docx, xlsx) seront
        fournis par GUDE-PME.
      </p>
      <ul className="divide-y divide-line">
        {templates.data!.map((template) => (
          <li key={template.id} className="py-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-medium">{template.title}</p>
              <span className="text-xs text-muted">
                {template.category} · {template.format} · déposé comme <span className="font-mono">{template.document_type_code}</span>
              </span>
            </div>
            <p className="mt-1 text-muted">{template.instructions}</p>
            <p className="mt-1 text-xs text-muted">Vérifié : {(template.verification_criteria as string[]).join(" · ")}</p>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Rules() {
  const queryClient = useQueryClient();
  const rules = useQuery({ queryKey: ["recommendation-rules"], queryFn: () => unwrap(api.GET("/api/v1/recommendation-rules")) });
  const [editing, setEditing] = useState<Rule | "new" | null>(null);
  if (rules.isLoading) return <LoadingBlock />;
  if (rules.error) return <Alert>{errorMessage(rules.error)}</Alert>;
  const byCode = new Map<string, Rule[]>();
  for (const rule of rules.data!) byCode.set(rule.code, [...(byCode.get(rule.code) ?? []), rule]);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["recommendation-rules"] });

  return (
    <div className="space-y-4">
      <div className="flex justify-between gap-3">
        <p className="text-sm text-muted">
          « SI … ALORS proposer … » en JSON Logic. Variables : <span className="font-mono">criterion.RHO-01.level</span>,{" "}
          <span className="font-mono">dimension.D04.score</span>, <span className="font-mono">risk_index</span>,{" "}
          <span className="font-mono">maturity_level</span>, <span className="font-mono">compliance_rate</span>…
        </p>
        <Button variant="secondary" onClick={() => setEditing("new")}>
          Nouvelle règle
        </Button>
      </div>
      {editing && (
        <RuleForm
          base={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refresh();
          }}
        />
      )}
      {[...byCode.entries()].map(([code, versions]) => (
        <Card key={code} title={`${code} · ${versions[0].name}`} action={<span className="text-xs text-muted">→ {versions[0].offer_title}</span>}>
          <ul className="space-y-3">
            {versions.map((rule) => (
              <RuleVersion key={rule.id} rule={rule} onChanged={refresh} onNewVersion={() => setEditing(rule)} />
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}

function RuleVersion({ rule, onChanged, onNewVersion }: { rule: Rule; onChanged: () => void; onNewVersion: () => void }) {
  const test = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/recommendation-rules/{rule_id}/test", { params: { path: { rule_id: rule.id } } })),
    onSuccess: onChanged,
  });
  const activate = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/recommendation-rules/{rule_id}/activate", { params: { path: { rule_id: rule.id } } })),
    onSuccess: onChanged,
  });
  const deactivate = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/recommendation-rules/{rule_id}/deactivate", { params: { path: { rule_id: rule.id } } })),
    onSuccess: onChanged,
  });
  const status = RULE_STATUS[rule.status];
  const result = (test.data ?? rule.test_result) as { evaluated: number; matched: { pme_name: string; rationale: string }[] } | null;
  const error = test.error ?? activate.error ?? deactivate.error;

  return (
    <li className="rounded-lg border border-line p-3 text-sm" data-testid="rule-version">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p>
          <span className="font-medium">Version {rule.version}</span> <Badge tone={status?.tone}>{status?.label}</Badge>
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" className="px-3 py-1.5" loading={test.isPending} onClick={() => test.mutate()}>
            Tester
          </Button>
          {rule.status !== "ACTIVE" && (
            <Button className="px-3 py-1.5" disabled={!rule.tested_at && !test.data} loading={activate.isPending} onClick={() => activate.mutate()}>
              Activer
            </Button>
          )}
          {rule.status === "ACTIVE" && (
            <Button variant="ghost" className="px-3 py-1.5" loading={deactivate.isPending} onClick={() => deactivate.mutate()}>
              Désactiver
            </Button>
          )}
          <Button variant="ghost" className="px-3 py-1.5" onClick={onNewVersion}>
            Nouvelle version
          </Button>
        </div>
      </div>
      <pre className="mt-2 overflow-x-auto rounded bg-gray-50 p-2 text-xs">{JSON.stringify(rule.condition)}</pre>
      <p className="mt-1 text-xs text-muted">{rule.rationale_template}</p>
      {result && (
        <div className="mt-2 text-xs">
          <p className="font-medium">
            Test{rule.tested_at ? ` du ${formatDateTime(rule.tested_at)}` : ""} : {result.matched.length} PME concernée(s) sur {result.evaluated}
          </p>
          <ul className="list-inside list-disc text-muted">
            {result.matched.slice(0, 10).map((m) => (
              <li key={m.pme_name}>
                {m.pme_name} — {m.rationale}
              </li>
            ))}
          </ul>
        </div>
      )}
      {error && <Alert>{errorMessage(error)}</Alert>}
    </li>
  );
}

function RuleForm({ base, onClose, onSaved }: { base: Rule | null; onClose: () => void; onSaved: () => void }) {
  const offers = useQuery({ queryKey: ["support-offers"], queryFn: () => unwrap(api.GET("/api/v1/support-offers")) });
  const [form, setForm] = useState({
    code: base?.code ?? "",
    name: base?.name ?? "",
    offer_code: base?.offer_code ?? "",
    condition: base ? JSON.stringify(base.condition, null, 2) : '{"<=": [{"var": "criterion.RHO-01.level"}, 1]}',
    problem_template: base?.problem_template ?? "",
    rationale_template: base?.rationale_template ?? "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: () => {
      let condition: unknown;
      try {
        condition = JSON.parse(form.condition);
      } catch {
        throw new ApiError(400, { code: "validation_error", detail: "Condition JSON invalide.", errors: { condition: ["JSON invalide."] } });
      }
      return unwrap(api.POST("/api/v1/recommendation-rules", { body: { ...form, condition } }));
    },
    onSuccess: onSaved,
    onError: (error) => setErrors(error instanceof ApiError ? error.fieldErrors() : {}),
  });
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm({ ...form, [key]: e.target.value });

  return (
    <Card title={base ? `Nouvelle version de ${base.code}` : "Nouvelle règle"}>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <TextInput label="Code" required value={form.code} onChange={set("code")} disabled={Boolean(base)} error={errors.code} />
          <TextInput label="Nom" required value={form.name} onChange={set("name")} error={errors.name} />
        </div>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Offre proposée</span>
          <select required value={form.offer_code} onChange={set("offer_code")} className="w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm">
            <option value="">— Choisir —</option>
            {(offers.data ?? []).map((o) => (
              <option key={o.code} value={o.code}>
                {o.title}
              </option>
            ))}
          </select>
          {errors.offer_code && <span className="text-xs text-red-700">{errors.offer_code}</span>}
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Condition (JSON Logic)</span>
          <textarea rows={5} value={form.condition} onChange={set("condition")} className="w-full rounded-lg border border-line px-3 py-2 font-mono text-xs" />
          {errors.condition && <span className="text-xs text-red-700">{errors.condition}</span>}
        </label>
        <TextInput label="Problème (gabarit)" required value={form.problem_template} onChange={set("problem_template")} error={errors.problem_template} />
        <TextInput
          label="Justification (gabarit, ex. {{criterion.RHO-01.level}})"
          required
          value={form.rationale_template}
          onChange={set("rationale_template")}
          error={errors.rationale_template}
        />
        {save.error && !(save.error instanceof ApiError && save.error.code === "validation_error") && <Alert>{errorMessage(save.error)}</Alert>}
        <div className="flex gap-2">
          <Button type="submit" loading={save.isPending}>
            Enregistrer le brouillon
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Annuler
          </Button>
        </div>
        <p className="text-xs text-muted">La nouvelle version est créée en brouillon : testez-la, puis activez-la (l'ancienne version est désactivée).</p>
      </form>
    </Card>
  );
}
