import { expect, test } from "@playwright/test";

import { loginStaff } from "./helpers";

test("l'administrateur importe des PME depuis un fichier CSV", async ({ page }) => {
  const stamp = Date.now().toString().slice(-7);
  await loginStaff(page, "admin@demo.test");
  await page.getByRole("link", { name: "PME", exact: true }).click();
  await page.getByRole("link", { name: "Importer (CSV)" }).click();
  await expect(page.getByRole("heading", { name: "Importer des PME" })).toBeVisible();

  const template = page.waitForEvent("download");
  await page.getByRole("link", { name: "Télécharger le modèle" }).click();
  expect((await template).suggestedFilename()).toBe("modele-import-pme.csv");

  const csv = [
    "Raison sociale;Secteur;Région;Date de création;Effectif",
    `Import Alpha ${stamp} SARL;COMMERCE;ABIDJAN;12/05/2018;7`,
    `Import Beta ${stamp} SA;Commerce et distribution;;;`,
    `Import Erreur ${stamp};SECTEUR-INCONNU;;;`,
  ].join("\n");
  await page.getByLabel("Fichier CSV").setInputFiles({ name: "pme.csv", mimeType: "text/csv", buffer: Buffer.from(csv, "utf-8") });
  const table = page.getByRole("table", { name: "Lignes du fichier" });
  await expect(table.getByText(`Import Alpha ${stamp} SARL`)).toBeVisible();
  await expect(table.getByText("« SECTEUR-INCONNU » n'existe pas dans la nomenclature.")).toBeVisible();

  await page.getByRole("button", { name: "Importer 2 PME" }).click();
  await expect(page.getByText("Import terminé")).toBeVisible();
  await expect(page.getByText(/2 PME créée\(s\)/)).toBeVisible();
  await table.getByRole("link", { name: `Import Alpha ${stamp} SARL` }).click();
  await expect(page.getByRole("heading", { name: `Import Alpha ${stamp} SARL` })).toBeVisible();
});
