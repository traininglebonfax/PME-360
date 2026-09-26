"use client";

/**
 * Tableau du portefeuille (Document 9, § 3) : PME · secteur · niveau · score (+ tendance 6 mois) · confiance ·
 * conformité · risque · priorité · actions en retard · dernière activité ; filtres, export CSV, et nuage
 * « Maturité × Performance ».
 */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { QuadrantScatter } from "@/components/charts/Charts";
import { Alert, Badge, Card, LoadingBlock, PageHeader, SelectInput, TextInput } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import type { PortfolioDashboard, PortfolioRow } from "@/lib/dashboards";
import { formatRelative } from "@/lib/format";
import { formatPercent, formatScore, PRIORITY_LABELS } from "@/lib/scoring";
import { hasPermission, useMe } from "@/lib/session";

type SortKey = "legal_name" | "current_score" | "risk_index" | "actions_overdue" | "compliance_rate";

export default function PortfolioPage() {
  const { data: me } = useMe();
  const rows = useQuery({
    queryKey: ["dashboard", "portfolio-rows"],
    queryFn: async () => (await unwrap(api.GET("/api/v1/dashboards/portfolio/pmes"))) as unknown as PortfolioRow[],
  });
  const overview = useQuery({
    queryKey: ["dashboard", "portfolio"],
    queryFn: async () => (await unwrap(api.GET("/api/v1/dashboards/portfolio"))) as unknown as PortfolioDashboard,
    enabled: hasPermission(me, "dashboard.portfolio"),
  });
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState("");
  const [priority, setPriority] = useState("");
  const [lateOnly, setLateOnly] = useState(false);
  const [sort, setSort] = useState<SortKey>("legal_name");

  const sectors = useMemo(() => [...new Set((rows.data ?? []).map((r) => r.sector_name).filter(Boolean))] as string[], [rows.data]);
  const filtered = useMemo(() => {
    const list = (rows.data ?? []).filter(
      (r) =>
        (!search || r.legal_name.toLowerCase().includes(search.toLowerCase())) &&
        (!sector || r.sector_name === sector) &&
        (!priority || r.intervention_priority === priority) &&
        (!lateOnly || r.actions_overdue > 0),
    );
    return [...list].sort((a, b) => {
      if (sort === "legal_name") return a.legal_name.localeCompare(b.legal_name, "fr");
      const av = a[sort] ?? -1;
      const bv = b[sort] ?? -1;
      return sort === "current_score" || sort === "compliance_rate" ? av - bv : bv - av;
    });
  }, [rows.data, search, sector, priority, lateOnly, sort]);

  if (rows.isLoading) return <LoadingBlock />;
  if (rows.error) return <Alert>{errorMessage(rows.error)}</Alert>;
  const thresholds = overview.data?.quadrant_thresholds ?? { imo_threshold: 55, ipe_threshold: 60 };
  const points = filtered
    .filter((r) => r.imo !== null && r.ipe !== null)
    .map((r) => ({ id: r.pme_id, label: r.legal_name, x: r.imo!, y: r.ipe!, href: `/pme/${r.pme_id}?onglet=diagnostic` }));

  return (
    <>
      <PageHeader
        title="Tableau du portefeuille"
        subtitle={`${filtered.length} PME affichée(s) sur ${rows.data!.length}.`}
        actions={
          <a href="/api/v1/dashboards/portfolio/pmes?export=csv" className="rounded-lg border border-line bg-white px-3 py-2 text-sm font-medium text-ink hover:bg-gray-50">
            Exporter en CSV
          </a>
        }
      />
      <div className="mb-4 grid gap-3 rounded-xl border border-line bg-white p-3 sm:grid-cols-2 lg:grid-cols-5">
        <TextInput label="Rechercher" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nom de la PME" />
        <SelectInput label="Secteur" value={sector} onChange={(e) => setSector(e.target.value)} placeholder="Tous" options={sectors.map((s) => ({ value: s, label: s }))} />
        <SelectInput
          label="Priorité"
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
          placeholder="Toutes"
          options={["P1", "P2", "P3", "P4"].map((p) => ({ value: p, label: `${p} · ${PRIORITY_LABELS[p]}` }))}
        />
        <SelectInput
          label="Trier par"
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          placeholder="—"
          options={[
            { value: "legal_name", label: "Nom" },
            { value: "current_score", label: "Score (plus faible d'abord)" },
            { value: "risk_index", label: "Risque (plus élevé d'abord)" },
            { value: "actions_overdue", label: "Actions en retard" },
            { value: "compliance_rate", label: "Conformité (plus faible d'abord)" },
          ]}
        />
        <label className="flex items-end gap-2 pb-2.5 text-sm">
          <input type="checkbox" className="accent-brand-600" checked={lateOnly} onChange={(e) => setLateOnly(e.target.checked)} />
          Actions en retard seulement
        </label>
      </div>

      <div className="overflow-x-auto rounded-xl border border-line bg-white">
        <table className="min-w-full divide-y divide-line text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-3 py-2">PME</th>
              <th className="px-3 py-2">Secteur</th>
              <th className="px-3 py-2">Niveau</th>
              <th className="px-3 py-2 text-right">Score</th>
              <th className="px-3 py-2 text-right">6 mois</th>
              <th className="px-3 py-2 text-right">Confiance</th>
              <th className="px-3 py-2 text-right">Conformité</th>
              <th className="px-3 py-2 text-right">Risque</th>
              <th className="px-3 py-2">Priorité</th>
              <th className="px-3 py-2 text-right">Retards</th>
              <th className="px-3 py-2">Activité</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {filtered.map((r) => (
              <tr key={r.pme_id} className="hover:bg-gray-50">
                <td className="px-3 py-2">
                  <Link href={`/pme/${r.pme_id}`} className="font-medium text-ink hover:text-brand-700">
                    {r.legal_name}
                  </Link>
                </td>
                <td className="px-3 py-2 text-muted">{r.sector_name ?? "—"}</td>
                <td className="px-3 py-2">{r.maturity_level ? `N${r.maturity_level}` : "—"}</td>
                <td className="px-3 py-2 text-right font-medium tabular-nums">{formatScore(r.current_score)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-muted">
                  {r.trend_6m === null ? "—" : `${r.trend_6m >= 0 ? "+" : "−"}${Math.abs(r.trend_6m).toFixed(1).replace(".", ",")}`}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{r.confidence === null ? "—" : formatPercent(r.confidence)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{r.compliance_rate === null ? "—" : formatPercent(r.compliance_rate)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatScore(r.risk_index)}</td>
                <td className="px-3 py-2">
                  {r.intervention_priority ? <Badge tone={r.intervention_priority === "P1" ? "danger" : r.intervention_priority === "P2" ? "warning" : "neutral"}>{r.intervention_priority}</Badge> : "—"}
                </td>
                <td className={`px-3 py-2 text-right tabular-nums ${r.actions_overdue ? "font-medium text-red-700" : "text-muted"}`}>{r.actions_overdue}</td>
                <td className="px-3 py-2 text-muted">{formatRelative(r.last_activity_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Card title="Maturité × performance" className="mt-6">
        <p className="mb-3 text-xs text-muted">
          Chaque point est une PME diagnostiquée. Les lignes pointillées marquent les seuils des quadrants (maturité {thresholds.imo_threshold}, performance{" "}
          {thresholds.ipe_threshold}).
        </p>
        <QuadrantScatter points={points} xThreshold={thresholds.imo_threshold} yThreshold={thresholds.ipe_threshold} />
      </Card>
    </>
  );
}
