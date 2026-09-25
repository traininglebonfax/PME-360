"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { Questionnaire } from "@/components/diagnostic/Questionnaire";
import { ButtonLink, LoadingBlock } from "@/components/ui";
import { api, unwrap } from "@/lib/api";
import { DIAGNOSTIC_TYPE_LABELS } from "@/lib/scoring";
import { hasPermission, useMe } from "@/lib/session";

export default function DiagnosticQuestionnairePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: me } = useMe();
  const diagnostic = useQuery({
    queryKey: ["diagnostic", id],
    queryFn: () => unwrap(api.GET("/api/v1/diagnostics/{diagnostic_id}", { params: { path: { diagnostic_id: id } } })),
  });
  if (diagnostic.isLoading || !diagnostic.data) return <LoadingBlock />;
  const data = diagnostic.data;
  const canReview = hasPermission(me, "diagnostic.validate");

  return (
    <>
      <nav className="mb-2 text-sm text-muted">
        <Link href="/pme" className="hover:text-brand-700">
          PME
        </Link>{" "}
        /{" "}
        <Link href={`/pme/${data.pme.id}`} className="hover:text-brand-700">
          {data.pme.name}
        </Link>{" "}
        / {DIAGNOSTIC_TYPE_LABELS[data.type]}
      </nav>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Questionnaire du diagnostic 360°</h1>
        {canReview && data.status === "EN_REVUE" && <ButtonLink href={`/diagnostics/${id}/revue`}>Revue et validation</ButtonLink>}
      </div>
      <Questionnaire diagnosticId={id} onSubmitted={() => canReview && router.push(`/diagnostics/${id}/revue`)} />
    </>
  );
}
