"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { BarList } from "@/components/BarList";
import { LifecycleBadge } from "@/components/LifecycleBadge";
import { Alert, Badge, ButtonLink, Card, EmptyState, Kpi, LoadingBlock, PageHeader } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import type { AdvisorDashboard, PortfolioDashboard, ProgressRow } from "@/lib/dashboards";
import { formatDateTime, formatRelative } from "@/lib/format";
import { LIFECYCLE_LABELS, SIZE_LABELS } from "@/lib/labels";
import { DIAGNOSTIC_TYPE_LABELS, formatPercent, formatScore, PRIORITY_TONES } from "@/lib/scoring";
import { hasPermission, useMe } from "@/lib/session";

type QueueItem = AdvisorDashboard["work_queue"]["items"][number];

const QUEUE_KINDS: Record<string, { label: string; tone: "danger" | "warning" | "info" | "neutral"; href: (item: QueueItem) => string }> = {
  ALERTE: { label: "Alerte", tone: "danger", href: (item) => `/pme/${item.pme_id}?onglet=alertes` },
  DOCUMENT_A_VERIFIER: { label: "Document", tone: "warning", href: (item) => `/verifications/${item.id}` },
  DIAGNOSTIC_A_VALIDER: { label: "Diagnostic", tone: "info", href: (item) => `/diagnostics/${item.id}/revue` },
  ECHEANCE_EN_RETARD: { label: "Retard", tone: "neutral", href: (item) => `/pme/${item.pme_id}?onglet=documents` },
  ACTION_EN_RETARD: { label: "Action", tone: "warning", href: (item) => `/actions/${item.id}` },
};

