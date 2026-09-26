"use client";

/**
 * Workflow d'action en vigueur (configuré par l'organisation, V1) : libellés des états pour l'équipe et pour la
 * PME. Les tons de badge restent ceux du code ; en attendant le chargement, les libellés par défaut s'affichent.
 */
import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";

import { api, unwrap } from "./api";
import { ACTION_STATUS, type ActionStatus } from "./plans";

export function useActionWorkflow() {
  return useQuery({
    queryKey: ["workflow", "action"],
    queryFn: () => unwrap(api.GET("/api/v1/workflows/{target}", { params: { path: { target: "action" } } })),
    staleTime: 5 * 60_000,
  });
}

/** ``statusOf(code)`` → { label, pme, tone } selon le workflow actif. */
export function useActionStatus() {
  const workflow = useActionWorkflow();
  const states = workflow.data?.states;
  return useCallback(
    (status: string) => {
      const base = ACTION_STATUS[status as ActionStatus] ?? { label: status, pme: status, tone: "neutral" as const };
      const configured = states?.[status];
      return { ...base, label: configured?.label || base.label, pme: configured?.pme_label || base.pme };
    },
    [states],
  );
}
