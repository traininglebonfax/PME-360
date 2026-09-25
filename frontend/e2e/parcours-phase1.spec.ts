import { expect, test } from "@playwright/test";

import { latestLoginCode, loginStaff } from "./helpers";

test("un conseiller se connecte (MFA), crée une PME et la retrouve tracée dans son historique", async ({ page }) => {
  await loginStaff(page, "konan.conseiller@demo.test");
  await expect(page.getByRole("heading", { name: /Bonjour Konan/ })).toBeVisible();
  await expect(page.getByText("PME suivies")).toBeVisible();

  const name = `Menuiserie Test E2E ${Date.now()} SARL`;
  await page.getByRole("link", { name: "Nouvelle PME" }).first().click();
  await page.getByLabel("Raison sociale").fill(name);
  await page.getByLabel("N° RCCM").fill(`e2e abj ${Date.now()}`);
  await page.getByRole("button", { name: "Continuer" }).click();

  await page.getByLabel("Secteur d'activité").selectOption({ label: "Services aux entreprises et aux particuliers" });
  await page.getByLabel("Effectif déclaré").fill("7");
  await page.getByLabel("Région ou district").selectOption({ label: "District autonome d'Abidjan" });
  await page.getByRole("button", { name: "Continuer" }).click();

  await page.getByLabel("Nom complet").fill("Awa Test");
  await page.getByRole("button", { name: /^Créer/ }).click();

  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.getByText("Intégration").first()).toBeVisible();
  await expect(page.getByRole("main").getByText("Konan Brou")).toBeVisible(); // assigné automatiquement comme conseiller principal

  await page.getByRole("tab", { name: "Identité" }).click();
  await page.getByLabel("Commune").fill("Treichville");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("Modifications enregistrées.")).toBeVisible();

  await page.getByRole("tab", { name: "Historique" }).click();
  await expect(page.getByText("Fiche PME modifiée")).toBeVisible();
  await expect(page.getByText("PME créée")).toBeVisible();
  await expect(page.getByText("Treichville")).toBeVisible();
});

test("un conseiller ne voit que les PME de son portefeuille", async ({ page }) => {
  await loginStaff(page, "awa.conseillere@demo.test");
  await page.getByRole("link", { name: "PME", exact: true }).click();
  await expect(page.getByRole("link", { name: "NovaTech CI SAS" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Boutik Plus Distribution SARL" })).toHaveCount(0);
});

test("une dirigeante de PME se connecte par code e-mail et accède à son espace", async ({ page }) => {
  const email = "aya.dirigeante@demo.test";
  await page.goto("/connexion");
  await page.getByRole("tab", { name: "Espace PME" }).click();
  await page.getByLabel("Adresse e-mail").fill(email);
  const sentAfter = new Date(Date.now() - 1000);
  await page.getByRole("button", { name: "Recevoir mon code" }).click();
  await page.getByLabel("Code reçu par e-mail").fill(await latestLoginCode(email, sentAfter));
  await page.getByRole("button", { name: "Me connecter" }).click();

  await expect(page).toHaveURL(/\/espace$/);
  await expect(page.getByRole("heading", { name: "Boutik Plus Distribution SARL" })).toBeVisible();
  await expect(page.getByText("Où j'en suis ?")).toBeVisible();
  await expect(page.getByText("Konan Brou")).toBeVisible();

  // Le portail GUDE lui est inaccessible : redirection vers son espace.
  await page.goto("/pme");
  await expect(page).toHaveURL(/\/espace$/);
});
