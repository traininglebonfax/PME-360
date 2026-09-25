"use client";

import { useQuery } from "@tanstack/react-query";

import { useGuard } from "@/components/AppShell";
import { BrandMark } from "@/components/Brand";
import { LifecycleBadge } from "@/components/LifecycleBadge";
import { Alert, Card, LoadingBlock } from "@/components/ui";
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
          <button onClick={logout} className="text-sm text-muted hover:text-ink">
            Se déconnecter
          </button>
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
              <p className="text-sm text-muted">
                Votre diagnostic 360° n'a pas encore commencé. Votre conseiller vous guidera pour répondre au questionnaire ; votre
                score et votre niveau de maturité s'afficheront ici.
              </p>
            </Card>

            <Card title="Que dois-je faire maintenant ?">
              <p className="text-sm text-muted">
                Rien pour le moment. Vos prochaines actions (3 au maximum), avec le pourquoi, le comment et le document à fournir,
                apparaîtront ici.
              </p>
            </Card>

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

            <Card title="Mes prochaines échéances">
              <p className="text-sm text-muted">Aucune échéance pour le moment.</p>
            </Card>
          </>
        ) : (
          <Alert tone="warning">Aucune entreprise n'est associée à votre compte.</Alert>
        )}
      </main>
    </div>
  );
}
