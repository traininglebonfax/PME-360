"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import { LifecycleBadge } from "@/components/LifecycleBadge";
import { Alert, Button, ButtonLink, EmptyState, LoadingBlock, PageHeader, SelectInput, TextInput } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { LIFECYCLE_LABELS, SIZE_LABELS } from "@/lib/labels";
import { toOptions, useReference } from "@/lib/references";
import { hasPermission, useMe } from "@/lib/session";

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export default function PmeListPage() {
  const { data: me } = useMe();
  const sectors = useReference("sectors");
  const regions = useReference("regions");
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState({ sector: "", region: "", lifecycle_status: "", advisor: "", ordering: "legal_name" });
  const q = useDebounced(search);

  const list = useInfiniteQuery({
    queryKey: ["pmes", q, filters],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/pmes", {
          params: {
            query: {
              q: q || undefined,
              sector: filters.sector || undefined,
              region: filters.region || undefined,
              lifecycle_status: filters.lifecycle_status || undefined,
              advisor: filters.advisor || undefined,
              ordering: filters.ordering,
              cursor: pageParam,
            },
          },
        }),
      ),
    getNextPageParam: (last) => (last.next ? new URL(last.next).searchParams.get("cursor") ?? undefined : undefined),
  });

  const rows = list.data?.pages.flatMap((page) => page.results) ?? [];
  const setFilter = (key: keyof typeof filters) => (event: React.ChangeEvent<HTMLSelectElement>) =>
    setFilters((current) => ({ ...current, [key]: event.target.value }));

  return (
    <>
      <PageHeader
        title="PME"
        subtitle="Entreprises de votre périmètre"
        actions={hasPermission(me, "pme.create") && <ButtonLink href="/pme/nouvelle">Nouvelle PME</ButtonLink>}
      />
      <div className="mb-4 grid gap-3 rounded-xl border border-line bg-white p-4 sm:grid-cols-2 lg:grid-cols-6">
        <div className="lg:col-span-2">
          <TextInput label="Recherche" placeholder="Raison sociale, sigle, RCCM, NCC" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <SelectInput label="Secteur" placeholder="Tous" value={filters.sector} onChange={setFilter("sector")} options={toOptions(sectors.data, "code")} />
        <SelectInput label="Région" placeholder="Toutes" value={filters.region} onChange={setFilter("region")} options={toOptions(regions.data, "code")} />
        <SelectInput
          label="Statut"
          placeholder="Tous"
          value={filters.lifecycle_status}
          onChange={setFilter("lifecycle_status")}
          options={Object.entries(LIFECYCLE_LABELS).map(([value, label]) => ({ value, label }))}
        />
        <SelectInput
          label="Suivi"
          placeholder="Tout le périmètre"
          value={filters.advisor}
          onChange={setFilter("advisor")}
          options={[{ value: "me", label: "Mes PME" }]}
        />
      </div>

      {list.isLoading ? (
        <LoadingBlock />
      ) : list.error ? (
        <Alert>{errorMessage(list.error)}</Alert>
      ) : rows.length === 0 ? (
        <EmptyState title="Aucune PME ne correspond">Modifiez la recherche ou les filtres.</EmptyState>
      ) : (
        <div className="overflow-hidden rounded-xl border border-line bg-white">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-sm">
              <thead className="bg-gray-50 text-left text-xs font-medium uppercase tracking-wide text-muted">
                <tr>
                  <th scope="col" className="px-4 py-3">
                    <button onClick={() => setFilters((f) => ({ ...f, ordering: f.ordering === "legal_name" ? "-legal_name" : "legal_name" }))}>
                      Entreprise {filters.ordering === "legal_name" ? "↑" : filters.ordering === "-legal_name" ? "↓" : ""}
                    </button>
                  </th>
                  <th scope="col" className="px-4 py-3">Secteur</th>
                  <th scope="col" className="hidden px-4 py-3 md:table-cell">Localisation</th>
                  <th scope="col" className="hidden px-4 py-3 lg:table-cell">Taille</th>
                  <th scope="col" className="px-4 py-3">Statut</th>
                  <th scope="col" className="hidden px-4 py-3 md:table-cell">Conseiller</th>
                  <th scope="col" className="hidden px-4 py-3 xl:table-cell">Dernière activité</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((pme) => (
                  <tr key={pme.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <Link href={`/pme/${pme.id}`} className="font-medium text-ink hover:text-brand-700">
                        {pme.legal_name}
                      </Link>
                      {pme.rccm_number && <p className="text-xs text-muted">{pme.rccm_number}</p>}
                    </td>
                    <td className="px-4 py-3 text-muted">{pme.sector?.name ?? "—"}</td>
                    <td className="hidden px-4 py-3 text-muted md:table-cell">{[pme.commune, pme.region?.name].filter(Boolean).join(", ") || "—"}</td>
                    <td className="hidden px-4 py-3 text-muted lg:table-cell">{SIZE_LABELS[pme.size_category ?? "NON_DETERMINEE"]}</td>
                    <td className="px-4 py-3">
                      <LifecycleBadge status={pme.lifecycle_status} />
                    </td>
                    <td className="hidden px-4 py-3 text-muted md:table-cell">{pme.principal_advisor?.full_name ?? "Non assigné"}</td>
                    <td className="hidden px-4 py-3 text-muted xl:table-cell">{formatRelative(pme.last_activity_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {list.hasNextPage && (
            <div className="border-t border-line p-3 text-center">
              <Button variant="secondary" loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>
                Afficher plus
              </Button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
