"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { api, ApiError, type Schemas, unwrap } from "./api";

export type Me = Schemas["Me"];

export const ME_KEY = ["me"] as const;

/** Utilisateur connecté (null si non authentifié). */
export function useMe() {
  return useQuery<Me | null>({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return await unwrap(api.GET("/api/v1/me"));
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function hasPermission(me: Me | null | undefined, code: string): boolean {
  return Boolean(me?.permissions.includes(code));
}

/** Page d'accueil selon le portail de l'utilisateur. */
export function homeFor(me: Me): string {
  if (me.portal === "pme") return "/espace";
  if (me.portal === "platform") return "/plateforme";
  if (me.portal === "none") return "/connexion?raison=aucune-organisation";
  return "/tableau-de-bord";
}

export function useLogout() {
  const queryClient = useQueryClient();
  const router = useRouter();
  return async () => {
    await api.POST("/api/v1/auth/logout");
    queryClient.clear();
    router.replace("/connexion");
  };
}
