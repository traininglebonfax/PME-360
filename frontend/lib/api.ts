/**
 * Client de l'API PME360, typé à partir du schéma OpenAPI (`npm run api:types`).
 *
 * - même origine (`/api` est relayé vers Django par Next) : cookie de session HttpOnly ;
 * - en-tête CSRF ajouté sur toute requête non sûre ;
 * - erreurs RFC 9457 converties en `ApiError` (code métier stable + messages par champ).
 */
import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./api-schema";

export type Schemas = components["schemas"];

const CSRF_COOKIE = "pme360_csrftoken";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export interface Problem {
  type?: string;
  title?: string;
  status?: number;
  code?: string;
  detail?: string;
  errors?: Record<string, unknown>;
  [key: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly problem: Problem;

  constructor(status: number, problem: Problem) {
    super(problem.detail ?? `Erreur ${status}`);
    this.status = status;
    this.code = problem.code ?? "error";
    this.problem = problem;
  }

  /** Messages d'erreur par champ (validation DRF), aplatis. */
  fieldErrors(): Record<string, string> {
    const result: Record<string, string> = {};
    const walk = (value: unknown, prefix: string) => {
      if (Array.isArray(value)) {
        if (value.every((item) => typeof item === "string")) result[prefix] = value.join(" ");
        else value.forEach((item, index) => walk(item, `${prefix}.${index}`));
      } else if (value && typeof value === "object") {
        for (const [key, nested] of Object.entries(value)) walk(nested, prefix ? `${prefix}.${key}` : key);
      } else if (typeof value === "string") {
        result[prefix] = value;
      }
    };
    walk(this.problem.errors ?? {}, "");
    return result;
  }
}

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

async function ensureCsrfToken(): Promise<string | null> {
  let token = readCookie(CSRF_COOKIE);
  if (!token) {
    await fetch("/api/v1/auth/csrf", { credentials: "same-origin" });
    token = readCookie(CSRF_COOKIE);
  }
  return token;
}

const csrfMiddleware: Middleware = {
  async onRequest({ request }) {
    if (!SAFE_METHODS.has(request.method)) {
      const token = await ensureCsrfToken();
      if (token) request.headers.set("X-CSRFToken", token);
    }
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: typeof window === "undefined" ? "http://localhost" : "", credentials: "same-origin" });
api.use(csrfMiddleware);

/** Renvoie `data` ou lève une `ApiError` exploitable par l'interface. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) {
    const problem: Problem =
      error && typeof error === "object" ? (error as Problem) : { detail: `Erreur ${response.status}` };
    throw new ApiError(response.status, problem);
  }
  return data as T;
}

/** Message lisible pour une erreur quelconque. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.problem.detail ?? error.message;
  if (error instanceof Error) return error.message;
  return "Une erreur inattendue est survenue.";
}
