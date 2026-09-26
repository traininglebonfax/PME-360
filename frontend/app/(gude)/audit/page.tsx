"use client";

/**
 * Tableau de bord auditeur (Document 9, § 5 ; V1), en lecture seule : activité du journal sur la période, intégrité
 * de la chaîne, événements sensibles, revue humaine des propositions de l'IA (par dimension), échantillonnage
 * reproductible de dossiers PME et export CSV du journal. Le tirage et l'export sont eux-mêmes journalisés.
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Alert, Badge, Button, Card, Kpi, LoadingBlock, PageHeader, SelectInput, TextInput } from "@/components/ui";
import { api, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { LIFECYCLE_LABELS } from "@/lib/labels";

const PERIODS = [
  { value: "30", label: "30 derniers jours" },
  { value: "90", label: "90 derniers jours" },
  { value: "365", label: "12 derniers mois" },
];
const ACTOR_TYPES: Record<string, string> = { USER: "Utilisateurs", SYSTEM: "Système", AI: "IA" };

function isoDaysAgo(days: number) {
  const date = new Date();
  date.setDate(date.getDate() - days + 1);
  return date.toISOString().slice(0, 10);
}

function percent(value: number | null | undefined) {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)} %`;
}

export default function AuditorDashboardPage() {
  const [days, setDays] = useState("30");
  const range = useMemo(() => ({ from: isoDaysAgo(Number(days)), to: new Date().toISOString().slice(0, 10) }), [days]);
  const overview = useQuery({
    queryKey: ["audit-overview", range],
    queryFn: () => unwrap(api.GET("/api/v1/audit/overview", { params: { query: range } })),
  });
  const chain = useQuery({ queryKey: ["audit-verify"], queryFn: () => unwrap(api.GET("/api/v1/audit-logs/verify")), enabled: false });
  const exportHref = `/api/v1/audit-logs/export?from=${range.from}T00:00:00&to=${range.to}T23:59:59`;

  return (
    <>
      <PageHeader
        title="Tableau de bord auditeur"
        subtitle="Contrôle a posteriori, en lecture seule : traçabilité des décisions, revue humaine des propositions de l'IA, échantillons de dossiers."
        actions={
          <div className="flex flex-wrap items-end gap-2">
            <SelectInput label="Période" value={days} onChange={(e) => setDays(e.target.value)} placeholder="—" options={PERIODS} />
            <a href={exportHref} download className="rounded-lg border border-brand-600 px-3 py-2.5 text-sm font-medium text-brand-700 hover:bg-brand-50">
              Exporter le journal (CSV)
            </a>
          </div>
        }
      />
      {overview.isLoading ? (
        <LoadingBlock />
      ) : overview.error ? (
        <Alert>{errorMessage(overview.error)}</Alert>
      ) : (
        <Overview data={overview.data!} chain={chain} />
      )}
      <div className="mt-6">
        <Sample />
      </div>
    </>
  );
}

function Overview({
  data,
  chain,
}: {
  data: Schemas["AuditOverview"];
  chain: UseQueryResult<Schemas["ChainVerification"]>;
}) {
  const ai = data.ai_review;
  const maxDomain = Math.max(1, ...data.by_domain.map((d) => d.count));
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi
          label="Entrées du journal"
          value={data.total.toLocaleString("fr-FR")}
          hint={`du ${formatDate(data.period_start)} au ${formatDate(data.period_end)}`}
        />
        <Kpi label="Échecs de connexion" value={data.login_failures} hint="Tentatives refusées sur la période" />
        <Kpi
          label="Propositions IA modifiées"
          value={percent(ai.suggestions_change_rate)}
          hint={`${ai.suggestions_reviewed} proposition(s) de pré-diagnostic revue(s)`}
          definition="Part des propositions de niveau faites par l'IA que le conseiller a modifiées ou écartées lors de la revue."
        />
        <Kpi
          label="Lectures de documents corrigées"
          value={percent(ai.documents_change_rate)}
          hint={`${ai.documents_reviewed} lecture(s) revue(s)`}
          definition="Part des extractions de documents par l'IA corrigées ou rejetées par un humain."
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card
          title="Intégrité du journal"
          action={
            <Button variant="secondary" loading={chain.isFetching} onClick={() => chain.refetch()}>
              Vérifier la chaîne
            </Button>
          }
        >
          <p className="text-sm text-muted">
            Chaque entrée contient l'empreinte de la précédente : toute modification ou suppression est détectée. Les entrées ne peuvent être ni
            modifiées ni supprimées en base.
          </p>
          {chain.data && (
            <div className="mt-3" data-testid="chain-status">
              {chain.data.valid ? (
                <Alert tone="success">Chaîne intègre : {chain.data.entries_checked.toLocaleString("fr-FR")} entrées vérifiées.</Alert>
              ) : (
                <Alert title="Altération détectée">Première entrée invalide : n° {chain.data.first_invalid_id}.</Alert>
              )}
            </div>
          )}
          <dl className="mt-4 grid grid-cols-3 gap-2 text-sm">
            {Object.entries(ACTOR_TYPES).map(([key, label]) => (
              <div key={key}>
                <dt className="text-xs text-muted">{label}</dt>
                <dd className="font-medium tabular-nums">{(data.by_actor_type[key] ?? 0).toLocaleString("fr-FR")}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card title="Activité par domaine">
          {data.by_domain.length === 0 ? (
            <p className="text-sm text-muted">Aucune activité sur la période.</p>
          ) : (
            <ul className="space-y-1.5" aria-label="Activité par domaine">
              {data.by_domain.map((d) => (
                <li key={d.domain} className="grid grid-cols-[10rem_1fr_3.5rem] items-center gap-2 text-sm">
                  <span className="truncate text-muted">{d.domain}</span>
                  <span className="h-2.5 rounded-sm bg-gray-100">
                    <span className="block h-full rounded-sm bg-brand-600" style={{ width: `${(d.count / maxDomain) * 100}%` }} />
                  </span>
                  <span className="text-right tabular-nums">{d.count.toLocaleString("fr-FR")}</span>
                </li>
              ))}
            </ul>
          )}
          {data.top_actors.length > 0 && (
            <p className="mt-3 text-xs text-muted">
              Principaux acteurs : {data.top_actors.map((a) => `${a.name} (${a.count})`).join(", ")}
            </p>
          )}
        </Card>
      </div>

      <Card title="Revue humaine des propositions de l'IA, par dimension">
        {ai.by_dimension.length === 0 ? (
          <p className="text-sm text-muted">Aucune proposition de pré-diagnostic revue sur la période.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-sm" aria-label="Revue des propositions IA par dimension">
              <thead className="text-left text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="py-2 pr-3">Dimension</th>
                  <th className="py-2 pr-3 text-right">Revues</th>
                  <th className="py-2 pr-3 text-right">Acceptées</th>
                  <th className="py-2 pr-3 text-right">Modifiées</th>
                  <th className="py-2 pr-3 text-right">Écartées</th>
                  <th className="py-2">Taux de modification</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {ai.by_dimension.map((d) => (
                  <tr key={d.dimension}>
                    <td className="py-2 pr-3">
                      <span className="font-mono text-xs text-muted">{d.dimension}</span> {d.name}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">{d.reviewed}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{d.accepted}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{d.modified}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{d.rejected}</td>
                    <td className="py-2">
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-24 rounded-sm bg-gray-100">
                          <span className="block h-full rounded-sm bg-brand-600" style={{ width: `${(d.change_rate ?? 0) * 100}%` }} />
                        </span>
                        <span className="tabular-nums">{percent(d.change_rate)}</span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-xs text-muted">
          Documents lus par l'IA et revus : {ai.documents_validated} validé(s), {ai.documents_corrected} corrigé(s), {ai.documents_rejected} rejeté(s). Un
          taux élevé signale une dimension où l'IA doit être surveillée, pas une faute du conseiller.
        </p>
      </Card>

      <Card title="Événements sensibles de la période">
        {data.sensitive.length === 0 ? (
          <p className="text-sm text-muted">Aucun événement sensible (accès, rôles, publications, exports, fichiers bloqués).</p>
        ) : (
          <ul className="divide-y divide-line text-sm" aria-label="Événements sensibles">
            {data.sensitive.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span>
                  <span className="font-medium">{e.label}</span>
                  <span className="text-xs text-muted"> · {e.actor_name ?? (e.actor_type === "SYSTEM" ? "système" : e.actor_type)}</span>
                </span>
                <span className="text-xs text-muted">
                  n° {e.id} · {formatDateTime(e.at)}
                </span>
              </li>
            ))}
          </ul>
        )}
        <Link href="/journal" className="mt-3 inline-block text-sm text-brand-700 hover:underline">
          Ouvrir le journal complet
        </Link>
      </Card>
    </div>
  );
}

function Sample() {
  const [seed, setSeed] = useState("");
  const [size, setSize] = useState("5");
  const [request, setRequest] = useState<{ seed: string; size: string } | null>(null);
  const sample = useQuery({
    queryKey: ["audit-sample", request],
    queryFn: () => unwrap(api.GET("/api/v1/audit/sample", { params: { query: { seed: request!.seed || undefined, size: Number(request!.size) } } })),
    enabled: request !== null,
  });
  return (
    <Card title="Échantillon de dossiers PME">
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setRequest({ seed, size });
        }}
      >
        <TextInput label="Graine (facultatif)" value={seed} onChange={(e) => setSeed(e.target.value)} hint="La même graine redonne le même échantillon." />
        <TextInput label="Taille" type="number" min={1} max={50} value={size} onChange={(e) => setSize(e.target.value)} className="w-24" />
        <Button type="submit" loading={sample.isFetching}>
          Tirer un échantillon
        </Button>
      </form>
      {sample.error && <Alert>{errorMessage(sample.error)}</Alert>}
      {sample.data && (
        <div className="mt-4" data-testid="audit-sample">
          <p className="mb-2 text-sm text-muted">
            {sample.data.items.length} dossier(s) tiré(s) parmi {sample.data.population} — graine <span className="font-mono text-ink">{sample.data.seed}</span>{" "}
            (à noter pour reproduire le tirage).
          </p>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="py-2 pr-3">PME</th>
                  <th className="py-2 pr-3">Statut</th>
                  <th className="py-2 pr-3">Dernier diagnostic validé</th>
                  <th className="py-2 pr-3 text-right">Documents vérifiés</th>
                  <th className="py-2 pr-3 text-right">Propositions IA modifiées</th>
                  <th className="py-2 text-right">Entrées au journal</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {sample.data.items.map((item) => (
                  <tr key={item.id}>
                    <td className="py-2 pr-3">
                      <Link href={`/pme/${item.id}`} className="font-medium text-brand-700 hover:underline">
                        {item.name}
                      </Link>
                      <span className="block text-xs text-muted">{[item.sector, item.region].filter(Boolean).join(" · ")}</span>
                    </td>
                    <td className="py-2 pr-3">
                      <Badge tone="neutral">{LIFECYCLE_LABELS[item.lifecycle_status as keyof typeof LIFECYCLE_LABELS] ?? item.lifecycle_status}</Badge>
                    </td>
                    <td className="py-2 pr-3 text-muted">{item.last_validated_diagnostic ? formatDate(item.last_validated_diagnostic) : "—"}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {item.documents_verified} / {item.documents}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">{item.ai_suggestions_changed}</td>
                    <td className="py-2 text-right tabular-nums">{item.audit_entries}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}
