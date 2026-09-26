"use client";

/**
 * Référentiel de diagnostic versionné (Document 5 ; ADR-004) : consultation, clonage en brouillon, édition sans code
 * du brouillon (V1 : dimensions, critères, questions, pondérations) et publication. Une version publiée est immuable.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { FrameworkEditor } from "@/components/framework/FrameworkEditor";
import { Alert, Badge, Button, Card, cx, LoadingBlock, PageHeader, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, unwrap } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { LENS_LABELS } from "@/lib/scoring";
import { hasPermission, useMe } from "@/lib/session";

const STATUS_TONES = { PUBLISHED: "brand", DRAFT: "warning", RETIRED: "muted" } as const;
const STATUS_LABELS = { PUBLISHED: "Publiée", DRAFT: "Brouillon", RETIRED: "Retirée" } as const;
const EVIDENCE_LABELS: Record<string, string> = { NONE: "—", RECOMMENDED: "Recommandée", REQUIRED: "Obligatoire" };

export default function FrameworkPage() {
  const { data: me } = useMe();
  const queryClient = useQueryClient();
  const canConfigure = hasPermission(me, "org.configure");
  const versions = useQuery({ queryKey: ["framework-versions"], queryFn: () => unwrap(api.GET("/api/v1/framework-versions")) });
  const [selected, setSelected] = useState<string | null>(null);
  const current = selected ?? versions.data?.find((v) => v.status === "PUBLISHED")?.id ?? versions.data?.[0]?.id;
  const detail = useQuery({
    queryKey: ["framework-version", current],
    queryFn: () => unwrap(api.GET("/api/v1/framework-versions/{version_id}", { params: { path: { version_id: current! } } })),
    enabled: Boolean(current),
  });
  const [newVersion, setNewVersion] = useState("");
  const [openDimension, setOpenDimension] = useState<string | null>(null);
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["framework-versions"] });
    queryClient.invalidateQueries({ queryKey: ["framework-version", current] });
    queryClient.invalidateQueries({ queryKey: ["framework-editor", current] });
  };
  const clone = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/api/v1/framework-versions/{version_id}/clone", { params: { path: { version_id: current! } }, body: { version: newVersion } })),
    onSuccess: (draft) => {
      setNewVersion("");
      setSelected(draft.id);
      refresh();
    },
  });
  const publish = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/framework-versions/{version_id}/publish", { params: { path: { version_id: current! } } })),
    onSuccess: refresh,
  });

  if (versions.isLoading) return <LoadingBlock />;
  if (versions.error) return <Alert>{errorMessage(versions.error)}</Alert>;
  const version = detail.data;
  const editing = canConfigure && version?.status === "DRAFT" && version.id === current;
  const publishErrors = publish.error instanceof ApiError ? Object.values(publish.error.fieldErrors()) : [];

  return (
    <>
      <PageHeader title="Référentiel de diagnostic" subtitle="Dimensions, critères, pondérations, grilles et indicateurs utilisés par le moteur de scoring" />
      <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
        <aside className="space-y-4">
          <Card title="Versions">
            <ul className="space-y-1">
              {versions.data!.map((v) => (
                <li key={v.id}>
                  <button
                    onClick={() => setSelected(v.id)}
                    className={cx("flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm", v.id === current ? "bg-brand-50 font-medium" : "hover:bg-gray-50")}
                  >
                    <span>
                      {v.framework_code} v{v.version}
                    </span>
                    <Badge tone={STATUS_TONES[v.status]}>{STATUS_LABELS[v.status]}</Badge>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          {canConfigure && version && (
            <Card title="Gestion">
              <form
                className="space-y-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  clone.mutate();
                }}
              >
                <TextInput label="Nouvelle version (brouillon)" placeholder="1.1.0" pattern="\d+\.\d+\.\d+" value={newVersion} onChange={(e) => setNewVersion(e.target.value)} required />
                <Button type="submit" variant="secondary" className="w-full" loading={clone.isPending}>
                  Créer un brouillon à partir de v{version.version}
                </Button>
                {clone.error && <Alert>{errorMessage(clone.error)}</Alert>}
              </form>
              {version.status === "DRAFT" && (
                <div className="mt-4 border-t border-line pt-4">
                  <Button className="w-full" loading={publish.isPending} onClick={() => publish.mutate()}>
                    Publier v{version.version}
                  </Button>
                  <p className="mt-1 text-xs text-muted">La version publiée remplace l'actuelle pour les nouveaux diagnostics ; elle devient immuable.</p>
                  {publishErrors.length > 0 && (
                    <div className="mt-2">
                      <Alert title="Publication impossible">
                        <ul className="list-disc pl-4">
                          {publishErrors.flatMap((e) => e.split(/(?<=\.) /)).map((e, i) => (
                            <li key={i}>{e}</li>
                          ))}
                        </ul>
                      </Alert>
                    </div>
                  )}
                </div>
              )}
            </Card>
          )}
        </aside>

        <section>
          {!version ? (
            <LoadingBlock />
          ) : editing ? (
            <FrameworkEditor
              versionId={version.id}
              onDeleted={() => {
                setSelected(null);
                queryClient.invalidateQueries({ queryKey: ["framework-versions"] });
              }}
            />
          ) : (
            <div className="space-y-4">
              <Card>
                <p className="text-sm text-muted">
                  {version.framework_name} · version {version.version} · {STATUS_LABELS[version.status]}
                  {version.published_at && ` le ${formatDate(version.published_at)}`}
                </p>
                {version.notes && <p className="mt-1 text-sm text-ink">{version.notes}</p>}
                <div className="mt-3 flex flex-wrap gap-2">
                  {version.pillars.map((p) => (
                    <Badge key={p.code} tone="neutral">
                      Pilier {p.code} · {p.name} · {Number(p.weight)} pts
                    </Badge>
                  ))}
                </div>
              </Card>
              {version.dimensions.map((dimension) => (
                <Card
                  key={dimension.code}
                  title={`${dimension.code} · ${dimension.name}`}
                  action={
                    <button className="text-sm text-brand-700 hover:underline" onClick={() => setOpenDimension(openDimension === dimension.code ? null : dimension.code)}>
                      {Number(dimension.weight)} pts · {dimension.criteria.length} critères {openDimension === dimension.code ? "▲" : "▼"}
                    </button>
                  }
                >
                  <p className="text-sm text-muted">{dimension.description}</p>
                  {openDimension === dimension.code && (
                    <div className="mt-4 overflow-x-auto">
                      <table className="min-w-full divide-y divide-line text-sm">
                        <thead className="text-left text-xs uppercase tracking-wide text-muted">
                          <tr>
                            <th className="py-2 pr-3">Critère</th>
                            <th className="py-2 pr-3">Lentille</th>
                            <th className="py-2 pr-3 text-right">Poids</th>
                            <th className="py-2 pr-3">Preuve</th>
                            <th className="py-2">Calcul</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-line align-top">
                          {dimension.criteria.map((criterion) => (
                            <tr key={criterion.code}>
                              <td className="py-2 pr-3">
                                <span className="font-mono text-xs text-muted">{criterion.code}</span> {criterion.name}
                                <div className="mt-1 flex flex-wrap gap-1">
                                  {criterion.is_critical && <Badge tone="warning">Critique</Badge>}
                                  {criterion.sector_module && <Badge tone="info">Module {criterion.sector_module}</Badge>}
                                  {Boolean(criterion.applicability) && <Badge tone="muted">Conditionnel</Badge>}
                                </div>
                              </td>
                              <td className="py-2 pr-3 text-muted">{LENS_LABELS[criterion.lens]}</td>
                              <td className="py-2 pr-3 text-right tabular-nums">{Number(criterion.weight)}</td>
                              <td className="py-2 pr-3 text-muted">
                                {EVIDENCE_LABELS[criterion.evidence_policy]}
                                {criterion.evidence_document_types.length > 0 && (
                                  <div className="text-xs">{criterion.evidence_document_types.join(", ")}</div>
                                )}
                              </td>
                              <td className="py-2 text-xs text-muted">
                                {criterion.metrics.length
                                  ? criterion.metrics.map((m) => (
                                      <div key={m.code}>
                                        {m.name} = {m.formula_label}
                                      </div>
                                    ))
                                  : "Grille 0 à 4"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Card>
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  );
}
