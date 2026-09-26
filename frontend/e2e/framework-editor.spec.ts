import { expect, test } from "@playwright/test";

import { loginStaff } from "./helpers";

const RUBRIC = ["Aucun registre", "Notes éparses", "Registre partiel", "Registre tenu", "Registre tenu et signé"];

test("l'administrateur modifie un brouillon de référentiel : pondération, nouveau critère, contrôle de publication", async ({ page }) => {
  const version = `9.${Date.now().toString().slice(-6)}.0`;
  await loginStaff(page, "admin@demo.test");
  await page.getByRole("link", { name: "Référentiel" }).click();
  await expect(page.getByRole("heading", { name: "Référentiel de diagnostic" })).toBeVisible();

  await page.getByLabel("Nouvelle version (brouillon)").fill(version);
  await page.getByRole("button", { name: /Créer un brouillon/ }).click();
  const status = page.getByTestId("publication-status");
  await expect(page.getByText(`Brouillon v${version}`)).toBeVisible();
  await expect(status.getByText(/peut être publié/)).toBeVisible();

  // Baisser le poids d'un critère déséquilibre la dimension : la publication est signalée comme bloquée.
  await page.getByRole("button", { name: /^D01/ }).click();
  const weight = page.getByLabel("Poids de FOR-01");
  const initial = Number(await weight.inputValue());
  await weight.fill(String(initial - 5));
  await weight.press("Enter");
  await expect(status.getByText(/D01 : la somme des poids du tronc commun/)).toBeVisible();

  // Un nouveau critère de 5 points rééquilibre la dimension.
  await page.getByRole("button", { name: "+ Nouveau critère dans D01" }).click();
  await page.getByLabel("Code du critère").fill("FOR-E2E");
  await page.getByLabel("Libellé du critère").fill("Registre des décisions tenu à jour");
  await page.getByLabel("Poids dans la dimension (points)").fill("5");
  for (const [level, text] of RUBRIC.entries()) await page.getByLabel(`Grille Niveau ${level}`).fill(text);
  await page.getByLabel("Question principale (facultatif)").fill("Tenez-vous un registre des décisions ?");
  await page.getByLabel("Ajouter une condition").selectOption("has_stock");
  await expect(page.getByTestId("applicability-preview")).toHaveText("Lecture : Gère un stock égal à oui");
  await page.getByRole("button", { name: "Ajouter le critère" }).click();

  const table = page.getByRole("table", { name: "Critères de D01" });
  await expect(table.getByText("Registre des décisions tenu à jour")).toBeVisible();
  await expect(status.getByText(/peut être publié/)).toBeVisible();
  await table.getByRole("row").filter({ hasText: "FOR-E2E" }).getByRole("button", { name: /1 question/ }).click();
  await expect(page.getByText("Tenez-vous un registre des décisions ?")).toBeVisible();

  // Le brouillon d'essai est supprimé : la version publiée de la démo reste inchangée.
  await page.getByRole("button", { name: "Supprimer ce brouillon" }).click();
  await page.getByRole("button", { name: "Oui, supprimer" }).click();
  await expect(page.getByText(`Brouillon v${version}`)).toHaveCount(0);
  await expect(page.getByRole("button", { name: new RegExp(`v${version.replace(/\./g, "\\.")}`) })).toHaveCount(0);
});
