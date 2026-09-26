import { expect, test } from "@playwright/test";

import { loginStaff } from "./helpers";

test("l'administrateur crée un type de document puis une obligation avec des règles lisibles", async ({ page }) => {
  const stamp = Date.now().toString().slice(-6);
  const typeCode = `E2E-DOC-${stamp}`;
  const typeName = `Registre E2E ${stamp}`;
  const obligationName = `Tenue du registre E2E ${stamp}`;

  await loginStaff(page, "admin@demo.test");
  await page.getByRole("link", { name: "Conformité et obligations" }).click();

  // Type de document
  await page.getByRole("tab", { name: "Types de documents" }).click();
  await page.getByRole("button", { name: "Nouveau type de document" }).click();
  await page.getByLabel("Code").fill(typeCode);
  await page.getByLabel("Libellé").fill(typeName);
  await page.getByLabel("Catégorie").selectOption({ index: 1 });
  await page.getByLabel("Période couverte").selectOption("TRIMESTRE");
  await page.getByRole("button", { name: "Créer le type" }).click();
  const typeRow = page.getByRole("row").filter({ hasText: typeCode });
  await expect(typeRow).toContainText(typeName);
  await expect(typeRow).toContainText("0 document(s)");

  // Obligation
  await page.getByRole("tab", { name: "Obligations" }).click();
  await page.getByRole("button", { name: "Nouvelle obligation" }).click();
  await page.getByLabel("Code").fill(`E2E-OBL-${stamp}`);
  await page.getByLabel("Libellé").fill(obligationName);
  await page.getByLabel("Nature").selectOption("PROGRAMME");
  await page.getByLabel("Document à déposer").selectOption(typeCode);
  await page.getByLabel("Ajouter une condition").selectOption("headcount");
  await page.getByLabel("Valeur").fill("5");
  await page.getByLabel("Ajouter une condition").selectOption("size_category");
  await page.getByTestId("applicability-clause").nth(1).getByLabel("Petite entreprise").check();
  await expect(page.getByTestId("applicability-preview")).toHaveText("Lecture : Effectif au moins 5 ET Taille parmi Petite entreprise");
  await page.getByLabel("Selon l'effectif").check();
  await page.getByLabel("Seuil d'effectif").fill("20");
  await page.getByRole("button", { name: "Créer l'obligation" }).click();

  const row = page.getByRole("row").filter({ hasText: obligationName });
  await expect(row).toContainText("Effectif au moins 5 ET Taille parmi Petite entreprise");
  await expect(row).toContainText("Mensuelle si effectif au moins 20, sinon trimestrielle");
  await expect(row.getByLabel(`Activer ${obligationName}`)).not.toBeChecked();

  // Le type est désormais référencé par l'obligation
  await page.getByRole("tab", { name: "Types de documents" }).click();
  await expect(page.getByRole("row").filter({ hasText: typeCode })).toContainText(`Obligations : E2E-OBL-${stamp}`);
});
