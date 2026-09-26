"use client";

/**
 * Analyses de portefeuille (Document 9, § 4.2) : problèmes fréquents, besoins d'accompagnement, secteurs en
 * difficulté, trajectoires, accompagnement renforcé, évolutions observées par offre. Aucune attribution causale
 * (RM-09) : les évolutions sont décrites, avec leurs effectifs.
 */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { BarList } from "@/components/BarList";
import { Heatmap } from "@/components/charts/Charts";
import { Alert, Badge, Card, EmptyState, LoadingBlock, PageHeader } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import type { PortfolioAnalyses, ShareRow } from "@/lib/dashboards";
import { formatDateTime } from "@/lib/format";
import { DIMENSIONS } from "@/lib/plans";
import { formatPercent, formatScore } from "@/lib/scoring";

function signed(value: number | null, digits = 1): string {
  if (value === null) return "—";
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(digits).replace(".", ",")}`;
}

export default function AnalysesPage() {
  const analyses = useQuery({
    queryKey: ["dashboard", "analyses"],
    queryFn: async () => (await unwrap(api.GET("/api/v1/dashboards/portfolio/analyses"))) as unknown as PortfolioAnalyses,
  });
  if (analyses.isLoading) return <LoadingBlock />;
  if (analyses.error) return <Alert>{errorMessage(analyses.error)}</Alert>;
  const data = analyses.data!;
  const problems = data.frequent_problems;

  return (
    <>
      <PageHeader
        title="Analyses de portefeuille"
        subtitle={`Évolutions observées chez les PME du périmètre${data.refreshed_at ? ` · données au ${formatDateTime(data.refreshed_at)}` : ""}.`}
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Quels problèmes sont les plus fréquents ?">
          <p className="mb-3 text-xs text-muted">Part des PME diagnostiquées dont la dimension est sous {problems.threshold}/100.</p>
          <ShareBars rows={problems.dimensions} />
          {problems.criteria.length > 0 && (
            <>
              <h3 className="mb-2 mt-5 text-sm font-medium">Critères le plus souvent au niveau 0 ou 1</h3>
              <table className="w-full text-sm">
                <tbody className="divide-y divide-line">
                  {problems.criteria.map((c) => (
                    <tr key={c.code}>
                      <td className="py-1.5 pr-2">
                        <span className="font-mono text-xs text-muted">{c.code}</span> {c.name}
                      </td>
                      <td className="py-1.5 text-right tabular-nums text-muted">
                        {c.weak}/{c.evaluated} PME
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </Card>

        <Card title="Quels accompagnements sont les plus demandés ?">
          <p className="mb-3 text-xs text-muted">PME pour lesquelles l'offre a été retenue (recommandation acceptée ou mise au plan).</p>
          <BarList
            items={data.demanded_offers.map((o) => ({ key: o.code, label: `${o.title} (${DIMENSIONS[o.dimension] ?? o.dimension})`, count: o.pmes }))}
            emptyLabel="Aucune recommandation retenue pour l'instant."
          />
        </Card>

        <Card title="Quels secteurs présentent les plus fortes difficultés ?" className="lg:col-span-2">
          <p className="mb-3 text-xs text-muted">
            Score moyen par secteur et par dimension. Une cellule est masquée quand elle compte moins de {data.sector_heatmap.min_cell} PME (protection
            des données et fiabilité).
          </p>
          <Heatmap data={data.sector_heatmap} />
        </Card>

        <Card title="Quelles PME progressent ou stagnent ?">
          <p className="mb-3 text-xs text-muted">
            Écart entre le diagnostic initial et le dernier diagnostic validé ({data.trajectories.measured} PME avec au moins deux diagnostics).
          </p>
          <BarList items={data.trajectories.distribution.map((d) => ({ key: d.label, label: d.label, count: d.count }))} />
          <h3 className="mb-2 mt-5 text-sm font-medium">Plus fortes progressions</h3>
          <Rows rows={data.trajectories.top} empty="Pas encore de diagnostic de suivi." />
          <h3 className="mb-2 mt-4 text-sm font-medium">Stagnation (6 mois, moins de +2 points)</h3>
          <Rows rows={data.trajectories.stagnating} empty="Aucune PME en stagnation." />
        </Card>

        <Card title="Quelles PME nécessitent un accompagnement renforcé ?">
          {data.reinforced_support.length === 0 ? (
            <EmptyState title="Aucune PME en priorité P1 ou P2" />
          ) : (
            <ul className="divide-y divide-line text-sm">
              {data.reinforced_support.map((p) => (
                <li key={p.pme_id} className="flex items-start justify-between gap-3 py-2">
                  <div>
                    <Link href={`/pme/${p.pme_id}?onglet=diagnostic`} className="font-medium text-ink hover:text-brand-700">
                      {p.pme_name}
                    </Link>
                    <p className="text-xs text-muted">
                      {p.reason ?? "Règle de priorité"} · score {formatScore(p.global_score)} · risque {formatScore(p.risk_index)}
                      {p.actions_overdue > 0 && ` · ${p.actions_overdue} action(s) en retard`}
                      {p.alerts_high > 0 && ` · ${p.alerts_high} alerte(s) élevée(s)`}
                    </p>
                  </div>
                  <Badge tone={p.priority === "P1" ? "danger" : "warning"}>{p.priority}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Évolutions observées par accompagnement" className="lg:col-span-2">
          <Alert tone="info">{data.offer_effectiveness.notice}</Alert>
          {data.offer_effectiveness.offers.length === 0 ? (
            <p className="mt-3 text-sm text-muted">Aucune action terminée pour l'instant : rien à comparer.</p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs text-muted">
                  <tr>
                    <th className="py-2 pr-4">Accompagnement</th>
                    <th className="py-2 pr-4">Critères suivis</th>
                    <th className="py-2 pr-4 text-right">PME l'ayant terminé</th>
                    <th className="py-2 pr-4 text-right">Évolution moyenne</th>
                    <th className="py-2 pr-4 text-right">PME éligibles sans l'offre</th>
                    <th className="py-2 text-right">Évolution moyenne</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {data.offer_effectiveness.offers.map((o) => (
                    <tr key={o.code}>
                      <td className="py-2 pr-4">{o.title}</td>
                      <td className="py-2 pr-4 text-xs text-muted">{o.criteria.join(", ")}</td>
                      <td className="py-2 pr-4 text-right tabular-nums">{o.treated_n}</td>
                      <td className="py-2 pr-4 text-right tabular-nums">{signed(o.treated_delta, 2)}</td>
                      <td className="py-2 pr-4 text-right tabular-nums">{o.compared_n}</td>
                      <td className="py-2 text-right tabular-nums">{signed(o.compared_delta, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-xs text-muted">Évolution en {data.offer_effectiveness.unit}, entre le diagnostic initial et la situation courante. Effectifs faibles : à lire avec prudence.</p>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

function ShareBars({ rows }: { rows: ShareRow[] }) {
  if (rows.length === 0) return <p className="text-sm text-muted">Aucun diagnostic validé.</p>;
  return (
    <ul className="space-y-2.5">
      {rows.map((row) => (
        <li key={row.code} title={`${row.weak} PME sur ${row.evaluated}`}>
          <div className="flex justify-between gap-3 text-sm">
            <span className="text-ink">{row.name}</span>
            <span className="font-medium tabular-nums">
              {formatPercent(row.share)} <span className="text-xs font-normal text-muted">({row.weak}/{row.evaluated})</span>
            </span>
          </div>
          <div className="mt-1 h-2 rounded-full bg-gray-100" aria-hidden="true">
            <div className="h-2 rounded-full bg-brand-600" style={{ width: `${Math.max(row.share * 100, row.share ? 2 : 0)}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function Rows({ rows, empty }: { rows: PortfolioAnalyses["trajectories"]["top"]; empty: string }) {
  if (rows.length === 0) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ul className="space-y-1.5 text-sm">
      {rows.map((row) => (
        <li key={row.pme_id} className="flex justify-between gap-2">
          <Link href={`/pme/${row.pme_id}?onglet=diagnostic`} className="truncate text-ink hover:text-brand-700">
            {row.pme_name}
          </Link>
          <span className="shrink-0 tabular-nums text-muted">
            {formatScore(row.from)} → {formatScore(row.to)} ({signed(row.delta)}) · {row.months} mois
          </span>
        </li>
      ))}
    </ul>
  );
}
