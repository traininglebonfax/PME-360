/** Documents, échéances et conformité : libellés et envoi de fichiers avec progression. */
import { ApiError, readCookie, type Problem } from "./api";

export const ACCEPTED_FILES = ".pdf,.docx,.xlsx,.xls,.csv,.jpg,.jpeg,.png,.heic";

type Tone = "neutral" | "info" | "brand" | "warning" | "danger" | "muted";

/** Statut affiché d'un document (dérivé des axes, cf. backend ``Document.status_display``). */
export const DOCUMENT_STATUS: Record<string, { label: string; tone: Tone }> = {
  RECU: { label: "Reçu", tone: "info" },
  EN_ANALYSE: { label: "En analyse", tone: "info" },
  A_VERIFIER: { label: "À vérifier", tone: "warning" },
  CONFORME: { label: "Conforme", tone: "brand" },
  CONFORME_SOUS_RESERVE: { label: "Conforme sous réserve", tone: "brand" },
  NON_CONFORME: { label: "Non conforme", tone: "danger" },
  INCOHERENT: { label: "Incohérent", tone: "danger" },
  EXPIRE: { label: "Expiré", tone: "danger" },
  REJETE_SECURITE: { label: "Bloqué (sécurité)", tone: "danger" },
};

/** État d'un type de document dans le dossier de conformité. */
export const FOLDER_STATE: Record<string, { label: string; tone: Tone }> = {
  CONFORME: { label: "Conforme", tone: "brand" },
  CONFORME_SOUS_RESERVE: { label: "Sous réserve", tone: "brand" },
  EN_VERIFICATION: { label: "En vérification", tone: "info" },
  MANQUANT: { label: "Manquant", tone: "warning" },
  EXPIRE: { label: "Expiré", tone: "danger" },
  NON_CONFORME: { label: "Non conforme", tone: "danger" },
};

export const DEADLINE_STATUS: Record<string, { label: string; tone: Tone }> = {
  A_FOURNIR: { label: "À fournir", tone: "neutral" },
  EN_ATTENTE: { label: "En attente", tone: "info" },
  RECU: { label: "Reçu", tone: "info" },
  EN_ANALYSE: { label: "En analyse", tone: "info" },
  VERIF_HUMAINE_REQUISE: { label: "En vérification", tone: "info" },
  CONFORME: { label: "Conforme", tone: "brand" },
  CONFORME_SOUS_RESERVE: { label: "Conforme sous réserve", tone: "brand" },
  NON_CONFORME: { label: "Non conforme", tone: "danger" },
  EXPIRE: { label: "Document expiré", tone: "danger" },
  INCOHERENT: { label: "Document incohérent", tone: "danger" },
  EN_RETARD: { label: "En retard", tone: "danger" },
  DISPENSE: { label: "Dispensée", tone: "muted" },
};

export const SEVERITY: Record<string, { label: string; tone: Tone }> = {
  INFO: { label: "Information", tone: "info" },
  MOYENNE: { label: "Moyenne", tone: "warning" },
  ELEVEE: { label: "Élevée", tone: "danger" },
  CRITIQUE: { label: "Critique", tone: "danger" },
};

export const CHECK_LABELS: Record<string, string> = {
  DOUBLON: "Doublon",
  QUALITE_LECTURE: "Lisibilité",
  DATE_VALIDITE: "Date de validité",
  PERIODE_ATTENDUE: "Période attendue",
};

export const DECISIONS = [
  { value: "CONFORME", label: "Conforme" },
  { value: "CONFORME_SOUS_RESERVE", label: "Conforme sous réserve" },
  { value: "NON_CONFORME", label: "Non conforme" },
  { value: "INCOHERENT", label: "Incohérent" },
] as const;

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} Mo`;
}

export interface UploadFields {
  document_type?: string;
  document_id?: string;
  deadline_id?: string;
  title?: string;
  period_start?: string;
  period_end?: string;
  issued_at?: string;
  expires_at?: string;
}

/**
 * Dépôt multipart avec progression (XMLHttpRequest : utile sur connexion lente).
 * Rejette une ``ApiError`` au format RFC 9457 (fichier refusé, infecté, trop volumineux…).
 */
export async function uploadDocument(
  pmeId: string,
  file: File,
  fields: UploadFields,
  onProgress?: (ratio: number) => void,
): Promise<{ id: string }> {
  if (!readCookie("pme360_csrftoken")) await fetch("/api/v1/auth/csrf", { credentials: "same-origin" });
  const form = new FormData();
  form.append("file", file);
  for (const [key, value] of Object.entries(fields)) if (value) form.append(key, value);
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", `/api/v1/pmes/${pmeId}/documents`);
    request.withCredentials = true;
    request.setRequestHeader("X-CSRFToken", readCookie("pme360_csrftoken") ?? "");
    request.upload.onprogress = (event) => event.lengthComputable && onProgress?.(event.loaded / event.total);
    request.onerror = () => reject(new ApiError(0, { detail: "Connexion interrompue : réessayez." }));
    request.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(request.responseText);
      } catch {
        body = { detail: `Erreur ${request.status}` };
      }
      if (request.status >= 200 && request.status < 300) resolve(body as { id: string });
      else reject(new ApiError(request.status, body as Problem));
    };
    request.send(form);
  });
}
