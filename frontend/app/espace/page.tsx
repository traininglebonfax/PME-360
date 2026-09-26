"use client";

import { useQuery } from "@tanstack/react-query";

import { useGuard } from "@/components/AppShell";
import { BrandMark } from "@/components/Brand";
import { LifecycleBadge } from "@/components/LifecycleBadge";
import Link from "next/link";

import { NotificationBell } from "@/components/NotificationBell";
import { Dumbbell } from "@/components/charts/Charts";
import { ReportsList } from "@/components/reports/ReportsList";
import { Alert, ButtonLink, Card, LoadingBlock } from "@/components/ui";
import { DOCUMENT_STATUS } from "@/lib/documents";
import { ACTION_STATUS, type ActionStatus } from "@/lib/plans";
import { formatDate } from "@/lib/format";
import { formatPercent, formatScore } from "@/lib/scoring";
import { api, errorMessage, unwrap } from "@/lib/api";
import type { PmeDashboard } from "@/lib/dashboards";
import { useLogout } from "@/lib/session";

/**
 * Portail PME, mobile d'abord (Document 1, § 10 ; Document 9, § 2).
 * L'accueil répond à 4 questions : où j'en suis, que dois-je faire, qu'est-ce qui a été validé, mes échéances.
 */
export default function PmeSpacePage() {
  const { me, isLoading } = useGuard("pme");
  const logout = useLogout();
  const pmeId = me?.pme_ids[0];
  const dashboard = useQuery({
    queryKey: ["dashboard", "pme", pmeId],
    queryFn: async () =>
      (await unwrap(api.GET("/api/v1/dashboards/pme/{pme_id}", { params: { path: { pme_id: pmeId! } } }))) as unknown as PmeDashboard,
    enabled: Boolean(pmeId),
  });

  if (isLoading || !me) return <LoadingBlock />;

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <BrandMark className="h-8 w-8" />
            <span className="font-semibold">Mon espace</span>
          </div>
          <div className="flex items-center gap-2">
            <NotificationBell tone="light" preferencesHref="/espace/notifications" />
            <button onClick={logout} className="text-sm text-muted hover:text-ink">
              Se déconnecter
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-2xl space-y-4 px-4 py-6">
        {dashboard.isLoading ? (
          <LoadingBlock />
        ) : dashboard.error ? (
          <Alert>{errorMessage(dashboard.error)}</Alert>
        ) : dashboard.data ? (
          <>
            <div>
              <p className="text-sm text-muted">Bonjour {me.user.full_name.split(" ")[0]} 👋</p>
              <h1 className="text-xl font-semibold">{dashboard.data.pme.legal_name}</h1>
              <div className="mt-1">
                <LifecycleBadge status={dashboard.data.pme.lifecycle_status} />
              </div>
            </div>

            <Card title="Où j'en suis ?">
              <ScoreSummary data={dashboard.data} />
            </Card>

            <Card title="Que dois-je faire maintenant ?">
              {dashboard.data.open_diagnostic?.status === "EN_COLLECTE" ? (
                <div className="flex flex-col gap-3">
                  <p className="text-sm text-ink">
                    Répondez au questionnaire du diagnostic 360°. Vous pouvez le faire en plusieurs fois : vos réponses sont enregistrées
                    automatiquement.
                  </p>
                  <ButtonLink href="/espace/diagnostic">Remplir le questionnaire</ButtonLink>
                </div>
              ) : dashboard.data.open_diagnostic?.status === "EN_REVUE" ? (
                <p className="text-sm text-muted">Merci ! Votre conseiller examine vos réponses. Vos résultats s'afficheront ici après validation.</p>
              ) : (
                <NextActions data={dashboard.data} />
              )}
            </Card>

            {dashboard.data.evolution.length > 0 && (
              <Card title="Mon évolution par domaine">
                <Dumbbell rows={dashboard.data.evolution} />
              </Card>
            )}

            <ReportsList pmeId={dashboard.data.pme.id} pmeView />

            <Card title="Mon conseiller GUDE-PME">
              {dashboard.data.advisor ? (
                <div className="text-sm">
                  <p className="font-medium">{dashboard.data.advisor.full_name}</p>
                  <p className="text-muted">
                    <a href={`mailto:${dashboard.data.advisor.email}`} className="text-brand-700 hover:underline">
                      {dashboard.data.advisor.email}
                    </a>
                    {dashboard.data.advisor.phone && ` · ${dashboard.data.advisor.phone}`}
                  </p>
                </div>
              ) : (
                <p className="text-sm text-muted">Un conseiller vous sera bientôt attribué.</p>
              )}
            </Card>

            <Card title="Ce qui a été validé ou refusé">
              {dashboard.data.feedback.length === 0 ? (
                <p className="text-sm text-muted">Aucun retour pour le moment.</p>
              ) : (
                <ul className="space-y-2">
                  {dashboard.data.feedback.map((item) => {
                    const ok = item.status === "CONFORME" || item.status === "CONFORME_SOUS_RESERVE";
                    return (
                      <li key={item.id} className="text-sm">
                        <p className={ok ? "text-brand-800" : "text-red-800"}>
                          {ok ? "✔" : "✖"} {item.title} : {DOCUMENT_STATUS[item.status]?.label.toLowerCase() ?? item.status}
                        </p>
                        {item.reason && <p className="pl-5 text-muted">→ « {item.reason} »</p>}
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>

            <Card title="Mes prochaines échéances" action={<Link href="/espace/documents" className="text-sm text-brand-700 hover:underline">Mes documents</Link>}>
              {dashboard.data.deadlines.length === 0 ? (
                <p className="text-sm text-muted">Aucune échéance pour le moment.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {dashboard.data.deadlines.slice(0, 5).map((deadline) => (
                    <li key={deadline.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                      <span>
                        {deadline.label} <span className="text-muted">· {deadline.period}</span>
                      </span>
                      <span className={deadline.status === "EN_RETARD" ? "font-medium text-red-700" : "text-muted"}>
                        {deadline.status === "EN_RETARD" ? "en retard" : `avant le ${formatDate(deadline.due_date)}`}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {dashboard.data.compliance.rate !== null && (
                <p className="mt-3 text-xs text-muted">Dossier complet à {formatPercent(dashboard.data.compliance.rate)}.</p>
              )}
            </Card>
          </>
        ) : (
          <Alert tone="warning">Aucune entreprise n'est associée à votre compte.</Alert>
        )}
      </main>
    </div>
  );
}

function ScoreSummary({ data }: { data: PmeDashboard }) {
  const score = data.score;
  if (!score) {
    return (
      <p className="text-sm text-muted">
        Votre diagnostic 360° n'est pas encore validé. Votre score et votre niveau de maturité s'afficheront ici.
      </p>
    );
  }
  return (
    <div>
      <p className="text-4xl font-semibold text-ink">
        {formatScore(score.global_score)}
        <span className="text-base font-normal text-muted">/100</span>
      </p>
      <p className="mt-1 text-sm font-medium text-brand-800">
        Niveau {score.maturity_level} · {score.maturity_label}
      </p>
      {score.delta_since_baseline !== null && (
        <p className="mt-1 text-sm text-ink">
          {score.delta_since_baseline >= 0 ? "▲ +" : "▼ "}
          {String(score.delta_since_baseline).replace(".", ",")} points depuis votre premier diagnostic
          {score.baseline_date ? ` (${formatDate(score.baseline_date)})` : ""}
        </p>
      )}
      <p className="mt-2 text-xs text-muted">
        Fiabilité de la mesure : {formatPercent(score.confidence)} ({score.confidence_label?.toLowerCase()}). Elle augmentera quand vos
        justificatifs seront déposés et vérifiés.
      </p>
    </div>
  );
}

function NextActions({ data }: { data: PmeDashboard }) {
  const plan = data.next_actions.plan;
  if (!plan)
    return (
      <p className="text-sm text-muted">
        Rien pour le moment. Votre conseiller prépare votre plan d'accompagnement : vos prochaines actions, avec le pourquoi et les documents à
        fournir, apparaîtront ici.
      </p>
    );
  if (plan.to_accept)
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-ink">Votre plan d'accompagnement ({plan.total} actions) est prêt. Consultez-le et acceptez-le pour démarrer.</p>
        <ButtonLink href="/espace/plan">Voir mon plan</ButtonLink>
      </div>
    );
  const items = data.next_actions.items.slice(0, 3);
  return (
    <div className="space-y-3">
      {items.length === 0 ? (
        <p className="text-sm text-muted">Toutes les actions de votre plan sont terminées. Bravo !</p>
      ) : (
        <ul className="divide-y divide-line">
          {items.map((item) => {
            const status = ACTION_STATUS[item.status as ActionStatus];
            return (
              <li key={item.id} className="py-2">
                <Link href={`/espace/plan/${item.id}`} className="flex items-center justify-between gap-3 text-sm hover:text-brand-700">
                  <span className="font-medium">{item.title}</span>
                  <span className={item.overdue ? "text-xs font-medium text-red-700" : "text-xs text-muted"}>
                    {item.overdue ? "en retard" : status?.pme ?? item.status} · {formatDate(item.due_date)}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      <p className="text-xs text-muted">
        {plan.done}/{plan.total} action(s) terminée(s) · {plan.in_progress} en cours
        {plan.overdue > 0 && <span className="font-medium text-red-700"> · {plan.overdue} en retard</span>} ·{" "}
        <Link href="/espace/plan" className="text-brand-700 hover:underline">
          Voir tout mon plan
        </Link>
      </p>
    </div>
  );
}
