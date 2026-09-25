"use client";

/**
 * Questionnaire adaptatif (Document 5, § 6) : étapes courtes, sauvegarde automatique, reprise possible.
 * Partagé entre le portail GUDE-PME (niveaux visibles, questions « conseiller ») et le portail PME.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { Alert, Badge, Button, cx, LoadingBlock } from "@/components/ui";
import { api, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { DIAGNOSTIC_STATUS_LABELS, DIAGNOSTIC_TYPE_LABELS } from "@/lib/scoring";

type Question = Schemas["QuestionnaireQuestion"];
type Value = string | number | boolean | null;

const SAVE_DELAY_MS = 500;

export function Questionnaire({ diagnosticId, onSubmitted }: { diagnosticId: string; onSubmitted?: () => void }) {
  const queryClient = useQueryClient();
  const key = ["questionnaire", diagnosticId];
  const questionnaire = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/v1/diagnostics/{diagnostic_id}/questionnaire", { params: { path: { diagnostic_id: diagnosticId } } })),
  });
  const [stepIndex, setStepIndex] = useState(0);
  const [draft, setDraft] = useState<Record<string, Value>>({});
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const pending = useRef<Record<string, Value>>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flush = useCallback(async () => {
    const answers = Object.entries(pending.current).map(([question, value]) => ({ question, value }));
    if (!answers.length) return;
    pending.current = {};
    setSaveState("saving");
    try {
      await unwrap(
        api.PUT("/api/v1/diagnostics/{diagnostic_id}/answers", { params: { path: { diagnostic_id: diagnosticId } }, body: { answers } }),
      );
      setSaveState("saved");
      setSaveError(null);
      // Rechargement : les réponses de profil peuvent faire apparaître ou disparaître des questions.
      await queryClient.invalidateQueries({ queryKey: ["questionnaire", diagnosticId] });
      setDraft((current) => {
        const next = { ...current };
        for (const { question } of answers) if (!(question in pending.current)) delete next[question];
        return next;
      });
    } catch (error) {
      setSaveState("error");
      setSaveError(errorMessage(error));
    }
  }, [diagnosticId, queryClient]);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const setValue = (code: string, value: Value, immediate = true) => {
    setDraft((current) => ({ ...current, [code]: value }));
    pending.current[code] = value;
    if (timer.current) clearTimeout(timer.current);
    if (immediate) timer.current = setTimeout(flush, SAVE_DELAY_MS);
  };

  const submit = useMutation({
    mutationFn: async () => {
      await flush();
      return unwrap(api.POST("/api/v1/diagnostics/{diagnostic_id}/submit", { params: { path: { diagnostic_id: diagnosticId } } }));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: key });
      onSubmitted?.();
    },
  });

  if (questionnaire.isLoading) return <LoadingBlock />;
  if (questionnaire.error) return <Alert>{errorMessage(questionnaire.error)}</Alert>;
  const data = questionnaire.data!;
  const steps = data.steps;
  const step = steps[Math.min(stepIndex, steps.length - 1)];
  const { progress, editable } = data;
  const status = data.diagnostic.status;
  const canSubmit = editable && status === "EN_COLLECTE" && progress.completion >= progress.submit_threshold;

  const answeredIn = (s: (typeof steps)[number]) => s.questions.filter((q) => q.answered || (q.code in draft && draft[q.code] !== null)).length;

  return (
    <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
      <aside className="space-y-4">
        <div className="rounded-xl border border-line bg-white p-4">
          <p className="text-sm font-medium">{DIAGNOSTIC_TYPE_LABELS[data.diagnostic.type]}</p>
          <p className="text-xs text-muted">{DIAGNOSTIC_STATUS_LABELS[status]}</p>
          <div className="mt-3 h-2 rounded-full bg-gray-100" aria-hidden="true">
            <div className="h-2 rounded-full bg-brand-600" style={{ width: `${Math.round(progress.completion * 100)}%` }} />
          </div>
          <p className="mt-1.5 text-xs text-muted">
            {progress.required_answered} / {progress.required} questions obligatoires ({Math.round(progress.completion * 100)} %)
          </p>
          <p className="mt-2 text-xs" aria-live="polite">
            {saveState === "saving" && <span className="text-muted">Enregistrement…</span>}
            {saveState === "saved" && <span className="text-brand-700">✓ Réponses enregistrées</span>}
            {saveState === "error" && <span className="text-red-700">Échec de l'enregistrement</span>}
          </p>
        </div>
        <nav aria-label="Étapes du questionnaire" className="rounded-xl border border-line bg-white p-2">
          <ol className="space-y-0.5">
            {steps.map((s, index) => {
              const done = answeredIn(s);
              return (
                <li key={s.code}>
                  <button
                    onClick={() => setStepIndex(index)}
                    aria-current={index === stepIndex ? "step" : undefined}
                    className={cx(
                      "flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm",
                      index === stepIndex ? "bg-brand-50 font-medium text-brand-800" : "text-ink hover:bg-gray-50",
                    )}
                  >
                    <span className="truncate">{s.title}</span>
                    <span className={cx("shrink-0 text-xs tabular-nums", done === s.questions.length ? "text-brand-700" : "text-muted")}>
                      {done}/{s.questions.length}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>
      </aside>

      <section>
        {saveError && (
          <div className="mb-4">
            <Alert>{saveError}</Alert>
          </div>
        )}
        {!editable && (
          <div className="mb-4">
            <Alert tone="info">Le questionnaire est en lecture seule dans l'état actuel du diagnostic.</Alert>
          </div>
        )}
        <header className="mb-4">
          <h2 className="text-lg font-semibold">{step.title}</h2>
          {step.description && <p className="text-sm text-muted">{step.description}</p>}
        </header>
        <div className="space-y-4">
          {step.questions.map((question) => (
            <QuestionCard
              key={question.code}
              question={question}
              value={question.code in draft ? draft[question.code] : (question.value as Value)}
              disabled={!editable}
              onChange={setValue}
              onCommit={flush}
            />
          ))}
        </div>
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          <Button variant="secondary" disabled={stepIndex === 0} onClick={() => setStepIndex(stepIndex - 1)}>
            Étape précédente
          </Button>
          {stepIndex < steps.length - 1 ? (
            <Button onClick={() => setStepIndex(stepIndex + 1)}>Étape suivante</Button>
          ) : (
            editable &&
            status === "EN_COLLECTE" && (
              <div className="flex flex-col items-end gap-1">
                <Button onClick={() => submit.mutate()} loading={submit.isPending} disabled={!canSubmit}>
                  Soumettre le questionnaire
                </Button>
                {!canSubmit && (
                  <span className="text-xs text-muted">
                    Répondez à au moins {Math.round(progress.submit_threshold * 100)} % des questions obligatoires.
                  </span>
                )}
              </div>
            )
          )}
        </div>
        {submit.error && (
          <div className="mt-4">
            <Alert>{errorMessage(submit.error)}</Alert>
          </div>
        )}
      </section>
    </div>
  );
}

function QuestionCard({
  question,
  value,
  disabled,
  onChange,
  onCommit,
}: {
  question: Question;
  value: Value;
  disabled: boolean;
  onChange: (code: string, value: Value, immediate?: boolean) => void;
  onCommit: () => void;
}) {
  const [showWhy, setShowWhy] = useState(false);
  const name = `q-${question.code}`;
  return (
    <fieldset className="rounded-xl border border-line bg-white p-5" disabled={disabled}>
      <legend className="sr-only">{question.text}</legend>
      <div className="flex items-start justify-between gap-3">
        <p className="font-medium text-ink" aria-hidden="true">
          {question.text}
          {question.required && <span className="text-red-600"> *</span>}
        </p>
        <div className="flex shrink-0 gap-1">
          {question.is_critical && <Badge tone="warning">Critique</Badge>}
          {question.source === "REPRISE" && <Badge tone="muted">À confirmer</Badge>}
        </div>
      </div>
      {question.help_text && <p className="mt-1 text-sm text-muted">{question.help_text}</p>}
      {question.why_text && (
        <button type="button" className="mt-1 text-xs text-brand-700 hover:underline" onClick={() => setShowWhy(!showWhy)} aria-expanded={showWhy}>
          Pourquoi cette question ?
        </button>
      )}
      {showWhy && <p className="mt-1 rounded-md bg-brand-50 px-3 py-2 text-sm text-brand-800">{question.why_text}</p>}

      <div className="mt-3">
        {question.type === "SINGLE" && (
          <div className="space-y-1.5">
            {question.options.map((option) => (
              <label
                key={option.value}
                className={cx(
                  "flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 text-sm",
                  String(value) === option.value ? "border-brand-600 bg-brand-50" : "border-line hover:bg-gray-50",
                )}
              >
                <input
                  type="radio"
                  name={name}
                  className="mt-0.5 accent-brand-600"
                  checked={String(value) === option.value}
                  onChange={() => onChange(question.code, option.value)}
                />
                <span className="flex-1">{option.label}</span>
                {option.level !== undefined && <span className="text-xs tabular-nums text-muted">niv. {option.level}</span>}
              </label>
            ))}
          </div>
        )}
        {question.type === "BOOLEAN" && (
          <div className="flex gap-2">
            {[
              [true, "Oui"],
              [false, "Non"],
            ].map(([option, label]) => (
              <label
                key={String(option)}
                className={cx(
                  "flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-2 text-sm",
                  value === option ? "border-brand-600 bg-brand-50" : "border-line hover:bg-gray-50",
                )}
              >
                <input type="radio" name={name} className="accent-brand-600" checked={value === option} onChange={() => onChange(question.code, option as boolean)} />
                {label as string}
              </label>
            ))}
          </div>
        )}
        {(question.type === "NUMBER" || question.type === "AMOUNT" || question.type === "PERCENT") && (
          <div className="flex max-w-xs items-center gap-2">
            <input
              type="number"
              inputMode="decimal"
              aria-label={question.text}
              className="w-full rounded-lg border border-line px-3 py-2 text-sm focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-100"
              value={value === null || value === undefined ? "" : String(value)}
              min={question.type === "AMOUNT" ? undefined : 0}
              max={question.type === "PERCENT" ? 100 : undefined}
              onChange={(e) => onChange(question.code, e.target.value === "" ? null : Number(e.target.value), false)}
              onBlur={onCommit}
            />
            <span className="text-sm text-muted">{question.type === "AMOUNT" ? "FCFA" : question.type === "PERCENT" ? "%" : ""}</span>
          </div>
        )}
        {question.type === "TEXT" && (
          <textarea
            aria-label={question.text}
            className="w-full rounded-lg border border-line px-3 py-2 text-sm"
            rows={3}
            value={value === null || value === undefined ? "" : String(value)}
            onChange={(e) => onChange(question.code, e.target.value, false)}
            onBlur={onCommit}
          />
        )}
      </div>
      {question.evidence_hint && <p className="mt-2 text-xs text-muted">Preuve qui sera demandée pour les niveaux élevés : {question.evidence_hint}</p>}
    </fieldset>
  );
}
