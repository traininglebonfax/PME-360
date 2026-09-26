"use client";

/**
 * Création et modification d'une obligation (Document 8) : à qui elle s'applique, à quelle périodicité, quand
 * elle est due et quand relancer. Les règles de profil se construisent visuellement ; le JSON n'apparaît que pour
 * une règle avancée. Une obligation réglementaire reste adossée à une règle vérifiée du registre (RM-08).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { initialRuleState, ProfileRuleBuilder, type RuleState, ruleValue } from "@/components/rules/ProfileRuleBuilder";
import { Alert, Button, SelectInput, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { LIFECYCLE_LABELS, SIZE_LABELS } from "@/lib/labels";
import { buildFrequencyRule, parseFrequencyRule, PROFILE_VARIABLES } from "@/lib/profileRules";
import { useReference } from "@/lib/references";

export const NATURES: Record<string, string> = { REGLEMENTAIRE: "Réglementaire", PROGRAMME: "Programme", BONNE_PRATIQUE: "Bonne pratique" };
export const FREQUENCIES: Record<string, string> = {
  PONCTUELLE: "Ponctuelle", MENSUELLE: "Mensuelle", TRIMESTRIELLE: "Trimestrielle", SEMESTRIELLE: "Semestrielle", ANNUELLE: "Annuelle",
};
const DEFAULT_REMINDERS = "-30, -15, -7, 0, 7, 15, 30";

type Template = Schemas["ObligationTemplate"];

function jsonText(value: unknown) {
  return value ? JSON.stringify(value, null, 2) : "";
}

export function ObligationForm({ initial, onDone }: { initial: Template | null; onDone: () => void }) {
  const queryClient = useQueryClient();
  const documentTypes = useQuery({ queryKey: ["config-document-types"], queryFn: () => unwrap(api.GET("/api/v1/config/document-types")) });
  const rules = useQuery({ queryKey: ["regulatory-rules"], queryFn: () => unwrap(api.GET("/api/v1/regulatory-rules")) });
  const sectors = useReference("sectors");

  const [form, setForm] = useState({
    code: initial?.code ?? "",
    name: initial?.name ?? "",
    description: initial?.description ?? "",
    nature: initial?.nature ?? "PROGRAMME",
    document_type: initial?.document_type ?? "",
    regulatory_rule: initial?.regulatory_rule ?? "",
    frequency: initial?.frequency ?? "ANNUELLE",
    due_days_after_period_end: String(initial?.due_days_after_period_end ?? 30),
    reminders: initial ? initial.reminder_offsets.join(", ") : DEFAULT_REMINDERS,
    is_critical: initial?.is_critical ?? false,
  });
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch });

  // Applicabilité : constructeur si la règle s'y prête, sinon JSON avancé.
  const [applicability, setApplicability] = useState<RuleState>(() => initialRuleState(initial?.applicability, PROFILE_VARIABLES));

  // Périodicité : fixe, selon l'effectif, ou JSON avancé.
  const parsedFrequency = useMemo(() => parseFrequencyRule(initial?.frequency_rule), [initial]);
  const [frequencyMode, setFrequencyMode] = useState<"fixed" | "headcount" | "json">(
    !initial?.frequency_rule ? "fixed" : parsedFrequency ? "headcount" : "json",
  );
  const [byHeadcount, setByHeadcount] = useState(parsedFrequency ?? { threshold: 20, above: "MENSUELLE", below: "TRIMESTRIELLE" });
  const [frequencyJson, setFrequencyJson] = useState(parsedFrequency ? "" : jsonText(initial?.frequency_rule));

  const [errors, setErrors] = useState<Record<string, string>>({});

  const listOptions: Record<string, { value: string; label: string }[]> = {
    size_category: Object.entries(SIZE_LABELS).map(([value, label]) => ({ value, label })),
    lifecycle_status: Object.entries(LIFECYCLE_LABELS).map(([value, label]) => ({ value, label })),
    sector: (sectors.data ?? []).map((s) => ({ value: s.code, label: s.name })),
  };

  const save = useMutation({
    mutationFn: () => {
      const local: Record<string, string> = {};
      let applicabilityRule: unknown = null;
      let frequencyRule: unknown = null;
      try {
        applicabilityRule = ruleValue(applicability);
      } catch {
        local.applicability = "JSON invalide.";
      }
      if (frequencyMode === "headcount") frequencyRule = buildFrequencyRule(byHeadcount);
      if (frequencyMode === "json") {
        try {
          frequencyRule = frequencyJson.trim() ? JSON.parse(frequencyJson) : null;
        } catch {
          local.frequency_rule = "JSON invalide.";
        }
      }
      const offsets = form.reminders
        .split(/[,;\s]+/)
        .filter(Boolean)
        .map(Number);
      if (offsets.some((n) => !Number.isInteger(n))) local.reminder_offsets = "Nombres entiers de jours séparés par des virgules.";
      if (Object.keys(local).length) {
        setErrors(local);
        throw new Error("Corrigez les champs signalés.");
      }
      const body: Schemas["ObligationWriteRequest"] = {
        name: form.name,
        description: form.description,
        nature: form.nature as Schemas["NatureEnum"],
        document_type: form.document_type,
        regulatory_rule: form.regulatory_rule || null,
        frequency: form.frequency as Schemas["FrequencyEnum"],
        frequency_rule: frequencyRule,
        due_days_after_period_end: Number(form.due_days_after_period_end || 0),
        applicability: applicabilityRule,
        reminder_offsets: offsets,
        is_critical: form.is_critical,
      };
      return initial
        ? unwrap(api.PATCH("/api/v1/obligation-templates/{template_id}", { params: { path: { template_id: initial.id } }, body }))
        : unwrap(api.POST("/api/v1/obligation-templates/new", { body: { ...body, code: form.code.trim().toUpperCase() } }));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["obligation-templates"] });
      queryClient.invalidateQueries({ queryKey: ["config-document-types"] });
      queryClient.invalidateQueries({ queryKey: ["regulatory-rules"] });
      onDone();
    },
    onError: (err) => {
      if (err instanceof ApiError) setErrors(err.fieldErrors());
    },
  });
  const fieldError = Object.keys(errors).length > 0;

  const frequencyOptions = Object.entries(FREQUENCIES).map(([value, label]) => ({ value, label }));

  return (
    <form
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        setErrors({});
        save.mutate();
      }}
    >
      {initial ? (
        <p className="text-sm sm:col-span-2">
          Code <span className="font-mono">{initial.code}</span> <span className="text-xs text-muted">(non modifiable)</span>
        </p>
      ) : (
        <TextInput
          label="Code"
          value={form.code}
          onChange={(e) => set({ code: e.target.value.toUpperCase() })}
          hint="Majuscules, chiffres, - et _ ; définitif après création."
          error={errors.code}
          required
        />
      )}
      <TextInput label="Libellé" value={form.name} onChange={(e) => set({ name: e.target.value })} error={errors.name} required />
      <div className="sm:col-span-2">
        <TextInput label="Description" value={form.description} onChange={(e) => set({ description: e.target.value })} error={errors.description} />
      </div>
      <SelectInput
        label="Nature"
        value={form.nature}
        onChange={(e) => set({ nature: e.target.value as Template["nature"] })}
        placeholder="—"
        options={Object.entries(NATURES).map(([value, label]) => ({ value, label }))}
        error={errors.nature}
      />
      <SelectInput
        label="Document à déposer"
        value={form.document_type}
        onChange={(e) => set({ document_type: e.target.value })}
        options={(documentTypes.data ?? []).filter((t) => t.is_active || t.code === form.document_type).map((t) => ({ value: t.code, label: t.name }))}
        error={errors.document_type}
        required
      />
      <div className="sm:col-span-2">
        <SelectInput
          label="Règle du registre réglementaire"
          value={form.regulatory_rule}
          onChange={(e) => set({ regulatory_rule: e.target.value })}
          placeholder="Aucune"
          options={(rules.data ?? []).map((r) => ({ value: r.code, label: `${r.code} — ${r.title}${r.status === "VERIFIE" ? "" : " (non vérifiée)"}` }))}
          hint={form.nature === "REGLEMENTAIRE" ? "Obligatoire pour une obligation réglementaire ; l'activation exige une règle vérifiée (RM-08)." : undefined}
          error={errors.regulatory_rule}
          required={form.nature === "REGLEMENTAIRE"}
        />
      </div>

      <div className="sm:col-span-2">
        <ProfileRuleBuilder
          legend="À qui s'applique l'obligation"
          variables={PROFILE_VARIABLES}
          listOptions={listOptions}
          state={applicability}
          onChange={setApplicability}
          error={errors.applicability}
        />
      </div>

      <fieldset className="space-y-2 rounded-lg border border-line p-3 sm:col-span-2">
        <legend className="px-1 text-sm font-medium">Périodicité et échéance</legend>
        <div className="flex flex-wrap gap-4 text-sm">
          {(
            [
              ["fixed", "Fixe"],
              ["headcount", "Selon l'effectif"],
              ["json", "Règle avancée (JSON)"],
            ] as const
          ).map(([mode, label]) => (
            <label key={mode} className="flex items-center gap-1.5">
              <input type="radio" name="frequency-mode" className="accent-brand-600" checked={frequencyMode === mode} onChange={() => setFrequencyMode(mode)} />
              {label}
            </label>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <SelectInput
            label={frequencyMode === "fixed" ? "Périodicité" : "Périodicité par défaut"}
            value={form.frequency}
            onChange={(e) => set({ frequency: e.target.value as Template["frequency"] })}
            placeholder="—"
            options={frequencyOptions}
            error={errors.frequency}
          />
          <TextInput
            label="Échéance (jours après la fin de période)"
            type="number"
            min={0}
            max={365}
            value={form.due_days_after_period_end}
            onChange={(e) => set({ due_days_after_period_end: e.target.value })}
            error={errors.due_days_after_period_end}
          />
          <TextInput
            label="Relances (jours avant − / après +)"
            value={form.reminders}
            onChange={(e) => set({ reminders: e.target.value })}
            hint="Ex. -15, -7, 0, 7"
            error={errors.reminder_offsets}
          />
        </div>
        {frequencyMode === "headcount" && (
          <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="frequency-builder">
            <select
              aria-label="Périodicité si effectif au-dessus du seuil"
              className="rounded-md border border-line px-2 py-1"
              value={byHeadcount.above}
              onChange={(e) => setByHeadcount({ ...byHeadcount, above: e.target.value })}
            >
              {frequencyOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            si effectif au moins
            <input
              type="number"
              min={1}
              aria-label="Seuil d'effectif"
              className="w-20 rounded-md border border-line px-2 py-1"
              value={byHeadcount.threshold}
              onChange={(e) => setByHeadcount({ ...byHeadcount, threshold: Number(e.target.value) })}
            />
            , sinon
            <select
              aria-label="Périodicité sinon"
              className="rounded-md border border-line px-2 py-1"
              value={byHeadcount.below}
              onChange={(e) => setByHeadcount({ ...byHeadcount, below: e.target.value })}
            >
              {frequencyOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        )}
        {frequencyMode === "json" && (
          <textarea
            aria-label="Règle de périodicité (JSON Logic)"
            className="h-24 w-full rounded-md border border-line p-2 font-mono text-xs"
            value={frequencyJson}
            onChange={(e) => setFrequencyJson(e.target.value)}
            placeholder='{"if": [{">=": [{"var": "headcount"}, 20]}, "MENSUELLE", "TRIMESTRIELLE"]}'
          />
        )}
        {errors.frequency_rule && <p className="text-xs text-red-700" role="alert">{errors.frequency_rule}</p>}
      </fieldset>

      <label className="flex items-center gap-2 text-sm sm:col-span-2">
        <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={form.is_critical} onChange={(e) => set({ is_critical: e.target.checked })} />
        Obligation critique (retard signalé en priorité)
      </label>

      <div className="sm:col-span-2">
        <Alert tone="info">
          {initial
            ? "Les modifications valent pour les prochaines échéances ; les échéances déjà générées ne changent pas."
            : "L'obligation est créée inactive : activez-la dans la liste une fois relue."}
        </Alert>
      </div>
      {save.error && !fieldError && (
        <div className="sm:col-span-2">
          <Alert>{errorMessage(save.error)}</Alert>
        </div>
      )}
      {save.error && fieldError && (
        <div className="sm:col-span-2">
          <Alert>Corrigez les champs signalés.</Alert>
        </div>
      )}
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" loading={save.isPending}>
          {initial ? "Enregistrer" : "Créer l'obligation"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Annuler
        </Button>
      </div>
    </form>
  );
}
