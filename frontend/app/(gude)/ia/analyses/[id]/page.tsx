"use client";

/** « Voir l'analyse IA » (Document 4, § 11) : ce que l'IA a reçu, produit, avec quel modèle et quel prompt. */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Alert, Badge, Card, LoadingBlock } from "@/components/ui";
import { ANALYSIS_STATUS, formatConfidence, PROVIDER_LABELS, TASK_LABELS } from "@/lib/ai";
import { api, errorMessage, unwrap } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export default function AnalysisPage() {
  const { id } = useParams<{ id: string }>();
  const analysis = useQuery({
    queryKey: ["ai-analysis", id],
    queryFn: () => unwrap(api.GET("/api/v1/ai/analyses/{analysis_id}", { params: { path: { analysis_id: id } } })),
  });
  if (analysis.isLoading) return <LoadingBlock />;
  if (analysis.error) return <Alert>{errorMessage(analysis.error)}</Alert>;
  const data = analysis.data!;
  const status = ANALYSIS_STATUS[data.status];

  return (
    <>
      <nav className="mb-2 text-sm text-muted">
        <Link href="/ia" className="hover:text-brand-700">
          Intelligence artificielle
        </Link>{" "}
        / Analyse
      </nav>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{TASK_LABELS[data.task] ?? data.task}</h1>
        <Badge tone={status?.tone}>{status?.label ?? data.status}</Badge>
      </div>
      <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
        <Card title="Traçabilité">
          <dl className="space-y-1.5 text-sm">
            <Row label="Date" value={formatDateTime(data.created_at)} />
            <Row label="Demandée par" value={data.requested_by_name || "Système"} />
            <Row
              label="PME"
              value={
                data.pme ? (
                  <Link href={`/pme/${data.pme}`} className="text-brand-700 hover:underline">
                    {data.pme_name}
                  </Link>
                ) : (
                  "—"
                )
              }
            />
            <Row label="Moteur" value={PROVIDER_LABELS[data.provider] ?? data.provider} />
            <Row label="Modèle" value={<span className="font-mono text-xs">{data.model || "—"}</span>} />
            <Row label="Prompt" value={<span className="font-mono text-xs">{data.prompt_code} v{data.prompt_version}</span>} />
            <Row label="Pseudonymisé" value={data.pseudonymized ? "Oui" : "Non"} />
            <Row label="Confiance" value={formatConfidence(data.confidence === null ? null : Number(data.confidence))} />
            <Row label="Jetons" value={`${data.tokens_in.toLocaleString("fr-FR")} ↑ · ${data.tokens_out.toLocaleString("fr-FR")} ↓`} />
            <Row label="Coût estimé" value={`${Number(data.cost_usd).toFixed(4).replace(".", ",")} $`} />
            <Row label="Durée" value={`${data.latency_ms} ms (${data.attempts} tentative${data.attempts > 1 ? "s" : ""})`} />
          </dl>
          {data.error && (
            <div className="mt-3">
              <Alert tone="warning">{data.error}</Alert>
            </div>
          )}
        </Card>
        <div className="space-y-6">
          <Card title="Entrées (références)">
            <Json value={data.input_refs} />
          </Card>
          <Card title="Sortie">
            <Json value={data.output} />
          </Card>
        </div>
      </div>
    </>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right text-ink">{value}</dd>
    </div>
  );
}

function Json({ value }: { value: unknown }) {
  return <pre className="max-h-[32rem] overflow-auto rounded-lg bg-gray-50 p-3 text-xs leading-relaxed">{JSON.stringify(value ?? null, null, 2)}</pre>;
}
