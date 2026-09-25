"use client";

import { useQuery } from "@tanstack/react-query";

import { api, type Schemas, unwrap } from "./api";

export type RefKind = "sectors" | "legal-forms" | "regions";

/** Nomenclatures de l'organisation (secteurs, formes juridiques, régions), mises en cache. */
export function useReference(kind: RefKind) {
  return useQuery<Schemas["RefItem"][]>({
    queryKey: ["ref", kind],
    queryFn: () => unwrap(api.GET("/api/v1/ref/{kind}", { params: { path: { kind } } })),
    staleTime: 10 * 60_000,
  });
}

export function toOptions(items: Schemas["RefItem"][] | undefined, value: "id" | "code" = "id") {
  return (items ?? []).map((item) => ({ value: item[value], label: item.name }));
}
