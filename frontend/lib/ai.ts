/** IA (Document 4) : libellés, niveaux de confiance et lecture du flux du Copilot (Server-Sent Events). */
import { ApiError, readCookie, type Problem } from "./api";

type Tone = "neutral" | "info" | "brand" | "warning" | "danger" | "muted";

/** Statut de l'extraction IA d'une version de document (revue humaine, Document 4, § 7). */
export const EXTRACTION_STATUS: Record<string, { label: string; tone: Tone }> = {
  PROVISOIRE: { label: "Provisoire", tone: "info" },
  A_VERIFIER: { label: "À vérifier", tone: "warning" },
  VALIDEE: { label: "Validée", tone: "brand" },
  CORRIGEE: { label: "Corrigée", tone: "brand" },
  REJETEE: { label: "Rejetée", tone: "danger" },
  NON_ANALYSEE: { label: "Non analysée", tone: "muted" },
};

export const TASK_LABELS: Record<string, string> = {
  CLASSIFICATION: "Classification documentaire",
  EXTRACTION: "Extraction structurée",
  CONTROLE: "Contrôles et anomalies",
  ANALYSE_FINANCIERE: "Interprétation financière",
  PRE_DIAGNOSTIC: "Pré-diagnostic",
  ASK_AI: "Copilot",
};

export const ANALYSIS_STATUS: Record<string, { label: string; tone: Tone }> = {
  SUCCES: { label: "Succès", tone: "brand" },
  SORTIE_INVALIDE: { label: "Sortie invalide", tone: "warning" },
  REFUSE_POLITIQUE: { label: "Refusé (politique)", tone: "muted" },
  BUDGET_EPUISE: { label: "Budget épuisé", tone: "warning" },
  DIFFERE: { label: "Différé", tone: "info" },
  ECHEC: { label: "Échec", tone: "danger" },
};

export const SUGGESTION_STATUS: Record<string, { label: string; tone: Tone }> = {
  PROPOSEE: { label: "Proposée", tone: "info" },
  ACCEPTEE: { label: "Acceptée", tone: "brand" },
  MODIFIEE: { label: "Modifiée", tone: "warning" },
  ECARTEE: { label: "Écartée", tone: "muted" },
};

export const PROVIDER_LABELS: Record<string, string> = {
  local: "Moteur local (règles)",
  anthropic: "Claude (Anthropic)",
};

/** Contrôles déterministes ajoutés par l'IA (en plus des contrôles de dépôt de la phase 3). */
export const AI_CHECK_LABELS: Record<string, string> = {
  TYPE_ATTENDU: "Type attendu",
  ENTITE_CORRESPOND: "Entreprise",
  CONTENU_SUSPECT: "Contenu suspect",
  BILAN_EQUILIBRE: "Équilibre du bilan",
  COHERENCE_CA_DECLARATIF: "CA / déclaratif",
  COHERENCE_EFFECTIF_CNPS: "Effectif / CNPS",
  COHERENCE_REGIME_CA: "Régime fiscal / CA",
};

export const STATEMENT_STATUS: Record<string, { label: string; tone: Tone }> = {
  PROVISOIRE: { label: "Provisoire (IA)", tone: "info" },
  VERIFIE: { label: "Vérifié", tone: "brand" },
  ECARTE: { label: "Écarté", tone: "muted" },
};

/** Confiance 0..1 → pourcentage et ton (seuil de revue par défaut 0,85 ; champs critiques 0,90). */
export function confidenceTone(value: number | null | undefined, threshold = 0.85): Tone {
  if (value === null || value === undefined) return "muted";
  if (value >= threshold) return "brand";
  if (value >= 0.6) return "warning";
  return "danger";
}

export function formatConfidence(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)} %`;
}

/** Valeur extraite affichable (montants en FCFA, dates, listes). */
export function formatFieldValue(value: unknown, type: string): string {
  if (value === null || value === undefined || value === "") return "—";
  if (type === "number" && typeof value === "number") return `${value.toLocaleString("fr-FR")} FCFA`;
  if (type === "integer" && typeof value === "number") return value.toLocaleString("fr-FR");
  if (type === "date" && typeof value === "string") return new Date(`${value}T00:00:00`).toLocaleDateString("fr-FR");
  if (type === "boolean") return value ? "Oui" : "Non";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

/** Saisie d'une correction → valeur JSON typée (``null`` si vide). */
export function parseFieldValue(raw: string, type: string): unknown {
  const text = raw.trim();
  if (!text) return null;
  if (type === "number" || type === "integer") {
    const number = Number(text.replace(/\s|FCFA/gi, "").replace(",", "."));
    return Number.isFinite(number) ? (type === "integer" ? Math.round(number) : number) : text;
  }
  if (type === "boolean") return ["oui", "true", "1"].includes(text.toLowerCase());
  if (type === "list") return text.split(",").map((item) => item.trim()).filter(Boolean);
  return text;
}

export function fieldInputValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "oui" : "non";
  return String(value);
}

// --- Copilot ---------------------------------------------------------------------------------------------------

export interface AskSource {
  label: string;
  detail?: string;
}

export interface AskMessage {
  id: string;
  content: string;
  sources: AskSource[];
  /** ELEVEE | MOYENNE | FAIBLE */
  confidence: string | null;
  limits: string[];
  analysis_id?: string;
  provider?: string;
}

export type AskEvent =
  | { type: "status"; text: string }
  | { type: "delta"; text: string }
  | { type: "done"; message: AskMessage }
  | { type: "error"; text: string };

/** Découpe un tampon SSE en événements complets ; renvoie le reste non terminé. */
export function parseSse(buffer: string): { events: AskEvent[]; rest: string } {
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: AskEvent[] = [];
  for (const block of blocks) {
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!data) continue;
    try {
      events.push(JSON.parse(data) as AskEvent);
    } catch {
      // bloc incomplet ou commentaire : ignoré
    }
  }
  return { events, rest };
}

/** Pose une question au Copilot et relaie chaque événement du flux. */
export async function askQuestion(
  conversationId: string,
  question: string,
  onEvent: (event: AskEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (!readCookie("pme360_csrftoken")) await fetch("/api/v1/auth/csrf", { credentials: "same-origin" });
  const response = await fetch(`/api/v1/ai/conversations/${conversationId}/messages`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "X-CSRFToken": readCookie("pme360_csrftoken") ?? "",
    },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!response.ok || !response.body) {
    let problem: Problem = { detail: `Erreur ${response.status}` };
    try {
      problem = (await response.json()) as Problem;
    } catch {
      // réponse non JSON
    }
    throw new ApiError(response.status, problem);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSse(buffer);
    buffer = parsed.rest;
    parsed.events.forEach(onEvent);
  }
  parseSse(`${buffer}\n\n`).events.forEach(onEvent);
}
