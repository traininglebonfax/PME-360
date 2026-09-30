import { expect, test } from "@playwright/test";

import { demoPdf, loginPme } from "./helpers";

// Le dirigeant trouve « Mes documents » dans le menu et peut toujours déposer un document, même non demandé.
test("espace PME : menu visible et dépôt d'un autre document", async ({ page }) => {
  await loginPme(page, "aya.dirigeante@demo.test");
  const menu = page.getByRole("navigation", { name: "Menu de mon espace" });
  for (const entry of ["Accueil", "Mes documents", "Mon plan", "Mon diagnostic"]) {
    await expect(menu.getByRole("link", { name: entry })).toBeVisible();
  }

  await menu.getByRole("link", { name: "Mes documents" }).click();
  await expect(page.getByRole("heading", { name: "Mes documents" })).toBeVisible();
  const other = page.locator("section").filter({ has: page.getByRole("heading", { name: "Déposer un autre document" }) });
  const select = other.getByLabel("Type de document");
  const statuts = await select.locator("option", { hasText: "Statuts" }).first().getAttribute("value");
  await select.selectOption(statuts!);
  await other.locator('input[type="file"]:not([capture])').setInputFiles({
    name: "statuts-demo.pdf",
    mimeType: "application/pdf",
    buffer: demoPdf("DOCUMENT DE DEMONSTRATION - STATUTS"),
  });
  await expect(other.getByText(/document reçu/)).toBeVisible();
  await page.screenshot({ path: "test-results/espace-pme-depots.png", fullPage: true });

  await menu.getByRole("link", { name: "Mon plan" }).click();
  await expect(page.getByRole("heading", { name: "Mon plan d'accompagnement" })).toBeVisible();
});
