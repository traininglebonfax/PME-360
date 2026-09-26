import { expect, test } from "@playwright/test";

import { loginStaff } from "./helpers";

test("les analyses montrent les livrables non fournis et la carte des régions", async ({ page }) => {
  await loginStaff(page, "admin@demo.test");
  await page.getByRole("link", { name: "Analyses" }).click();
  await expect(page.getByRole("heading", { name: "Analyses de portefeuille" })).toBeVisible();

  await expect(page.getByText("Quels livrables restent systématiquement non fournis ?")).toBeVisible();
  await expect(page.getByRole("table", { name: "Livrables d'action non fournis" })).toBeVisible();
  await page.getByRole("tab", { name: /Documents d'obligation/ }).click();
  await expect(page.getByText(/Une échéance échue est « non fournie »/)).toBeVisible();

  const map = page.getByRole("img", { name: /Carte des régions/ });
  await expect(map).toBeVisible();
  await expect(map.locator("path[data-testid^='region-']")).toHaveCount(33);
  await page.getByTestId("region-ABIDJAN").hover();
  await expect(page.getByRole("tooltip")).toContainText("District autonome d'Abidjan");
  await page.getByRole("radio", { name: "Score moyen" }).click();
  await expect(page.getByRole("img", { name: "Carte des régions : Score moyen" })).toBeVisible();
  await expect(page.getByText(/geoBoundaries/)).toBeVisible();
});
