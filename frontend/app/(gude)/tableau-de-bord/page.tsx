"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { BarList } from "@/components/BarList";
import { LifecycleBadge } from "@/components/LifecycleBadge";
import { Alert, ButtonLink, Card, EmptyState, Kpi, LoadingBlock, PageHeader, PendingKpi } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import type { AdvisorDashboard, PortfolioDashboard } from "@/lib/dashboards";
import { formatRelative } from "@/lib/format";
import { LIFECYCLE_LABELS, SIZE_LABELS } from "@/lib/labels";
import { hasPermission, useMe } from "@/lib/session";

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

  return (
    <>
      <PageHeader
        title={`Bonjour ${me?.user.full_name.split(" ")[0] ?? ""}`}
        subtitle="Votre journée et votre portefeuille de PME"
        actions={hasPermission(me, "pme.create") && <ButtonLink href="/pme/nouvelle">Nouvelle PME</ButtonLink>}
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi label="PME suivies" value={data.kpis.pmes_followed} />
        <Kpi label="Inactives" value={data.kpis.pmes_inactive} hint={`Sans activité depuis ${data.inactivity_days} j`} />
        <Kpi label="Intégrées ce mois" value={data.kpis.pmes_onboarded_this_month} />
        <PendingKpi label="Documents à vérifier" phase={data.kpis.documents_to_verify.available_in_phase} />
        <PendingKpi label="Alertes ouvertes" phase={data.kpis.alerts_open.available_in_phase} />
        <PendingKpi label="Diagnostics à valider" phase={data.kpis.diagnostics_to_validate.available_in_phase} />
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
                  <LifecycleBadge status={pme.lifecycle_status} />
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Ma file de travail">
          <p className="text-sm text-muted">
            Documents à vérifier, actions en retard, alertes et diagnostics à valider seront regroupés ici, triés par urgence,
            à partir de la phase {data.work_queue.available_in_phase}.
          </p>
          <div className="mt-4">
            <BarList items={data.by_lifecycle} labels={LIFECYCLE_LABELS} />
          </div>
        </Card>
      </div>

      {canPortfolio && portfolio.data && (
        <>
          <h2 className="mb-3 mt-10 text-lg font-semibold">Vue d'ensemble du portefeuille</h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Kpi label="PME au total" value={portfolio.data.kpis.pmes_total} />
            <Kpi label="Nouvelles ce mois" value={portfolio.data.kpis.pmes_new_this_month} />
            <Kpi label="Accompagnées" value={portfolio.data.kpis.pmes_accompanied} hint="Statut « Accompagnement actif »" />
            <Kpi label="Sans conseiller" value={portfolio.data.kpis.pmes_without_advisor} />
            <PendingKpi label="Score moyen" phase={portfolio.data.kpis.average_score.available_in_phase} />
            <PendingKpi label="Conformité moyenne" phase={portfolio.data.kpis.average_compliance.available_in_phase} />
          </div>
          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <Card title="Par secteur">
              <BarList items={portfolio.data.by_sector} />
            </Card>
            <Card title="Par région">
              <BarList items={portfolio.data.by_region} />
            </Card>
            <Card title="Par taille">
              <BarList items={portfolio.data.by_size} labels={SIZE_LABELS} />
            </Card>
          </div>
        </>
      )}
    </>
  );
}
