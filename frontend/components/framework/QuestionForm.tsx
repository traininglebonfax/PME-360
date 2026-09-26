"use client";

/**
 * Question du questionnaire : texte en langage simple, aide, « pourquoi cette question », public visé et, pour un
 * choix unique, les réponses possibles avec le niveau (0 à 4) qu'elles donnent au critère.
 */
import { useState } from "react";

import { Alert, Button, SelectInput, TextInput } from "@/components/ui";
import { api, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { AUDIENCES, type EditorQuestion, fieldErrors, LEVEL_LABELS, QUESTION_TYPES, useEditorMutation } from "@/lib/frameworkEditor";

type Option = { value?: string; label: string; level: number };

export function QuestionForm({
  versionId,
  question,
  parent,
  defaultOptions,
  onDone,
}: {
  versionId: string;
  question: EditorQuestion | null;
  parent: { criterion?: string; dimension?: string };
  defaultOptions?: Option[];
  onDone: () => void;
}) {
  const [form, setForm] = useState({
    code: "",
    text: question?.text ?? "",
    help_text: question?.help_text ?? "",
    why_text: question?.why_text ?? "",
    type: (question?.type ?? "SINGLE") as Schemas["QuestionTypeEnum"],
    target_audience: (question?.target_audience ?? "LES_DEUX") as Schemas["TargetAudienceEnum"],
    is_required: question?.is_required ?? true,
    evidence_hint: question?.evidence_hint ?? "",
  });
  const [options, setOptions] = useState<Option[]>(
    ((question?.options as Option[] | undefined)?.length ? (question!.options as Option[]) : defaultOptions) ?? [
      { label: "Non", level: 0 },
      { label: "Oui", level: 3 },
    ],
  );
  const [visibility, setVisibility] = useState(question?.visibility ? JSON.stringify(question.visibility, null, 2) : "");
  const [localError, setLocalError] = useState<string | null>(null);
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch });

  const save = useEditorMutation(
    versionId,
    () => {
      let visibilityRule: unknown = null;
      try {
        visibilityRule = visibility.trim() ? JSON.parse(visibility) : null;
      } catch {
        setLocalError("Règle de visibilité : JSON invalide.");
        return Promise.reject(new Error("Règle de visibilité : JSON invalide."));
      }
      setLocalError(null);
      const body = {
        text: form.text,
        help_text: form.help_text,
        why_text: form.why_text,
        type: form.type,
        target_audience: form.target_audience,
        is_required: form.is_required,
        evidence_hint: form.evidence_hint,
        options: form.type === "SINGLE" ? options : [],
        visibility: visibilityRule,
      };
      const path = { params: { path: { version_id: versionId } } };
      return question
        ? unwrap(api.PATCH("/api/v1/framework-versions/{version_id}/questions/{item_id}", { params: { path: { version_id: versionId, item_id: question.id } }, body }))
        : unwrap(api.POST("/api/v1/framework-versions/{version_id}/questions", { ...path, body: { ...body, ...parent, code: form.code.trim().toUpperCase() } }));
    },
    onDone,
  );
  const errors = fieldErrors(save.error);
  const engineFed = Boolean(question?.feeds);

  return (
    <form
      className="grid gap-3 rounded-lg border border-line bg-gray-50/60 p-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      {question ? (
        <p className="text-xs text-muted sm:col-span-2">
          Question <span className="font-mono">{question.code}</span>
          {engineFed && ` · alimente le moteur (${question.feeds}) : son type ne change pas`}
        </p>
      ) : (
        <TextInput label="Code de la question" value={form.code} onChange={(e) => set({ code: e.target.value.toUpperCase() })} error={errors.code} required />
      )}
      <div className="sm:col-span-2">
        <TextInput label="Question posée" value={form.text} onChange={(e) => set({ text: e.target.value })} error={errors.text} maxLength={500} required />
      </div>
      <TextInput label="Aide (facultatif)" value={form.help_text} onChange={(e) => set({ help_text: e.target.value })} error={errors.help_text} />
      <TextInput label="Pourquoi cette question ?" value={form.why_text} onChange={(e) => set({ why_text: e.target.value })} error={errors.why_text} />
      <SelectInput
        label="Type de réponse"
        value={form.type}
        disabled={engineFed}
        onChange={(e) => set({ type: e.target.value as Schemas["QuestionTypeEnum"] })}
        placeholder="—"
        options={Object.entries(QUESTION_TYPES).map(([value, label]) => ({ value, label }))}
        error={errors.type}
      />
      <SelectInput
        label="Qui répond"
        value={form.target_audience}
        onChange={(e) => set({ target_audience: e.target.value as Schemas["TargetAudienceEnum"] })}
        placeholder="—"
        options={Object.entries(AUDIENCES).map(([value, label]) => ({ value, label }))}
      />
      {form.type === "SINGLE" && (
        <fieldset className="space-y-2 rounded-lg border border-line bg-white p-3 sm:col-span-2">
          <legend className="px-1 text-sm font-medium">Réponses possibles et niveau atteint</legend>
          {options.map((option, index) => (
            <div key={index} className="flex flex-wrap items-center gap-2" data-testid="question-option">
              <input
                aria-label={`Réponse ${index + 1}`}
                className="min-w-0 flex-1 rounded-md border border-line px-2 py-1 text-sm"
                value={option.label}
                onChange={(e) => setOptions(options.map((o, i) => (i === index ? { ...o, label: e.target.value } : o)))}
              />
              <select
                aria-label={`Niveau de la réponse ${index + 1}`}
                className="rounded-md border border-line px-2 py-1 text-sm"
                value={option.level}
                onChange={(e) => setOptions(options.map((o, i) => (i === index ? { ...o, level: Number(e.target.value) } : o)))}
              >
                {LEVEL_LABELS.map((label, level) => (
                  <option key={level} value={level}>
                    {label}
                  </option>
                ))}
              </select>
              <button type="button" className="text-xs text-red-700 hover:underline" onClick={() => setOptions(options.filter((_, i) => i !== index))}>
                Retirer
              </button>
            </div>
          ))}
          <button type="button" className="text-xs text-brand-700 hover:underline" onClick={() => setOptions([...options, { label: "", level: 0 }])}>
            + Ajouter une réponse
          </button>
          {errors.options && (
            <p className="text-xs text-red-700" role="alert">
              {errors.options}
            </p>
          )}
        </fieldset>
      )}
      <TextInput
        label="Preuve demandée pour les niveaux élevés"
        value={form.evidence_hint}
        onChange={(e) => set({ evidence_hint: e.target.value })}
        error={errors.evidence_hint}
      />
      <label className="flex items-center gap-2 self-end pb-2 text-sm">
        <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={form.is_required} onChange={(e) => set({ is_required: e.target.checked })} />
        Réponse obligatoire
      </label>
      <details className="text-sm sm:col-span-2" open={Boolean(visibility)}>
        <summary className="cursor-pointer text-muted">Condition d'affichage (avancé)</summary>
        <textarea
          aria-label="Condition d'affichage (JSON Logic)"
          className="mt-2 h-20 w-full rounded-md border border-line p-2 font-mono text-xs"
          value={visibility}
          onChange={(e) => setVisibility(e.target.value)}
          placeholder='{"==": [{"var": "has_stock"}, true]}'
        />
        <p className="text-xs text-muted">Vide : la question est toujours posée.</p>
        {errors.visibility && <p className="text-xs text-red-700">{errors.visibility}</p>}
      </details>
      {(localError || (save.error && Object.keys(errors).length === 0)) && (
        <div className="sm:col-span-2">
          <Alert>{localError ?? errorMessage(save.error)}</Alert>
        </div>
      )}
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" loading={save.isPending}>
          {question ? "Enregistrer la question" : "Ajouter la question"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Annuler
        </Button>
      </div>
    </form>
  );
}
