/** Libellés français des valeurs d'énumération renvoyées par l'API. */
import type { Schemas } from "./api";

type Lifecycle = Schemas["LifecycleStatusEnum"];

export const LIFECYCLE_LABELS: Record<Lifecycle, string> = {
  PROSPECT: "Prospect",
  ONBOARDING: "Intégration",
  DIAGNOSTIC_EN_COURS: "Diagnostic en cours",
  ACCOMPAGNEMENT_ACTIF: "Accompagnement actif",
  SUSPENDU: "Suspendu",
  SORTIE: "Sortie du programme",
  SUIVI_POST_PROGRAMME: "Suivi post-programme",
};

export const LIFECYCLE_TONES: Record<Lifecycle, "neutral" | "info" | "brand" | "warning" | "muted"> = {
  PROSPECT: "neutral",
  ONBOARDING: "info",
  DIAGNOSTIC_EN_COURS: "info",
  ACCOMPAGNEMENT_ACTIF: "brand",
  SUSPENDU: "warning",
  SORTIE: "muted",
  SUIVI_POST_PROGRAMME: "muted",
};

/** Transitions autorisées (miroir de pmes.services.LIFECYCLE_TRANSITIONS ; l'API reste la référence). */
export const LIFECYCLE_NEXT: Record<Lifecycle, Lifecycle[]> = {
  PROSPECT: ["ONBOARDING", "SORTIE"],
  ONBOARDING: ["DIAGNOSTIC_EN_COURS", "SORTIE"],
  DIAGNOSTIC_EN_COURS: ["ACCOMPAGNEMENT_ACTIF", "SORTIE"],
  ACCOMPAGNEMENT_ACTIF: ["SUSPENDU", "SORTIE"],
  SUSPENDU: ["ACCOMPAGNEMENT_ACTIF", "SORTIE"],
  SORTIE: ["SUIVI_POST_PROGRAMME"],
  SUIVI_POST_PROGRAMME: [],
};

export const SIZE_LABELS: Record<Schemas["SizeCategoryEnum"], string> = {
  NON_DETERMINEE: "Non déterminée",
  MICRO: "Micro-entreprise",
  PETITE: "Petite entreprise",
  MOYENNE: "Moyenne entreprise",
  HORS_PME: "Hors PME",
};

export const EXIT_REASON_LABELS: Record<Schemas["ExitReasonEnum"], string> = {
  DIPLOMEE: "Diplômée",
  ABANDON: "Abandon",
  REORIENTATION: "Réorientation",
};

export const PERSON_ROLE_LABELS: Record<Schemas["RoleEnum"], string> = {
  GERANT: "Gérant(e)",
  DG: "Directeur(rice) général(e)",
  PCA: "Président(e) du conseil d'administration",
  PRESIDENT: "Président(e)",
  ASSOCIE: "Associé(e)",
  DIRECTEUR: "Directeur(rice)",
  CONTACT: "Contact",
};

export const SCOPE_LABELS: Record<Schemas["ScopeEnum"], string> = {
  ORG: "Toute l'organisation",
  PROGRAMME: "Un programme",
  PORTEFEUILLE: "PME assignées",
  PME: "Sa propre PME",
};

export const ROLE_IN_PME_LABELS: Record<Schemas["RoleInPmeEnum"], string> = {
  CONSEILLER_PRINCIPAL: "Conseiller principal",
  EXPERT: "Expert",
};
