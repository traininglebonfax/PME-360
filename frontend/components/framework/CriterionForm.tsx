"use client";

/**
 * Critère du référentiel : libellé, lentille, poids, grille des niveaux 0 à 4, preuves attendues, module sectoriel
 * et règle d'applicabilité (constructeur visuel). La grille met à jour les réponses de la question principale.
 */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { initialRuleState, ProfileRuleBuilder, type RuleState, ruleValue } from "@/components/rules/ProfileRuleBuilder";
import { Alert, Button, SelectInput, TextInput } from "@/components/ui";
import { api, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { type EditorCriterion, EVIDENCE_POLICIES, fieldErrors, LEVEL_LABELS, useEditorMutation } from "@/lib/frameworkEditor";
import { SIZE_LABELS } from "@/lib/labels";
import { CRITERION_VARIABLES } from "@/lib/profileRules";
import { useReference } from "@/lib/references";
import { LENS_LABELS } from "@/lib/scoring";

export function CriterionForm({
  versionId,
  dimension,
  criterion,
  onDone,
}: {
  versionId: string;
  dimension: string;
  criterion: EditorCriterion | null;
  onDone: () => void;
}) {
  const sectors = useReference("sectors");
  const regions = useReference("regions");
  const documentTypes = useQuery({ queryKey: ["config-document-types"], queryFn: () => unwrap(api.GET("/api/v1/config/document-types")) });
  const [form, setForm] = useState({
    code: "",
    name: criterion?.name ?? "",
    lens: (criterion?.lens ?? "O") as Schemas["LensEnum"],
    weight: criterion ? String(Number(criterion.weight)) : "",
    is_critical: criterion?.is_critical ?? false,
    declarative_cap_level: String(criterion?.declarative_cap_level ?? 2),
    evidence_policy: (criterion?.evidence_policy ?? "NONE") as Schemas["EvidencePolicyEnum"],
    sector_module: criterion?.sector_module ?? "",
    question: "",
  });
  const [rubric, setRubric] = useState<string[]>(criterion?.rubric ?? ["", "", "", "", ""]);
  const [documents, setDocuments] = useState<string[]>(criterion?.evidence_document_types ?? []);
  const [applicability, setApplicability] = useState<RuleState>(() => initialRuleState(criterion?.applicability, CRITERION_VARIABLES));
  const [localError, setLocalError] = useState<string | null>(null);
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch });

  const listOptions = {
    size_category: Object.entries(SIZE_LABELS).map(([value, label]) => ({ value, label })),
    sector: (sectors.data ?? []).map((s) => ({ value: s.code, label: s.name })),
    region: (regions.data ?? []).map((r) => ({ value: r.code, label: r.name })),
  };
  const typeNames = Object.fromEntries((documentTypes.data ?? []).map((t) => [t.code, t.name]));

  const save = useEditorMutation(
    versionId,
    () => {
      let rule: unknown;
      try {
        rule = ruleValue(applicability);
      } catch {
        setLocalError("Applicabilité : JSON invalide.");
        return Promise.reject(new Error("Applicabilité : JSON invalide."));
      }
      setLocalError(null);
      const body = {
        name: form.name,
        dimension,
        lens: form.lens,
        weight: form.weight,
        is_critical: form.is_critical,
        rubric,
        declarative_cap_level: Number(form.declarative_cap_level),
        evidence_policy: form.evidence_policy,
        evidence_document_types: documents,
        sector_module: form.sector_module,
        applicability: rule,
      };
      return criterion
        ? unwrap(
            api.PATCH("/api/v1/framework-versions/{version_id}/criteria/{item_id}", {
              params: { path: { version_id: versionId, item_id: criterion.id } },
              body,
            }),
          )
        : unwrap(
            api.POST("/api/v1/framework-versions/{version_id}/criteria", {
              params: { path: { version_id: versionId } },
              body: { ...body, code: form.code.trim().toUpperCase(), question: form.question },
            }),
          );
    },
    onDone,
  );
  const errors = fieldErrors(save.error);

  return (
    <form
      className="grid gap-3 rounded-lg border border-brand-100 bg-brand-50/30 p-4 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      {criterion ? (
        <p className="text-sm sm:col-span-2">
          Critère <span className="font-mono">{criterion.code}</span>{" "}
          <span className="text-xs text-muted">(code non modifiable : il est utilisé par les règles d'accompagnement)</span>
        </p>
      ) : (
        <TextInput label="Code du critère" value={form.code} onChange={(e) => set({ code: e.target.value.toUpperCase() })} hint="Ex. FOR-12" error={errors.code} required />
      )}
      <div className={criterion ? "sm:col-span-2" : ""}>
        <TextInput label="Libellé du critère" value={form.name} onChange={(e) => set({ name: e.target.value })} error={errors.name} maxLength={300} required />
      </div>
      <SelectInput
        label="Lentille"
        value={form.lens}
        onChange={(e) => set({ lens: e.target.value as Schemas["LensEnum"] })}
        placeholder="—"
        options={Object.entries(LENS_LABELS).map(([value, label]) => ({ value, label }))}
        error={errors.lens}
      />
      <TextInput
        label="Poids dans la dimension (points)"
        type="number"
        min={0.01}
        max={100}
        step="0.01"
        value={form.weight}
        onChange={(e) => set({ weight: e.target.value })}
        error={errors.weight}
        required
      />

      <fieldset className="space-y-2 rounded-lg border border-line bg-white p-3 sm:col-span-2">
        <legend className="px-1 text-sm font-medium">Grille de maturité (ce qui est observé à chaque niveau)</legend>
        {rubric.map((anchor, level) => (
          <div key={level} className="flex items-center gap-2">
            <span className="w-16 shrink-0 text-xs font-medium text-muted">{LEVEL_LABELS[level]}</span>
            <input
              aria-label={`Grille ${LEVEL_LABELS[level]}`}
              className="min-w-0 flex-1 rounded-md border border-line px-2 py-1 text-sm"
              value={anchor}
              onChange={(e) => setRubric(rubric.map((a, i) => (i === level ? e.target.value : a)))}
              required
            />
          </div>
        ))}
        {errors.rubric && (
          <p className="text-xs text-red-700" role="alert">
            {errors.rubric}
          </p>
        )}
      </fieldset>

      {!criterion && (
        <div className="sm:col-span-2">
          <TextInput
            label="Question principale (facultatif)"
            value={form.question}
            onChange={(e) => set({ question: e.target.value })}
            hint="Question à choix unique dont les réponses reprennent la grille ci-dessus."
          />
        </div>
      )}

      <SelectInput
        label="Preuve"
        value={form.evidence_policy}
        onChange={(e) => set({ evidence_policy: e.target.value as Schemas["EvidencePolicyEnum"] })}
        placeholder="—"
        options={Object.entries(EVIDENCE_POLICIES).map(([value, label]) => ({ value, label }))}
      />
      <SelectInput
        label="Niveau maximal sur simple déclaration"
        value={form.declarative_cap_level}
        onChange={(e) => set({ declarative_cap_level: e.target.value })}
        placeholder="—"
        options={LEVEL_LABELS.map((label, level) => ({ value: String(level), label }))}
        hint="Au-delà, une preuve vérifiée est nécessaire."
      />
      <div className="space-y-1.5 sm:col-span-2">
        <p className="text-sm font-medium">Documents qui prouvent ce critère</p>
        <div className="flex flex-wrap gap-2">
          {documents.map((code) => (
            <span key={code} className="flex items-center gap-1 rounded-md bg-white px-2 py-1 text-xs ring-1 ring-line">
              {typeNames[code] ?? code}
              <button type="button" aria-label={`Retirer ${typeNames[code] ?? code}`} className="text-red-700" onClick={() => setDocuments(documents.filter((d) => d !== code))}>
                ×
              </button>
            </span>
          ))}
          <select
            aria-label="Ajouter un document de preuve"
            className="rounded-md border border-line px-2 py-1 text-xs"
            value=""
            onChange={(e) => e.target.value && setDocuments([...documents, e.target.value])}
          >
            <option value="">+ Ajouter un document…</option>
            {(documentTypes.data ?? [])
              .filter((t) => !documents.includes(t.code))
              .map((t) => (
                <option key={t.code} value={t.code}>
                  {t.name}
                </option>
              ))}
          </select>
        </div>
        {errors.evidence_document_types && <p className="text-xs text-red-700">{errors.evidence_document_types}</p>}
      </div>
      <SelectInput
        label="Module sectoriel"
        value={form.sector_module}
        onChange={(e) => set({ sector_module: e.target.value })}
        placeholder="Tronc commun (toutes les PME)"
        options={listOptions.sector}
        error={errors.sector_module}
      />
      <label className="flex items-center gap-2 self-end pb-2 text-sm">
        <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={form.is_critical} onChange={(e) => set({ is_critical: e.target.checked })} />
        Critère critique (plafonne le score s'il est faible ; exige une preuve)
      </label>
      <div className="sm:col-span-2">
        <ProfileRuleBuilder
          legend="PME concernées par ce critère"
          variables={CRITERION_VARIABLES}
          listOptions={listOptions}
          state={applicability}
          onChange={setApplicability}
          error={errors.applicability}
          everyone="Toutes les PME"
        />
      </div>
      {(localError || (save.error && Object.keys(errors).length === 0)) && (
        <div className="sm:col-span-2">
          <Alert>{localError ?? errorMessage(save.error)}</Alert>
        </div>
      )}
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" loading={save.isPending}>
          {criterion ? "Enregistrer le critère" : "Ajouter le critère"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Annuler
        </Button>
      </div>
    </form>
  );
}
