"use client";

/**
 * Accompagnement (Document 7, § 3 et § 7) : catalogue d'offres, bibliothèque de livrables, règles de
 * recommandation versionnées. Une règle active n'est jamais modifiée : on crée une version, on la teste sur le
 * portefeuille, puis on l'active.
 */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { RulesPanel } from "@/components/plans/RulesPanel";
import { Alert, Badge, Card, cx, LoadingBlock, PageHeader } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import { DIMENSIONS, formatCost } from "@/lib/plans";
import { OrgName } from "@/components/OrgName";

type Tab = "regles" | "offres" | "livrables";

export default function SupportPage() {
  const [tab, setTab] = useState<Tab>("regles");
  return (
    <>
      <PageHeader
        title="Accompagnement"
        subtitle="Règles de recommandation, offres d'accompagnement et modèles de livrables de votre organisation."
      />
      <div className="mb-6 flex gap-1 border-b border-line" role="tablist">
        {(
          [
            ["regles", "Règles"],
            ["offres", "Offres"],
            ["livrables", "Modèles de livrables"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cx(
              "border-b-2 px-3 py-2.5 text-sm",
              tab === key ? "border-brand-600 font-medium text-brand-800" : "border-transparent text-muted hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "regles" && <RulesPanel />}
      {tab === "offres" && <Offers />}
      {tab === "livrables" && <Templates />}
    </>
  );
}

function Offers() {
  const offers = useQuery({ queryKey: ["support-offers"], queryFn: () => unwrap(api.GET("/api/v1/support-offers")) });
  if (offers.isLoading) return <LoadingBlock />;
  if (offers.error) return <Alert>{errorMessage(offers.error)}</Alert>;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {offers.data!.map((offer) => (
        <Card key={offer.id} title={offer.title} action={<Badge tone="muted">{DIMENSIONS[offer.dimension_code] ?? offer.dimension_code}</Badge>}>
          <p className="text-sm text-ink">{offer.objective}</p>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div>
              <dt className="text-muted">Durée type</dt>
              <dd>{offer.typical_duration_days} jours · effort {offer.effort}/5</dd>
            </div>
            <div>
              <dt className="text-muted">Réussite</dt>
              <dd>{offer.success_indicator}</dd>
            </div>
            <div>
              <dt className="text-muted">Coût estimatif</dt>
              <dd>{formatCost(offer.estimated_cost_min, offer.estimated_cost_max)}</dd>
            </div>
            <div>
              <dt className="text-muted">Prérequis</dt>
              <dd>{(offer.depends_on as string[]).join(", ") || "—"}</dd>
            </div>
          </dl>
          <p className="mt-2 text-xs text-muted">
            <span className="font-mono">{offer.code}</span> · étapes : {(offer.sub_actions as string[]).join(" → ")}
          </p>
        </Card>
      ))}
    </div>
  );
}

function Templates() {
  const templates = useQuery({ queryKey: ["deliverable-templates"], queryFn: () => unwrap(api.GET("/api/v1/deliverable-templates")) });
  if (templates.isLoading) return <LoadingBlock />;
  if (templates.error) return <Alert>{errorMessage(templates.error)}</Alert>;
  return (
    <Card>
      <p className="mb-3 text-sm text-muted">
        Chaque modèle donne des instructions en langage simple et les points que le conseiller vérifie. Les fichiers modèles (docx, xlsx) seront
        fournis par <OrgName />.
      </p>
      <ul className="divide-y divide-line">
        {templates.data!.map((template) => (
          <li key={template.id} className="py-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-medium">{template.title}</p>
              <span className="text-xs text-muted">
                {template.category} · {template.format} · déposé comme <span className="font-mono">{template.document_type_code}</span>
              </span>
            </div>
            <p className="mt-1 text-muted">{template.instructions}</p>
            <p className="mt-1 text-xs text-muted">Vérifié : {(template.verification_criteria as string[]).join(" · ")}</p>
          </li>
        ))}
      </ul>
    </Card>
  );
}
