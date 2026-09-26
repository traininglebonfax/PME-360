"use client";

/**
 * Intelligence artificielle (Document 4, § 10 à 12) : traçabilité des analyses, politique du tenant (IA externe,
 * quota, seuils de revue), versions des prompts, jeu d'évaluation et index documentaire.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { type FormEvent, useState } from "react";

import { Alert, Badge, Button, Card, EmptyState, Kpi, LoadingBlock, PageHeader, SelectInput, TextInput } from "@/components/ui";
import { ANALYSIS_STATUS, formatConfidence, PROVIDER_LABELS, TASK_LABELS } from "@/lib/ai";
import { api, ApiError, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { hasPermission, useMe } from "@/lib/session";

export default function AiPage() {
  const { data: me } = useMe();
  const admin = hasPermission(me, "org.configure");
  return (
    <>
      <PageHeader
        title="Intelligence artificielle"
        subtitle="Chaque analyse est tracée (modèle, version du prompt, coût) ; l'IA propose, les équipes décident."
      />
      <div className="space-y-6">
        {admin && <SettingsSection />}
        {admin && <EvaluationSection />}
        <AnalysesSection />
      </div>
    </>
  );
}

// --- Paramètres --------------------------------------------------------------------------------------------------

function SettingsSection() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["ai-settings"], queryFn: () => unwrap(api.GET("/api/v1/ai/settings")) });
  if (settings.isLoading) return <LoadingBlock />;
  if (settings.error) return <Alert>{errorMessage(settings.error)}</Alert>;
  const data = settings.data!;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <SettingsForm
        key={JSON.stringify([data.external_allowed, data.monthly_token_quota, data.auto_threshold, data.field_threshold])}
        settings={data}
        onSaved={(updated) => queryClient.setQueryData(["ai-settings"], updated)}
      />
      <Card title="Consommation du mois">
        <div className="grid grid-cols-2 gap-3">
          <Kpi label="Jetons" value={data.usage.tokens.toLocaleString("fr-FR")} hint={`quota ${data.monthly_token_quota.toLocaleString("fr-FR")}`} />
          <Kpi label="Coût estimé" value={`${data.usage.cost_usd.toFixed(2).replace(".", ",")} $`} hint={`depuis le ${new Date(data.usage.since).toLocaleDateString("fr-FR")}`} />
        </div>
        {data.usage.by_task.length > 0 && (
          <table className="mt-4 w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="py-1.5">Tâche</th>
                <th className="py-1.5">Moteur</th>
                <th className="py-1.5 text-right">Analyses</th>
                <th className="py-1.5 text-right">Jetons</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(data.usage.by_task as { task: string; provider: string; count: number; tokens: number }[]).map((row) => (
                <tr key={`${row.task}-${row.provider}`}>
                  <td className="py-1.5">{TASK_LABELS[row.task] ?? row.task}</td>
                  <td className="py-1.5 text-muted">{PROVIDER_LABELS[row.provider] ?? row.provider}</td>
                  <td className="py-1.5 text-right tabular-nums">{row.count}</td>
                  <td className="py-1.5 text-right tabular-nums">{row.tokens.toLocaleString("fr-FR")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="mt-4 border-t border-line pt-3 text-xs text-muted">
          <p className="font-medium text-ink">Versions</p>
          <p>Moteur local : {data.local_engine}</p>
          {Object.entries(data.prompts).map(([code, version]) => (
            <p key={code}>
              <span className="font-mono">{code}</span> : {version}
            </p>
          ))}
          {Object.entries(data.models).map(([task, model]) => (
            <p key={task}>
              Modèle {task} : <span className="font-mono">{model}</span>
            </p>
          ))}
        </div>
      </Card>
    </div>
  );
}

function SettingsForm({ settings, onSaved }: { settings: Schemas["AiSettingsPayload"]; onSaved: (s: Schemas["AiSettingsPayload"]) => void }) {
  const [form, setForm] = useState({
    external_allowed: settings.external_allowed,
    monthly_token_quota: String(settings.monthly_token_quota),
    auto_threshold: String(Math.round(settings.auto_threshold * 100)),
    field_threshold: String(Math.round(settings.field_threshold * 100)),
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.PUT("/api/v1/ai/settings", {
          body: {
            external_allowed: form.external_allowed,
            monthly_token_quota: Number(form.monthly_token_quota),
            auto_threshold: Number(form.auto_threshold) / 100,
            field_threshold: Number(form.field_threshold) / 100,
          },
        }),
      ),
    onSuccess: (updated) => {
      setErrors({});
      onSaved(updated);
    },
    onError: (error) => setErrors(error instanceof ApiError ? error.fieldErrors() : {}),
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }
  return (
    <Card title="Politique IA de l'organisation">
      <form className="space-y-4" onSubmit={submit}>
        <div className="rounded-lg bg-gray-50 p-3 text-sm">
          <p>
            Moteur configuré : <span className="font-medium">{PROVIDER_LABELS[settings.provider] ?? settings.provider}</span>{" "}
            {settings.provider_configured ? <Badge tone="brand">disponible</Badge> : <Badge tone="muted">non configuré</Badge>}
          </p>
          <p className="mt-1 text-xs text-muted">
            Sans IA externe, le moteur local (règles déterministes, sans envoi de données) traite toutes les tâches.
          </p>
        </div>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 accent-brand-600"
            checked={form.external_allowed}
            onChange={(e) => setForm({ ...form, external_allowed: e.target.checked })}
          />
          <span>
            Autoriser l'IA externe
            <span className="block text-xs text-muted">
              Les données personnelles sont pseudonymisées avant tout envoi ; les documents d'identité ne sont jamais transmis.
            </span>
          </span>
        </label>
        <TextInput
          label="Quota mensuel de jetons"
          type="number"
          min={0}
          value={form.monthly_token_quota}
          onChange={(e) => setForm({ ...form, monthly_token_quota: e.target.value })}
          error={errors.monthly_token_quota}
        />
        <div className="grid grid-cols-2 gap-3">
          <TextInput
            label="Seuil document (%)"
            type="number"
            min={50}
            max={100}
            hint="En dessous : vérification humaine"
            value={form.auto_threshold}
            onChange={(e) => setForm({ ...form, auto_threshold: e.target.value })}
            error={errors.auto_threshold}
          />
          <TextInput
            label="Seuil champ critique (%)"
            type="number"
            min={50}
            max={100}
            value={form.field_threshold}
            onChange={(e) => setForm({ ...form, field_threshold: e.target.value })}
            error={errors.field_threshold}
          />
        </div>
        {save.error && !(save.error instanceof ApiError && save.error.code === "validation_error") && <Alert>{errorMessage(save.error)}</Alert>}
        {save.isSuccess && <Alert tone="success">Paramètres enregistrés (tracés dans le journal d'audit).</Alert>}
        <Button type="submit" loading={save.isPending}>
          Enregistrer
        </Button>
      </form>
    </Card>
  );
}

// --- Évaluation et index -----------------------------------------------------------------------------------------

const METRIC_LABELS: Record<string, string> = {
  samples: "Échantillons",
  classification_accuracy: "Classification",
  field_accuracy: "Champs extraits",
  key_financial_accuracy: "Montants financiers clés",
  ece: "Erreur de calibration (ECE)",
  balance_false_positive_rate: "Faux positifs « bilan déséquilibré »",
};

function formatMetricValue(key: string, value: unknown): string {
  if (typeof value !== "number") return String(value ?? "—");
  if (key === "samples") return String(value);
  return `${(value * 100).toFixed(1).replace(".", ",")} %`;
}

function EvaluationSection() {
  const queryClient = useQueryClient();
  const runs = useQuery({ queryKey: ["ai-evaluations"], queryFn: () => unwrap(api.GET("/api/v1/ai/evaluations")) });
  const evaluate = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/ai/evaluations")),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ai-evaluations"] }),
  });
  const reindex = useMutation({ mutationFn: () => unwrap(api.POST("/api/v1/ai/reindex")) });
  const latest = runs.data?.[0];
  const metrics = (latest?.metrics ?? {}) as Record<string, number>;
  const thresholds = (latest?.thresholds ?? {}) as Record<string, number>;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <Card
        title="Jeu d'évaluation"
        action={
          <Button variant="secondary" loading={evaluate.isPending} onClick={() => evaluate.mutate()}>
            Lancer l'évaluation
          </Button>
        }
      >
        {runs.isLoading ? (
          <LoadingBlock />
        ) : !latest ? (
          <EmptyState title="Aucune évaluation">Lancez l'évaluation pour mesurer la qualité des extractions sur le jeu de test.</EmptyState>
        ) : (
          <>
            <p className="mb-3 text-sm">
              {latest.passed ? <Badge tone="brand">Seuils atteints</Badge> : <Badge tone="danger">Seuils non atteints</Badge>}
              <span className="ml-2 text-muted">
                {formatDateTime(latest.created_at)} · {latest.dataset} · {PROVIDER_LABELS[latest.provider] ?? latest.provider}
              </span>
            </p>
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="py-1.5">Mesure</th>
                  <th className="py-1.5 text-right">Résultat</th>
                  <th className="py-1.5 text-right">Seuil</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {Object.entries(metrics).map(([key, value]) => (
                  <tr key={key}>
                    <td className="py-1.5">{METRIC_LABELS[key] ?? key}</td>
                    <td className="py-1.5 text-right tabular-nums">{formatMetricValue(key, value)}</td>
                    <td className="py-1.5 text-right tabular-nums text-muted">{key in thresholds ? formatMetricValue(key, thresholds[key]) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {runs.data!.length > 1 && (
              <p className="mt-3 text-xs text-muted">
                Historique :{" "}
                {runs.data!.slice(1, 6).map((run) => `${new Date(run.created_at).toLocaleDateString("fr-FR")} ${run.passed ? "✓" : "✗"}`).join(" · ")}
              </p>
            )}
          </>
        )}
        {evaluate.error && <p className="mt-2 text-sm text-red-700">{errorMessage(evaluate.error)}</p>}
      </Card>
      <Card title="Index du Copilot">
        <p className="text-sm text-muted">
          Le Copilot s'appuie sur le référentiel, les règles réglementaires vérifiées, les documents validés et l'historique des PME. Reconstruisez
          l'index après une modification importante.
        </p>
        <Button variant="secondary" className="mt-3 w-full" loading={reindex.isPending} onClick={() => reindex.mutate()}>
          Reconstruire l'index
        </Button>
        {reindex.data && (
          <p className="mt-2 text-xs text-muted">
            Indexé : {reindex.data.referentiel} passages du référentiel, {reindex.data.reglementation} règles, {reindex.data.documents} documents,{" "}
            {reindex.data.historique} historiques.
          </p>
        )}
        {reindex.error && <p className="mt-2 text-sm text-red-700">{errorMessage(reindex.error)}</p>}
      </Card>
    </div>
  );
}

// --- Traçabilité -------------------------------------------------------------------------------------------------

function AnalysesSection() {
  const [task, setTask] = useState("");
  const analyses = useQuery({
    queryKey: ["ai-analyses", task],
    queryFn: () => unwrap(api.GET("/api/v1/ai/analyses", { params: { query: { task: task || undefined } } })),
  });
  return (
    <Card
      title="Analyses récentes"
      action={
        <div className="w-56">
          <SelectInput
            label="Tâche"
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="Toutes les tâches"
            options={Object.entries(TASK_LABELS).map(([value, label]) => ({ value, label }))}
          />
        </div>
      }
    >
      {analyses.isLoading ? (
        <LoadingBlock />
      ) : analyses.error ? (
        <Alert>{errorMessage(analyses.error)}</Alert>
      ) : analyses.data!.length === 0 ? (
        <EmptyState title="Aucune analyse">Les analyses apparaîtront ici dès le premier document déposé.</EmptyState>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-line text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="py-2 pr-4">Date</th>
                <th className="py-2 pr-4">Tâche</th>
                <th className="py-2 pr-4">PME</th>
                <th className="py-2 pr-4">Statut</th>
                <th className="py-2 pr-4">Moteur</th>
                <th className="py-2 pr-4 text-right">Confiance</th>
                <th className="py-2 text-right">Durée</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {analyses.data!.map((analysis) => (
                <tr key={analysis.id} className="hover:bg-gray-50">
                  <td className="py-2 pr-4">
                    <Link href={`/ia/analyses/${analysis.id}`} className="text-brand-700 hover:underline">
                      {formatDateTime(analysis.created_at)}
                    </Link>
                  </td>
                  <td className="py-2 pr-4">{TASK_LABELS[analysis.task] ?? analysis.task}</td>
                  <td className="py-2 pr-4 text-muted">{analysis.pme_name || "—"}</td>
                  <td className="py-2 pr-4">
                    <Badge tone={ANALYSIS_STATUS[analysis.status]?.tone}>{ANALYSIS_STATUS[analysis.status]?.label ?? analysis.status}</Badge>
                  </td>
                  <td className="py-2 pr-4 text-muted">{PROVIDER_LABELS[analysis.provider] ?? analysis.provider}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{formatConfidence(analysis.confidence === null ? null : Number(analysis.confidence))}</td>
                  <td className="py-2 text-right tabular-nums text-muted">{analysis.latency_ms} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
