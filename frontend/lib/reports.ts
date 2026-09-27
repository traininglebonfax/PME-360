/**
 * Rapports d'une PME (Document 9, § 7) : libellés et périodes lisibles. La période est une date (diagnostic,
 * conformité) ou un intervalle « AAAA-MM-JJ_AAAA-MM-JJ » (suivi, annuel).
 */
import { formatDate } from "@/lib/format";

export type PmeReportType = "SUIVI" | "CONFORMITE" | "ANNUEL";

export const REPORT_TYPES: Record<string, { label: string; hint: string }> = {
  DIAGNOSTIC: { label: "Rapport de diagnostic", hint: "16 sections, édité à la validation du diagnostic." },
  SUIVI: {
    label: "Rapport de suivi",
    hint: "Évolution depuis le dernier rapport de suivi : score, actions, progrès vérifiés, conformité. Édité aussi chaque trimestre.",
  },
  CONFORMITE: { label: "Rapport de conformité", hint: "État du dossier, ce qu'il reste à fournir, échéances et anomalies." },
  ANNUEL: { label: "Rapport annuel", hint: "Trajectoire sur 12 mois et explication des écarts de score." },
};

/** Types que l'équipe peut éditer à la demande depuis la fiche PME. */
export const EDITABLE_REPORT_TYPES: PmeReportType[] = ["SUIVI", "CONFORMITE", "ANNUEL"];

export function reportLabel(type: string, period: string): string {
  const label = REPORT_TYPES[type]?.label ?? "Rapport";
  if (period.includes("_")) {
    const [start, end] = period.split("_");
    return start === end ? `${label} du ${formatDate(end)}` : `${label} du ${formatDate(start)} au ${formatDate(end)}`;
  }
  return `${label} ${type === "CONFORMITE" ? "au" : "du"} ${formatDate(period)}`;
}
