import { expect, test } from "@playwright/test";

import { loginPme, loginStaff } from "./helpers";

// Le nom et le profil de la personne connectée restent visibles en haut de chaque page (démo multi-profils).
test("équipe : nom et profil affichés en haut de page", async ({ page }) => {
  await loginStaff(page, "konan.conseiller@demo.test");
  const identity = page.getByTestId("current-user");
  await expect(identity).toContainText("Konan Brou");
  await expect(identity).toContainText("Conseiller");
  await page.goto("/pme");
  await expect(page.getByTestId("current-user")).toContainText("Konan Brou");
  await page.screenshot({ path: "test-results/identite-conseiller.png" });
});

test("espace PME : nom et profil affichés en haut de page", async ({ page }) => {
  await loginPme(page, "aya.dirigeante@demo.test");
  const identity = page.getByTestId("current-user");
  await expect(identity).toContainText("Aya Kouassi");
  await expect(identity).toContainText("Dirigeant de PME");
  await page.screenshot({ path: "test-results/identite-pme.png" });
  await page.goto("/espace/plan");
  await expect(page.getByTestId("current-user")).toContainText("Aya Kouassi");
});
