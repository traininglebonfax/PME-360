/**
 * Modèles de notification : même rendu que le serveur (``pme360/notifications/catalog.py``) pour l'aperçu en direct.
 * ``{variable}`` est remplacé ; ``{{`` et ``}}`` donnent des accolades littérales. Le serveur reste la référence.
 */

const TOKEN = /\{\{|\}\}|\{([a-z_]+)\}/g;

export function renderTemplate(text: string, values: Record<string, string>): string {
  return text.replace(TOKEN, (token, name?: string) => (name ? (values[name] ?? "") : token[0]));
}

export function checkTemplate(text: string, allowed: string[]): string[] {
  const errors: string[] = [];
  const unknown = [...new Set([...text.matchAll(TOKEN)].map((m) => m[1]).filter((n): n is string => Boolean(n) && !allowed.includes(n!)))].sort();
  if (unknown.length) errors.push(`Variable(s) inconnue(s) : ${unknown.map((n) => `{${n}}`).join(", ")}.`);
  const leftover = text.replace(TOKEN, "");
  if (leftover.includes("{") || leftover.includes("}")) errors.push("Accolade isolée : écrivez {variable}, ou {{ et }} pour une accolade littérale.");
  return errors;
}

/** Insère ``{name}`` à la position du curseur ; renvoie le texte et la nouvelle position. */
export function insertVariable(text: string, name: string, start: number, end: number): { text: string; caret: number } {
  const token = `{${name}}`;
  return { text: text.slice(0, start) + token + text.slice(end), caret: start + token.length };
}