function signed(value: number): string {
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(1).replace(".", ",")}`;
}

export default function DashboardPage() {
  const { data: me } = useMe();
  const canPortfolio = hasPermission(me, "dashboard.portfolio");
  const advisor = useQuery({
    queryKey: ["dashboard", "advisor"],
    queryFn: async () => (await unwrap(api.GET("/api/v1/dashboards/advisor"))) as unknown as AdvisorDashboard,
  });
  const portfolio = useQuery({
    queryKey: ["dashboard", "portfolio"],
    queryFn: async () => (await unwrap(api.GET("/api/v1/dashboards/portfolio"))) as unknown as PortfolioDashboard,
    enabled: canPortfolio,
  });

  if (advisor.isLoading) return <LoadingBlock />;
  if (advisor.error) return <Alert>{errorMessage(advisor.error)}</Alert>;
  const data = advisor.data!;
  const queue = data.work_queue.items;

  return (
    <>
      <PageHeader
        title={`Bonjour ${me?.user.full_name.split(" ")[0] ?? ""}`}
        subtitle="Votre journée et votre portefeuille de PME"
        actions={hasPermission(me, "pme.create") && <ButtonLink href="/pme/nouvelle">Nouvelle PME</ButtonLink>}
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi label="PME suivies" value={data.kpis.pmes_followed} />
        <Kpi label="Diagnostics à valider" value={data.kpis.diagnostics_to_validate} hint={`${data.kpis.diagnostics_in_progress} en collecte`} />
        <Kpi label="Intervention urgente" value={data.kpis.pmes_urgent} hint="Priorité P1" />
        <Kpi label="Inactives" value={data.kpis.pmes_inactive} hint={`Sans activité depuis ${data.inactivity_days} j`} />
        <Kpi
          label="Documents à vérifier"
          value={data.kpis.documents_to_verify}
          hint={`dont livrables d'actions : ${data.kpis.actions_to_verify} · ${data.kpis.actions_overdue} action(s) en retard`}
        />
        <Kpi
          label="Alertes ouvertes"
          value={data.kpis.alerts_open}
          hint={`${data.kpis.alerts_critical} élevée(s) ou critique(s) · ${data.kpis.deadlines_overdue} échéance(s) en retard`}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Activité récente de mes PME" className="lg:col-span-2" action={<Link href="/pme" className="text-sm text-brand-700 hover:underline">Tout voir</Link>}>
          {data.recent_pmes.length === 0 ? (
            <EmptyState title="Aucune PME dans votre périmètre">Les PME qui vous sont assignées apparaîtront ici.</EmptyState>
          ) : (
            <ul className="divide-y divide-line">
              {data.recent_pmes.map((pme) => (
                <li key={pme.id} className="flex items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <Link href={`/pme/${pme.id}`} className="font-medium text-ink hover:text-brand-700">
                      {pme.legal_name}
                    </Link>
                    <p className="text-xs text-muted">
                      {pme.sector__name ?? "Secteur non renseigné"} · activité {formatRelative(pme.last_activity_at)}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {pme.global_score !== null && <span className="text-sm font-semibold tabular-nums">{formatScore(pme.global_score)}</span>}
                    {pme.priority && <Badge tone={PRIORITY_TONES[pme.priority]}>{pme.priority}</Badge>}
                    <LifecycleBadge status={pme.lifecycle_status} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Ma file de travail">
          {queue.length === 0 ? (
            <p className="text-sm text-muted">Rien en attente : aucune alerte grave, aucun document ni diagnostic à traiter.</p>
          ) : (
            <ul className="space-y-2">
              {queue.slice(0, 12).map((item) => {
                const kind = QUEUE_KINDS[item.kind];
                return (
                  <li key={`${item.kind}-${item.id}`}>
                    <Link href={kind.href(item)} className="block rounded-lg border border-line px-3 py-2 hover:bg-gray-50">
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-sm font-medium">{item.pme_name}</p>
                        <Badge tone={kind.tone}>{kind.label}</Badge>
                      </div>
                      <p className="truncate text-xs text-muted">
                        {item.kind === "DIAGNOSTIC_A_VALIDER" ? DIAGNOSTIC_TYPE_LABELS[item.label] : item.label} · {formatRelative(item.since)}
                      </p>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
          <div className="mt-4">
            <BarList items={data.by_lifecycle} labels={LIFECYCLE_LABELS} />
          </div>
        </Card>
      </div>

      {canPortfolio && portfolio.data && <Portfolio data={portfolio.data} />}
    </>
  );
}

function Portfolio({ data }: { data: PortfolioDashboard }) {
  if (!data?.kpis) return null; // réponse incomplète (rechargement, API indisponible) : pas d'erreur d'affichage
  const k = data.kpis;
  const def = data.definitions;
  return (
    <>
      <div className="mb-3 mt-10 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-lg font-semibold">Vue d'ensemble du portefeuille</h2>
        <p className="text-xs text-muted">
          {data.refreshed_at && `Données au ${formatDateTime(data.refreshed_at)} · `}
          <Link href="/analyses" className="font-medium text-brand-700 hover:underline">
            Analyses détaillées
          </Link>{" "}
          ·{" "}
          <Link href="/portefeuille" className="font-medium text-brand-700 hover:underline">
            Tableau du portefeuille
          </Link>
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi label="PME au total" value={k.pmes_total} hint={`${k.pmes_diagnosed} avec un diagnostic validé`} definition={def.pmes_total} />
        <Kpi label="PME accompagnées" value={k.pmes_accompanied} hint={`${k.pmes_new_this_month} intégrée(s) ce mois-ci`} definition={def.pmes_accompanied} />
        <Kpi label="PME en retard" value={k.pmes_late} hint={`${k.actions_overdue} action(s) en retard`} definition={def.pmes_late} />
        <Kpi label="Actions réalisées" value={k.actions_done} definition={def.actions_done} />
        <Kpi label="PME actives" value={k.pmes_active} hint={`${k.pmes_inactive} inactive(s)`} definition={def.pmes_active} />
        <Kpi label="Sans conseiller" value={k.pmes_without_advisor} definition={def.pmes_without_advisor} />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi
          definition={def.average_score}
          label="Score moyen"
          value={k.average_score === null ? "—" : formatScore(k.average_score)}
          hint={k.average_confidence === null ? undefined : `Médiane ${formatScore(k.median_score)} · confiance ${formatPercent(k.average_confidence)}`}
        />
        <Kpi
          label="Progression moyenne"
          value={k.average_progress === null ? "—" : `${signed(k.average_progress)} pts`}
          hint={`${k.progress_pmes} PME accompagnées depuis 3 mois ou plus`}
          definition={def.average_progress}
        />
        <Kpi label="PME à risque" value={k.pmes_at_risk} hint="Exposition au risque ≥ 50" definition={def.pmes_at_risk} />
        <Kpi label="Intervention urgente" value={k.pmes_urgent} hint="Priorité P1" definition={def.pmes_urgent} />
        <Kpi label="Confiance moyenne" value={k.average_confidence === null ? "—" : formatPercent(k.average_confidence)} definition={def.average_confidence} />
        <Kpi
          definition={def.average_compliance}
          label="Conformité moyenne"
          value={k.average_compliance.value === null ? "—" : formatPercent(k.average_compliance.value)}
          hint={`${k.average_compliance.pmes} PME avec des éléments exigibles`}
        />
      </div>
      {k.low_confidence_share !== null && k.low_confidence_share > 0 && (
        <p className="mt-2 text-xs text-muted">
          {formatPercent(k.low_confidence_share)} des scores reposent sur une confiance faible (données surtout déclaratives) : à lire comme
          indicatifs.
        </p>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Problèmes les plus fréquents" className="lg:col-span-2">
          <p className="mb-3 text-xs text-muted">Part des PME diagnostiquées dont la dimension est sous {data.weakness_threshold}/100.</p>
          {data.weaknesses.length === 0 ? (
            <p className="text-sm text-muted">Aucun diagnostic validé.</p>
          ) : (
            <ul className="space-y-2.5">
              {data.weaknesses.map((w) => (
                <li key={w.code} title={`${w.weak} PME sur ${w.evaluated}`}>
                  <div className="flex justify-between gap-3 text-sm">
                    <span className="text-ink">{w.name}</span>
                    <span className="font-medium tabular-nums">
                      {formatPercent(w.share)} <span className="text-xs font-normal text-muted">({w.weak}/{w.evaluated})</span>
                    </span>
                  </div>
                  <div className="mt-1 h-2 rounded-full bg-gray-100" aria-hidden="true">
                    <div className="h-2 rounded-full bg-brand-600" style={{ width: `${Math.max(w.share * 100, w.share ? 2 : 0)}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          )}
          {data.kpis.pmes_diagnosed < data.min_cell && (
            <p className="mt-3 text-xs text-muted">
              Moins de {data.min_cell} PME diagnostiquées : ces proportions sont données à titre indicatif.
            </p>
          )}
        </Card>
        <div className="space-y-6">
          <Card title="Niveaux de maturité">
            <BarList items={data.by_maturity.map((b) => ({ ...b, label: `N${b.key} · ${b.label}` }))} />
          </Card>
          <Card title="Priorités d'intervention">
            <BarList items={data.by_priority} />
          </Card>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="PME en intervention urgente">
          {data.urgent.length === 0 ? (
            <p className="text-sm text-muted">Aucune.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {data.urgent.map((u) => (
                <li key={u.pme_id} className="flex justify-between gap-2">
                  <Link href={`/pme/${u.pme_id}?onglet=diagnostic`} className="text-ink hover:text-brand-700">
                    {u.pme_name}
                  </Link>
                  <span className="text-muted">risque {formatScore(u.risk_index)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Plus fortes progressions">
          <ProgressList rows={data.progress.top} empty="Pas encore de diagnostic de suivi." />
        </Card>
        <Card title="Stagnation (6 mois, moins de +2 pts)">
          <ProgressList rows={data.progress.stagnating} empty="Aucune PME en stagnation." />
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Par secteur">
          <BarList items={data.by_sector} />
        </Card>
        <Card title="Par région">
          <BarList items={data.by_region} />
        </Card>
        <Card title="Par taille">
          <BarList items={data.by_size} labels={SIZE_LABELS} />
        </Card>
      </div>
    </>
  );
}

function ProgressList({ rows, empty }: { rows: ProgressRow[]; empty: string }) {
  if (rows.length === 0) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ul className="space-y-2 text-sm">
      {rows.map((row) => (
        <li key={row.pme_id} className="flex justify-between gap-2">
          <Link href={`/pme/${row.pme_id}?onglet=diagnostic`} className="truncate text-ink hover:text-brand-700">
            {row.pme_name}
          </Link>
          <span className="shrink-0 tabular-nums text-muted">
            {formatScore(row.from)} → {formatScore(row.to)} ({signed(row.delta)})
          </span>
        </li>
      ))}
    </ul>
  );
}
