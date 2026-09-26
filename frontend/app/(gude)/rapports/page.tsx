"use client";

/**
 * Rapports trimestriels de portefeuille (Document 9, § 7) : direction GUDE-PME et bailleurs. Anonymisés par défaut ;
 * chaque édition est figée et archivée, une réédition crée une nouvelle version. Une édition automatique est produite
 * au début de chaque trimestre pour le trimestre écoulé.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { Alert, Badge, Button, Card, EmptyState, LoadingBlock, PageHeader, SelectInput } from "@/components/ui";
import { api, errorMessage, type Schemas, unwrap } from "@/lib/api";
import { formatSize } from "@/lib/documents";
import { formatDateTime } from "@/lib/format";
import { hasPermission, useMe } from "@/lib/session";

/** Trimestres proposés : le trimestre en cours et les sept précédents. */
function quarters(today = new Date()): { value: string; label: string }[] {
  const items = [];
  let year = today.getFullYear();
  let quarter = Math.floor(today.getMonth() / 3) + 1;
  for (let i = 0; i < 8; i++) {
    items.push({ value: `${year}-T${quarter}`, label: `${quarter === 1 ? "1er" : `${quarter}e`} trimestre ${year}${i === 0 ? " (en cours)" : ""}` });
    quarter -= 1;
    if (quarter === 0) {
      quarter = 4;
      year -= 1;
    }
  }
  return items;
}

export default function PortfolioReportsPage() {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const options = useMemo(() => quarters(), []);
  const [period, setPeriod] = useState(options[1].value);
  const [scope, setScope] = useState("");
  const [includeNames, setIncludeNames] = useState(false);
  const reports = useQuery({ queryKey: ["portfolio-reports"], queryFn: () => unwrap(api.GET("/api/v1/reports/portfolio")) });
  const programmes = useQuery({
    queryKey: ["programmes"],
    queryFn: async () => {
      const { data, response } = await api.GET("/api/v1/programmes");
      if (!response.ok) return [] as Schemas["Programme"][];
      return (Array.isArray(data) ? data : ((data as unknown as { results?: Schemas["Programme"][] })?.results ?? [])) as Schemas["Programme"][];
    },
  });
  const scopes = (programmes.data ?? []).flatMap((p) => [
    { value: `programme:${p.id}`, label: `Programme ${p.name}` },
    ...p.cohorts.map((c) => ({ value: `cohort:${c.id}`, label: `— Cohorte ${c.name}` })),
  ]);
  const generate = useMutation({
    mutationFn: () => {
      const [kind, id] = scope.split(":");
      return unwrap(
        api.POST("/api/v1/reports/portfolio", {
          body: {
            period,
            include_names: includeNames,
            programme_id: kind === "programme" ? id : null,
            cohort_id: kind === "cohort" ? id : null,
          },
        }),
      );
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["portfolio-reports"] }),
  });
  const canGenerate = hasPermission(me, "report.generate");

  return (
    <>
      <PageHeader
        title="Rapports de portefeuille"
        subtitle="Rapport trimestriel pour la direction et les bailleurs : PME accompagnées, évolution des scores, problèmes, besoins, actions, pilotage."
      />
      <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
        {canGenerate && (
          <Card title="Éditer un rapport">
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                generate.mutate();
              }}
            >
              <SelectInput label="Trimestre" value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="—" options={options} />
              <SelectInput label="Périmètre" value={scope} onChange={(e) => setScope(e.target.value)} placeholder="Tout mon portefeuille" options={scopes} />
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-0.5 accent-brand-600" checked={includeNames} onChange={(e) => setIncludeNames(e.target.checked)} />
                <span>
                  Citer les PME nommément
                  <span className="block text-xs text-muted">Diffusion interne uniquement. Sans cette option, le rapport est anonymisé et diffusable aux partenaires.</span>
                </span>
              </label>
              <Button type="submit" className="w-full" loading={generate.isPending}>
                Éditer le rapport
              </Button>
              {generate.error && <Alert>{errorMessage(generate.error)}</Alert>}
              <p className="text-xs text-muted">
                Les données sont figées à l'édition ; rééditer crée une nouvelle version. Une édition anonymisée de toute l'organisation est aussi produite
                automatiquement au début de chaque trimestre.
              </p>
            </form>
          </Card>
        )}

        <Card title="Éditions">
          {reports.isLoading ? (
            <LoadingBlock />
          ) : reports.error ? (
            <Alert>{errorMessage(reports.error)}</Alert>
          ) : reports.data!.length === 0 ? (
            <EmptyState title="Aucun rapport">Éditez un premier rapport de portefeuille.</EmptyState>
          ) : (
            <ul className="divide-y divide-line" aria-label="Rapports de portefeuille">
              {reports.data!.map((report) => (
                <li key={report.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
                  <div>
                    <p className="font-medium text-ink">
                      {report.period} · {report.scope_label} <Badge tone="muted">v{report.version}</Badge>{" "}
                      {report.include_names ? <Badge tone="warning">Nominatif — interne</Badge> : <Badge tone="brand">Anonymisé</Badge>}
                    </p>
                    <p className="text-xs text-muted">
                      {report.pme_count} PME · édité le {formatDateTime(report.generated_at)}
                      {report.generated_by_name ? ` par ${report.generated_by_name}` : " automatiquement"} · {formatSize(report.size_bytes)}
                    </p>
                  </div>
                  <a
                    href={`/api/v1/reports/${report.id}/pdf`}
                    download
                    className="rounded-lg border border-brand-600 px-3 py-1.5 text-sm font-medium text-brand-700 hover:bg-brand-50"
                  >
                    Télécharger le PDF
                  </a>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
