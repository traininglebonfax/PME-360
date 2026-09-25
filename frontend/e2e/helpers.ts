import { createHash, createHmac } from "node:crypto";

import { expect, type Page } from "@playwright/test";

export const DEMO_PASSWORD = "Demo-PME360-2026!";
const MAILPIT_URL = process.env.E2E_MAILPIT_URL ?? "http://localhost:8035";

/** Secret TOTP des comptes de démonstration (miroir de seed_demo.demo_totp_secret). */
function demoSecret(email: string): Buffer {
  return createHash("sha256").update(`pme360-demo:${email}`).digest().subarray(0, 20);
}

const lastStep = new Map<string, number>();

/** Code TOTP (RFC 6238) ; n'utilise jamais deux fois le même pas pour un compte (anti-rejeu côté API). */
export async function totp(email: string): Promise<string> {
  let step = Math.floor(Date.now() / 30_000);
  const previous = lastStep.get(email);
  if (previous !== undefined && step <= previous) {
    await new Promise((resolve) => setTimeout(resolve, (previous + 1) * 30_000 - Date.now() + 500));
    step = previous + 1;
  }
  lastStep.set(email, step);
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(step));
  const hmac = createHmac("sha1", demoSecret(email)).update(counter).digest();
  const offset = hmac[hmac.length - 1] & 0x0f;
  const binary = (hmac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return binary.toString().padStart(6, "0");
}

export async function loginStaff(page: Page, email: string) {
  await page.goto("/connexion");
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByLabel(/^Mot de passe/).fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();
  // Un pas TOTP déjà consommé (par un lancement précédent) est refusé par l'API : on réessaie au pas suivant.
  for (let attempt = 0; attempt < 2; attempt++) {
    await page.getByLabel("Code de vérification").fill(await totp(email));
    await page.getByRole("button", { name: "Valider" }).click();
    const outcome = await Promise.race([
      page.waitForURL(/\/tableau-de-bord$/).then(() => "ok"),
      page.getByText("Code invalide ou expiré.").waitFor().then(() => "rejected"),
    ]);
    if (outcome === "ok") return;
    lastStep.set(email, Math.floor(Date.now() / 30_000));
  }
  await expect(page).toHaveURL(/\/tableau-de-bord$/);
}

/** Dernier code de connexion reçu par e-mail (Mailpit). */
export async function latestLoginCode(email: string, after: Date): Promise<string> {
  for (let attempt = 0; attempt < 20; attempt++) {
    const response = await fetch(`${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:${email}`)}&limit=1`);
    const data = (await response.json()) as { messages: { ID: string; Created: string; Subject: string }[] };
    const message = data.messages[0];
    if (message && new Date(message.Created) >= after) {
      const match = message.Subject.match(/(\d{6})/);
      if (match) return match[1];
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Aucun code reçu pour ${email}`);
}

/** Connexion d'un utilisateur PME par code e-mail (lu dans Mailpit). */
export async function loginPme(page: Page, email: string) {
  await page.goto("/connexion");
  await page.getByRole("tab", { name: "Espace PME" }).click();
  await page.getByLabel("Adresse e-mail").fill(email);
  const sentAfter = new Date(Date.now() - 1000);
  await page.getByRole("button", { name: "Recevoir mon code" }).click();
  await page.getByLabel("Code reçu par e-mail").fill(await latestLoginCode(email, sentAfter));
  await page.getByRole("button", { name: "Me connecter" }).click();
  await expect(page).toHaveURL(/\/espace$/);
}

/** PDF minimal valide (lisible par pypdf), fictif. */
export function demoPdf(text: string): Buffer {
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
  ];
  const stream = `BT /F1 14 Tf 72 760 Td (${text}) Tj ET`;
  objects.push(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
  objects.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  let body = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((object, index) => {
    offsets.push(body.length);
    body += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = body.length;
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  body += offsets.map((offset) => `${offset.toString().padStart(10, "0")} 00000 n \n`).join("");
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(body, "latin1");
}
