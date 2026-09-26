"use client";

/**
 * Marque blanche (V1) : nom du produit, nom court de l'organisation, couleur principale et logo. La couleur
 * principale génère la palette « brand » (teintes claires et foncées) appliquée en variables CSS ; le titre de
 * l'onglet suit le nom du produit. Par défaut : « PME360 ».
 */
import { useEffect } from "react";

import { type Schemas } from "./api";
import { useMe } from "./session";

export type Brand = Schemas["Brand"];

export const DEFAULT_BRAND: Brand = {
  product_name: "PME360",
  short_name: "",
  primary_color: "#2E4A6B",
  logo: null,
  tagline: "Connaître · Accompagner · Mesurer",
};

/** Identité de l'organisation connectée (identité neutre hors connexion). */
export function useBrand(): Brand {
  const { data: me } = useMe();
  return (me?.organization?.brand as Brand | undefined) ?? DEFAULT_BRAND;
}

/** Nom affiché dans les libellés (« Équipe {nom} ») ; « l'équipe » si l'organisation n'a pas de nom court. */
export function orgLabel(brand: Brand, fallback = "l'équipe"): string {
  return brand.short_name || fallback;
}

function rgb(hex: string): [number, number, number] {
  const value = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16)) as [number, number, number];
}

function mix(hex: string, target: [number, number, number], amount: number): string {
  const [r, g, b] = rgb(hex);
  const channel = (c: number, t: number) => Math.round(c + (t - c) * amount);
  return `#${[channel(r, target[0]), channel(g, target[1]), channel(b, target[2])].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

/** Palette dérivée de la couleur principale (600) : teintes claires vers le blanc, foncées vers le noir. */
export function palette(primary: string): Record<string, string> {
  const white: [number, number, number] = [255, 255, 255];
  const black: [number, number, number] = [0, 0, 0];
  return {
    "50": mix(primary, white, 0.93),
    "100": mix(primary, white, 0.85),
    "200": mix(primary, white, 0.68),
    "500": mix(primary, white, 0.18),
    "600": primary,
    "700": mix(primary, black, 0.18),
    "800": mix(primary, black, 0.36),
  };
}

/** Applique couleurs et titre de l'onglet ; revient à l'identité par défaut au démontage. */
export function useApplyBrand(brand: Brand) {
  useEffect(() => {
    const root = document.documentElement;
    const colors = palette(/^#[0-9a-f]{6}$/i.test(brand.primary_color) ? brand.primary_color : DEFAULT_BRAND.primary_color);
    for (const [step, value] of Object.entries(colors)) root.style.setProperty(`--color-brand-${step}`, value);
    document.title = brand.product_name;
    return () => {
      for (const step of Object.keys(colors)) root.style.removeProperty(`--color-brand-${step}`);
    };
  }, [brand.primary_color, brand.product_name]);
}
