/** Accompagnement (Document 7) : libellés et tons des recommandations, plans, actions et livrables. */
import type { Schemas } from "./api";

type Tone = "neutral" | "info" | "brand" | "warning" | "danger" | "muted";

export type ActionStatus = Schemas["ActionStatusEnum"];

export const ACTION_STATUS: Record<ActionStatus, { label: string; tone: Tone; pme: string }> = {
  BLOQUE: { label: "Bloquée", tone: "muted", pme: "Disponible plus tard" },
  NON_COMMENCE: { label: "Non commencée", tone: "neutral", pme: "À démarrer" },
  EN_COURS: { label: "En cours", tone: "info", pme: "En cours" },
  DOCUMENT_DEMANDE: { label: "Document demandé", tone: "warning", pme: "Document à déposer" },
  DOCUMENT_RECU: { label: "Document reçu", tone: "info", pme: "Document reçu" },
  A_VERIFIER: { label: "À vérifier", tone: "warning", pme: "En vérification" },
  CONFORME: { label: "Conforme", tone: "brand", pme: "Validée" },
  NON_CONFORME: { label: "Non conforme", tone: "danger", pme: "Document à reprendre" },
  TERMINE: { label: "Terminée", tone: "brand", pme: "Terminée" },
  EN_ATTENTE_PME: { label: "En attente PME", tone: "warning", pme: "En attente de votre part" },
  EN_ATTENTE_GUDE: { label: "En attente GUDE-PME", tone: "info", pme: "En attente de votre conseiller" },
  ABANDONNE: { label: "Abandonnée", tone: "muted", pme: "Abandonnée" },
};

/** Libellé du bouton de transition (verbe). */
export const TRANSITION_LABELS: Partial<Record<ActionStatus, string>> = {
  EN_COURS: "Démarrer / reprendre",
  DOCUMENT_DEMANDE: "Demander le document",
  EN_ATTENTE_PME: "En attente de la PME",
  EN_ATTENTE_GUDE: "En attente de GUDE-PME",
  TERMINE: "Terminer l'action",
  ABANDONNE: "Abandonner",
};

export const PHASES = [
  { key: "J1_30", label: "Jours 1–30", hint: "Urgentes" },
  { key: "J31_60", label: "Jours 31–60", hint: "Structurantes" },
  { key: "J61_90", label: "Jours 61–90", hint: "Consolidation" },
  { key: "M6", label: "6 mois", hint: "Moyen terme" },
  { key: "M12", label: "12 mois", hint: "Croissance" },
] as const;

export const PLAN_STATUS: Record<string, { label: string; tone: Tone }> = {
  BROUILLON: { label: "Brouillon", tone: "neutral" },
  EN_VALIDATION: { label: "En validation", tone: "warning" },
  VALIDE: { label: "Validé", tone: "brand" },
  EN_COURS: { label: "En cours", tone: "info" },
  CLOS: { label: "Clos", tone: "muted" },
};

export const RECOMMENDATION_STATUS: Record<string, { label: string; tone: Tone }> = {
  PROPOSEE: { label: "Proposée", tone: "info" },
  ACCEPTEE: { label: "Acceptée", tone: "brand" },
  REJETEE: { label: "Rejetée", tone: "muted" },
  CONVERTIE: { label: "Au plan", tone: "brand" },
};

export const SOURCE_LABELS: Record<string, string> = { REGLE: "Règle", IA: "IA", CONSEILLER: "Conseiller" };

export const DELIVERABLE_STATUS: Record<string, { label: string; tone: Tone }> = {
  ATTENDU: { label: "Attendu", tone: "neutral" },
  DEPOSE: { label: "Déposé", tone: "info" },
  A_VERIFIER: { label: "En vérification", tone: "warning" },
  CONFORME: { label: "Conforme", tone: "brand" },
  NON_CONFORME: { label: "À reprendre", tone: "danger" },
};

export const AXES = [
  { key: "impact", label: "Impact", short: "I" },
  { key: "urgency", label: "Urgence", short: "U" },
  { key: "risk", label: "Risque", short: "R" },
  { key: "effort", label: "Effort", short: "E" },
] as const;

export const DIMENSIONS: Record<string, string> = {
  D01: "Formalisation",
  D02: "Fiscalité",
  D03: "CNPS / Social",
  D04: "Finance",
  D05: "Stratégie",
  D06: "Commercial",
  D07: "Opérations",
  D08: "RH & organisation",
  D09: "Digital",
  D10: "Risques",
  D11: "Financement",
  D12: "Innovation",
};

export const RULE_STATUS: Record<string, { label: string; tone: Tone }> = {
  DRAFT: { label: "Brouillon", tone: "neutral" },
  ACTIVE: { label: "Active", tone: "brand" },
  INACTIVE: { label: "Inactive", tone: "muted" },
};

/** Priorité PS (13 à 100) → libellé (Document 6, § 9.2). */
export function priorityLabel(ps: number): { label: string; tone: Tone } {
  if (ps >= 70) return { label: "Élevée", tone: "danger" };
  if (ps >= 50) return { label: "Moyenne", tone: "warning" };
  return { label: "Normale", tone: "neutral" };
}

export function formatCost(min: number, max: number): string {
  const fmt = (v: number) => `${v.toLocaleString("fr-FR")} FCFA`;
  if (!min && !max) return "Inclus dans l'accompagnement";
  return min === max ? fmt(max) : `${min ? fmt(min) : "0"} à ${fmt(max)}`;
}
