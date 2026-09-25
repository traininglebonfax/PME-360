import { expect, test } from "@playwright/test";

import { demoPdf, loginPme, loginStaff } from "./helpers";

const DFE = "Déclaration fiscale d'existence (NCC)";

/** Chaîne de test antivirus standard, assemblée à l'exécution (jamais contiguë dans les sources). */
const avTestString = () =>
  [String.raw`X5O!P%@AP[4\PZX54(P^)7CC)7}$`, "EICAR-STANDARD-ANTIVIRUS", "-TEST-FILE!$H+H*"].join("");

test("la dirigeante dépose un justificatif ; un fichier infecté est refusé", async ({ page }) => {
  await loginPme(page, "aya.dirigeante@demo.test");
  await page.getByRole("link", { name: "Mes documents" }).click();
  await expect(page.getByRole("heading", { name: "Mes documents" })).toBeVisible();
  const folder = page.locator("section").filter({ has: page.getByRole("heading", { name: "Mon dossier" }) });
  await expect(folder.getByText(/Dossier complet|%/).first()).toBeVisible();

  // Fichier piégé : refus avant tout stockage, message clair.
  const anyUpload = folder.locator('input[type="file"]:not([capture])').last();
  await anyUpload.setInputFiles({ name: "releve.csv", mimeType: "text/csv", buffer: Buffer.from(avTestString()) });
  await expect(folder.getByRole("alert").first()).toContainText(/virus|infect|refus/i);

  // Dépôt de la DFE : part en vérification, jamais conforme d'office.
  const dfe = folder.getByRole("listitem").filter({ hasText: DFE });
  const dfeUpload = dfe.locator('input[type="file"]:not([capture])');
  test.skip((await dfeUpload.count()) === 0, "DFE déjà déposée : relancer seed_demo sur une base neuve.");
  await dfeUpload.setInputFiles({ name: "dfe-demo.pdf", mimeType: "application/pdf", buffer: demoPdf("DOCUMENT DE DEMONSTRATION - DFE") });
  await expect(dfe.getByText("En vérification")).toBeVisible();
});

test("le conseiller vérifie le document déposé depuis sa file", async ({ page }) => {
  await loginStaff(page, "konan.conseiller@demo.test");
  await page.getByRole("link", { name: "Documents à vérifier" }).click();
  await expect(page.getByRole("heading", { name: "Documents à vérifier" })).toBeVisible();
  await page.getByRole("main").getByRole("list").or(page.getByText("Aucun document en attente")).first().waitFor(); // file chargée
  const item = page.getByRole("link").filter({ hasText: DFE }).filter({ hasText: "Boutik Plus" });
  test.skip((await item.count()) === 0, "Aucune DFE en attente : lancer d'abord le test de dépôt.");
  await item.first().click();

  await expect(page.getByTitle("Aperçu du document")).toBeVisible();
  await expect(page.getByText(/Sain \(/)).toBeVisible();
  await page.getByLabel("Conforme", { exact: true }).check();
  await page.getByRole("button", { name: "Enregistrer la décision" }).click();
  await expect(page).toHaveURL(/\/verifications$/);
  await expect(page.getByRole("link").filter({ hasText: DFE }).filter({ hasText: "Boutik Plus" })).toHaveCount(0);
});

test("l'administrateur consulte le registre réglementaire et lance le planificateur", async ({ page }) => {
  await loginStaff(page, "admin@demo.test");
  await page.getByRole("link", { name: "Conformité et obligations" }).click();
  await expect(page.getByRole("heading", { name: "Conformité et obligations" })).toBeVisible();
  await expect(page.getByText("REG-CNPS-01")).toBeVisible();
  await page.getByRole("tab", { name: "Obligations" }).click();
  await expect(page.getByRole("table")).toBeVisible();
  await page.getByRole("button", { name: "Exécuter le planificateur maintenant" }).click();
  await expect(page.getByText(/PME traitées/)).toBeVisible();
});
