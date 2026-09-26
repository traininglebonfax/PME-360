"use client";

import { useBrand } from "@/lib/brand";

/** Nom court de l'organisation connectée (marque blanche) ; ``fallback`` si l'organisation n'en a pas. */
export function OrgName({ fallback = "l'équipe" }: { fallback?: string }) {
  const brand = useBrand();
  return <>{brand.short_name || fallback}</>;
}
