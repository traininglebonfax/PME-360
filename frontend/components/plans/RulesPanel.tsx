"use client";

/**
 * Règles de recommandation (Document 7, § 3.3) : lecture en français (« SI … ALORS proposer … »), test sur le
 * portefeuille avant activation, et constructeur visuel. La formule technique (JSON Logic) reste consultable et
 * modifiable en mode avancé.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { Alert, Badge, Button, Card, cx, LoadingBlock, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { RULE_STATUS } from "@/lib/plans";
import {
  buildCondition,
  type Clause,
  type Combinator,
  COMBINATOR_LABELS,
  defaultClause,
  describeCondition,
  type Operator,
  OPERATOR_LABELS,
  parseCondition,
  readableTemplate,
  type RuleVariable,
  valueRange,
} from "@/lib/ruleBuilder";

type Rule = Schemas["Rule"];

function useVariables() {
  return useQuery({
    queryKey: ["rule-variables"],
    queryFn: async () => (await unwrap(api.GET("/api/v1/recommendation-rules/variables"))) as RuleVariable[],
    staleTime: 10 * 60_000,
  });
}

export function RulesPanel() {
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
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-3xl text-sm text-muted">
          Chaque règle se lit « SI la situation de la PME remplit la condition ALORS proposer l'accompagnement ». Une règle active n'est jamais
          modifiée : créez une nouvelle version, testez-la sur le portefeuille, puis activez-la.
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
      <div className="mt-2 rounded-md bg-gray-50 p-3" data-testid="rule-sentence">
        <p>
          <span className="font-semibold text-brand-800">SI</span> {rule.condition_text}
        </p>
        <p className="mt-1">
          <span className="font-semibold text-brand-800">ALORS</span> proposer « {rule.offer_title} »
        </p>
      </div>
      <p className="mt-2 text-xs text-muted">
        <span className="font-medium text-ink">Problème affiché :</span> {rule.problem_readable}
      </p>
      <p className="mt-1 text-xs text-muted">
        <span className="font-medium text-ink">Justification :</span> {rule.rationale_readable}{" "}
        <span className="italic">(les valeurs entre crochets sont remplacées par celles de chaque PME)</span>
      </p>
      <details className="mt-2 text-xs">
        <summary className="cursor-pointer text-muted hover:text-ink">Voir la formule technique</summary>
        <pre className="mt-1 overflow-x-auto rounded bg-gray-50 p-2">{JSON.stringify(rule.condition, null, 2)}</pre>
      </details>
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

// --- Constructeur visuel ----------------------------------------------------------------------------------------

function RuleForm({ base, onClose, onSaved }: { base: Rule | null; onClose: () => void; onSaved: () => void }) {
  const variables = useVariables();
  const offers = useQuery({ queryKey: ["support-offers"], queryFn: () => unwrap(api.GET("/api/v1/support-offers")) });
  const parsed = base ? parseCondition(base.condition) : { combinator: "or" as Combinator, clauses: [] as Clause[] };
  const [combinator, setCombinator] = useState<Combinator>(parsed?.combinator ?? "or");
  const [clauses, setClauses] = useState<Clause[]>(parsed?.clauses ?? []);
  const [advanced, setAdvanced] = useState(parsed === null);
  const [json, setJson] = useState(base ? JSON.stringify(base.condition, null, 2) : "");
  const [form, setForm] = useState({
    code: base?.code ?? "",
    name: base?.name ?? "",
    offer_code: base?.offer_code ?? "",
    problem_template: base?.problem_template ?? "",
    rationale_template: base?.rationale_template ?? "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  const byKey = useMemo(() => new Map((variables.data ?? []).map((v) => [v.key, v])), [variables.data]);
  const labels = useMemo(() => Object.fromEntries((variables.data ?? []).map((v) => [v.key, v.label])), [variables.data]);
  const groups = useMemo(() => {
    const map = new Map<string, RuleVariable[]>();
    for (const v of variables.data ?? []) map.set(v.group, [...(map.get(v.group) ?? []), v]);
    return [...map.entries()];
  }, [variables.data]);
  const usedKeys = [...new Set(clauses.map((c) => c.key))];
  const offerTitle = offers.data?.find((o) => o.code === form.offer_code)?.title;

  const save = useMutation({
    mutationFn: () => {
      let condition: unknown;
      if (advanced) {
        try {
          condition = JSON.parse(json);
        } catch {
          throw new ApiError(400, { code: "validation_error", detail: "Formule technique invalide.", errors: { condition: ["JSON invalide."] } });
        }
      } else {
        if (clauses.length === 0) {
          throw new ApiError(400, { code: "validation_error", detail: "Ajoutez au moins une condition.", errors: { condition: ["Ajoutez au moins une condition."] } });
        }
        condition = buildCondition(combinator, clauses);
      }
      return unwrap(api.POST("/api/v1/recommendation-rules", { body: { ...form, condition } }));
    },
    onSuccess: onSaved,
    onError: (error) => setErrors(error instanceof ApiError ? error.fieldErrors() : {}),
  });

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [key]: e.target.value });
  const update = (index: number, patch: Partial<Clause>) => setClauses(clauses.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  const insert = (field: "problem_template" | "rationale_template", key: string) =>
    setForm({ ...form, [field]: `${form[field]}${form[field] && !form[field].endsWith(" ") ? " " : ""}{{${key}}}` });

  if (variables.isLoading) return <LoadingBlock />;

  return (
    <Card title={base ? `Nouvelle version de ${base.code}` : "Nouvelle règle"}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <TextInput label="Code" hint="Ex. : R-FIN-004" required value={form.code} onChange={set("code")} disabled={Boolean(base)} error={errors.code} />
          <TextInput label="Nom de la règle" required value={form.name} onChange={set("name")} error={errors.name} />
        </div>

        <fieldset className="rounded-lg border border-line p-3">
          <legend className="px-1 text-sm font-semibold text-brand-800">SI</legend>
          {advanced ? (
            <label className="block text-sm">
              <span className="mb-1 block text-muted">Formule technique (JSON Logic, réservé aux utilisateurs avancés)</span>
              <textarea rows={6} value={json} onChange={(e) => setJson(e.target.value)} className="w-full rounded-lg border border-line px-3 py-2 font-mono text-xs" />
            </label>
          ) : (
            <div className="space-y-2">
              {clauses.length > 1 && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-muted">Relier les conditions par</span>
                  {(["and", "or"] as Combinator[]).map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setCombinator(c)}
                      aria-pressed={combinator === c}
                      className={cx("rounded-md border px-2.5 py-1 text-xs font-semibold", combinator === c ? "border-brand-600 bg-brand-50 text-brand-800" : "border-line text-muted")}
                    >
                      {COMBINATOR_LABELS[c]}
                    </button>
                  ))}
                  <span className="text-xs text-muted">{combinator === "and" ? "(toutes doivent être vraies)" : "(une seule suffit)"}</span>
                </div>
              )}
              {clauses.map((clause, index) => {
                const variable = byKey.get(clause.key);
                const range = valueRange(variable?.type ?? "score");
                return (
                  <div key={index} className="grid items-end gap-2 sm:grid-cols-[auto_1fr_10rem_8rem_auto]" data-testid="rule-clause">
                    <span className="pb-2.5 text-xs font-semibold text-muted">{index === 0 ? "" : COMBINATOR_LABELS[combinator]}</span>
                    <label className="text-sm">
                      <span className="mb-1 block text-xs text-muted">Donnée de la PME</span>
                      <select
                        aria-label="Donnée de la PME"
                        value={clause.key}
                        onChange={(e) => {
                          const next = byKey.get(e.target.value);
                          if (next) update(index, defaultClause(next));
                        }}
                        className="w-full rounded-lg border border-line bg-white px-2 py-2.5 text-sm"
                      >
                        {groups.map(([group, items]) => (
                          <optgroup key={group} label={group}>
                            {items.map((v) => (
                              <option key={v.key} value={v.key}>
                                {v.label}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </select>
                    </label>
                    {variable?.type === "boolean" ? (
                      <label className="text-sm sm:col-span-2">
                        <span className="mb-1 block text-xs text-muted">Valeur</span>
                        <select
                          aria-label="Valeur"
                          value={String(clause.value)}
                          onChange={(e) => update(index, { op: "==", value: e.target.value === "true" })}
                          className="w-full rounded-lg border border-line bg-white px-2 py-2.5 text-sm"
                        >
                          <option value="true">oui</option>
                          <option value="false">non</option>
                        </select>
                      </label>
                    ) : (
                      <>
                        <label className="text-sm">
                          <span className="mb-1 block text-xs text-muted">Comparaison</span>
                          <select
                            aria-label="Comparaison"
                            value={clause.op}
                            onChange={(e) => update(index, { op: e.target.value as Operator })}
                            className="w-full rounded-lg border border-line bg-white px-2 py-2.5 text-sm"
                          >
                            {(Object.keys(OPERATOR_LABELS) as Operator[]).map((op) => (
                              <option key={op} value={op}>
                                {OPERATOR_LABELS[op]}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="text-sm">
                          <span className="mb-1 block text-xs text-muted">Valeur</span>
                          <input
                            aria-label="Valeur"
                            type="number"
                            min={range.min}
                            max={range.max}
                            step={range.step}
                            value={Number(clause.value)}
                            onChange={(e) => update(index, { value: Number(e.target.value) })}
                            className="w-full rounded-lg border border-line px-2 py-2 text-sm"
                          />
                        </label>
                      </>
                    )}
                    <button type="button" onClick={() => setClauses(clauses.filter((_, i) => i !== index))} className="pb-2.5 text-xs text-red-700 hover:underline">
                      Retirer
                    </button>
                  </div>
                );
              })}
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  const first = (variables.data ?? []).find((v) => v.type === "level") ?? variables.data?.[0];
                  if (first) setClauses([...clauses, defaultClause(first)]);
                }}
              >
                + Ajouter une condition
              </Button>
            </div>
          )}
          {errors.condition && <p className="mt-1 text-xs text-red-700">{errors.condition}</p>}
          <button
            type="button"
            className="mt-2 text-xs text-muted hover:text-ink"
            onClick={() => {
              if (!advanced) setJson(JSON.stringify(clauses.length ? buildCondition(combinator, clauses) : {}, null, 2));
              else {
                const back = (() => {
                  try {
                    return parseCondition(JSON.parse(json));
                  } catch {
                    return null;
                  }
                })();
                if (!back) {
                  setErrors({ condition: "Cette formule est trop complexe pour le constructeur : gardez l'édition technique." });
                  return;
                }
                setCombinator(back.combinator);
                setClauses(back.clauses);
              }
              setErrors({});
              setAdvanced(!advanced);
            }}
          >
            {advanced ? "Revenir au constructeur" : "Éditer la formule technique (avancé)"}
          </button>
        </fieldset>

        <fieldset className="rounded-lg border border-line p-3">
          <legend className="px-1 text-sm font-semibold text-brand-800">ALORS proposer</legend>
          <select
            aria-label="Offre proposée"
            required
            value={form.offer_code}
            onChange={set("offer_code")}
            className="w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm"
          >
            <option value="">— Choisir l'accompagnement —</option>
            {(offers.data ?? []).map((o) => (
              <option key={o.code} value={o.code}>
                {o.title}
              </option>
            ))}
          </select>
          {errors.offer_code && <p className="mt-1 text-xs text-red-700">{errors.offer_code}</p>}
        </fieldset>

        <fieldset className="space-y-2 rounded-lg border border-line p-3">
          <legend className="px-1 text-sm font-semibold text-brand-800">Texte affiché au conseiller</legend>
          <TemplateField label="Problème constaté" value={form.problem_template} onChange={(v) => setForm({ ...form, problem_template: v })} error={errors.problem_template} labels={labels} />
          <TemplateField label="Justification" value={form.rationale_template} onChange={(v) => setForm({ ...form, rationale_template: v })} error={errors.rationale_template} labels={labels} />
          {usedKeys.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="text-muted">Insérer la valeur de la PME dans la justification :</span>
              {usedKeys.map((key) => (
                <button key={key} type="button" onClick={() => insert("rationale_template", key)} className="rounded-full border border-line px-2 py-0.5 hover:border-brand-600">
                  {readableTemplate(`{{${key}}}`, labels)}
                </button>
              ))}
            </div>
          )}
        </fieldset>

        {!advanced && clauses.length > 0 && (
          <div className="rounded-md bg-brand-50 p-3 text-sm" data-testid="rule-preview">
            <p className="text-xs font-medium text-muted">Aperçu de la règle</p>
            <p>
              <span className="font-semibold text-brand-800">SI</span> {describeCondition(combinator, clauses, labels)}
            </p>
            <p>
              <span className="font-semibold text-brand-800">ALORS</span> proposer « {offerTitle ?? "…"} »
            </p>
          </div>
        )}

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

function TemplateField({
  label,
  value,
  onChange,
  error,
  labels,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  labels: Record<string, string>;
}) {
  const readable = readableTemplate(value, labels);
  return (
    <div>
      <TextInput label={label} required value={value} onChange={(e) => onChange(e.target.value)} error={error} />
      {readable !== value && <p className="mt-1 text-xs text-muted">Lecture : {readable}</p>}
    </div>
  );
}
