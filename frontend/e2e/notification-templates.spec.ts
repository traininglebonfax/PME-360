import { expect, test } from "@playwright/test";

import { loginStaff } from "./helpers";

const MAILPIT_URL = process.env.E2E_MAILPIT_URL ?? "http://localhost:8035";

test("l'administrateur personnalise un modèle de notification, le teste puis revient au texte par défaut", async ({ page }) => {
  const stamp = Date.now().toString().slice(-6);
  await loginStaff(page, "admin@demo.test");
  await page.getByRole("link", { name: "Modèles de notification" }).click();
  await expect(page.getByRole("heading", { name: "Modèles de notification" })).toBeVisible();
  await page.getByRole("list", { name: "Événements" }).getByRole("button", { name: /Rapport disponible/ }).click();

  const subject = page.getByLabel("Objet");
  await subject.fill("Votre rapport est prêt");
  await page.getByRole("button", { name: /\{nom\}|\{pme\}/ }).click();
  await expect(subject).toHaveValue("Votre rapport est prêt{pme}");
  await subject.fill(`Rapport ${stamp} disponible : {entreprise}`);
  await expect(page.getByText("Variable(s) inconnue(s) : {entreprise}.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Enregistrer" })).toBeDisabled();

  await subject.fill(`Rapport ${stamp} disponible : {pme}`);
  await expect(page.getByTestId("preview-inapp")).toContainText(`Rapport ${stamp} disponible : Boutik Plus SARL`);
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("Modèle enregistré")).toBeVisible();
  await expect(page.getByText("Personnalisé", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "M'envoyer un e-mail de test" }).click();
  await expect(page.getByText("E-mail de test envoyé à admin@demo.test.")).toBeVisible();
  const search = await fetch(`${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`subject:"Rapport ${stamp}"`)}&limit=1`);
  const found = (await search.json()) as { messages: { Subject: string }[] };
  expect(found.messages[0]?.Subject).toBe(`[Test] Rapport ${stamp} disponible : Boutik Plus SARL`);

  await page.getByRole("button", { name: "Revenir au texte par défaut" }).click();
  await expect(page.getByText("Texte par défaut", { exact: true })).toBeVisible();
  await expect(subject).toHaveValue("Rapport de diagnostic disponible : {pme}");
});
