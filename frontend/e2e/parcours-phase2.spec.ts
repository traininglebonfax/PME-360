import { expect, test } from "@playwright/test";

import { latestLoginCode, loginStaff } from "./helpers";

test("Health Check, évolution expliquée et indicateurs d'une PME suivie (Délices du Bandama)", async ({ page }) => {
  await loginStaff(page, "konan.conseiller@demo.test");
  await page.getByRole("link", { name: "PME", exact: true }).click();
  await expect(page).toHaveURL(/\/pme$/);
  await page.getByRole("table").getByRole("link", { name: "Délices du Bandama SAS" }).click();
  await page.getByRole("tab", { name: "Diagnostic & scores" }).click();

  await expect(page.getByText(/PME Health Check/)).toBeVisible();
  await expect(page.getByText("Scores par dimension")).toBeVisible();
  await expect(page.getByText("Explication de l'évolution")).toBeVisible();
  await expect(page.getByText(/points entre le/)).toBeVisible();
  await expect(page.getByRole("table", { name: "Historique des snapshots" }).getByRole("row")).toHaveCount(4);
  await expect(page.getByText("Rentabilité nette")).toBeVisible(); // indicateur → formule → données → résultat
});

test("un conseiller revoit et valide un diagnostic soumis (Akwaba)", async ({ page }) => {
  await loginStaff(page, "awa.conseillere@demo.test");
  await expect(page.getByText("Diagnostics à valider")).toBeVisible(); // tableau de bord chargé avant de lire la file
  const pending = page.getByRole("link", { name: /Conseil & Formation Akwaba SARLU/ }).filter({ hasText: "à valider" });
  test.skip((await pending.count()) === 0, "Diagnostic de démonstration déjà validé : relancer seed_demo sur une base neuve.");
  await pending.first().click();

  await expect(page.getByRole("heading", { name: "Revue et validation" })).toBeVisible();
  await expect(page.getByText("Résultat provisoire")).toBeVisible();
  await page.getByText(/Je confirme accepter/).click();
  await page.getByRole("button", { name: "Accepter les critères restants" }).click();
  await page.getByRole("button", { name: "Valider le diagnostic" }).click();

  await expect(page).toHaveURL(/\/pme\/.+\?onglet=diagnostic/);
  await expect(page.getByText(/PME Health Check · Référence/)).toBeVisible();
});

test("la dirigeante voit son score et sa progression dans son espace", async ({ page }) => {
  const email = "aya.dirigeante@demo.test";
  await page.goto("/connexion");
  await page.getByRole("tab", { name: "Espace PME" }).click();
  await page.getByLabel("Adresse e-mail").fill(email);
  const sentAfter = new Date(Date.now() - 1000);
  await page.getByRole("button", { name: "Recevoir mon code" }).click();
  await page.getByLabel("Code reçu par e-mail").fill(await latestLoginCode(email, sentAfter));
  await page.getByRole("button", { name: "Me connecter" }).click();

  await expect(page).toHaveURL(/\/espace$/);
  await expect(page.getByText("/100")).toBeVisible();
  await expect(page.getByText(/Niveau 2 · En structuration/)).toBeVisible();
  await expect(page.getByText(/Fiabilité de la mesure/)).toBeVisible();
});
