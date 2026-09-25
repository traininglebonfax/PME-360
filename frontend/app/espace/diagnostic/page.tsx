"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { useGuard } from "@/components/AppShell";
import { BrandMark } from "@/components/Brand";
import { Questionnaire } from "@/components/diagnostic/Questionnaire";
import { Alert, LoadingBlock } from "@/components/ui";
import { api, unwrap } from "@/lib/api";
import type { PmeDashboard } from "@/lib/dashboards";

/** Questionnaire du diagnostic, côté PME (questions de la PME uniquement, sans niveaux affichés). */
export default function PmeQuestionnairePage() {
  const { me, isLoading } = useGuard("pme");
  const router = useRouter();
  const pmeId = me?.pme_ids[0];
  const dashboard = useQuery({
    queryKey: ["dashboard", "pme", pmeId],
    queryFn: async () =>
      (await unwrap(api.GET("/api/v1/dashboards/pme/{pme_id}", { params: { path: { pme_id: pmeId! } } }))) as unknown as PmeDashboard,
    enabled: Boolean(pmeId),
  });

  if (isLoading || !me || dashboard.isLoading) return <LoadingBlock />;
  const diagnostic = dashboard.data?.open_diagnostic;

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <Link href="/espace" className="flex items-center gap-2">
            <BrandMark className="h-8 w-8" />
            <span className="font-semibold">Mon espace</span>
          </Link>
          <Link href="/espace" className="text-sm text-muted hover:text-ink">
            ← Retour à l'accueil
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        <h1 className="mb-1 text-xl font-semibold">Diagnostic 360° de votre entreprise</h1>
        <p className="mb-6 text-sm text-muted">
          Répondez simplement et honnêtement : il n'y a pas de mauvaise réponse. Votre conseiller relira vos réponses avec vous.
        </p>
        {diagnostic ? (
          <Questionnaire diagnosticId={diagnostic.id} onSubmitted={() => router.push("/espace")} />
        ) : (
          <Alert tone="info">Aucun questionnaire n'est ouvert pour le moment.</Alert>
        )}
      </main>
    </div>
  );
}
