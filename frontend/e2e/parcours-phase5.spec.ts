import { expect, test } from "@playwright/test";

import { demoPdf, loginPme, loginStaff } from "./helpers";

const CAISSE = "Procédure de caisse et rapprochements";

test("le conseiller revoit les recommandations et fait valider le plan de Délices du Bandama", async ({ page }) => {
  await loginStaff(page, "konan.conseiller@demo.test");
  await page.getByRole("link", { name: "PME", exact: true }).click();
  await page.getByRole("link", { name: /Délices/ }).first().click();
  await page.getByRole("tab", { name: "Plan & actions" }).click();
  await page.getByRole("heading", { name: "Recommandations" }).or(page.getByText(/Plan d'accompagnement/)).first().waitFor();
  const recommendations = page.getByTestId("recommendation");
  test.skip((await recommendations.count()) === 0, "Plan déjà soumis : relancer seed_demo sur une base neuve.");

  await expect(recommendations.first().getByText(/Impact \d\/5/)).toBeVisible();
  // Rejet motivé, puis acceptation des deux plus prioritaires.
  const last = recommendations.last();
  if (await last.getByRole("button", { name: "Rejeter" }).isVisible()) {
    await last.getByRole("button", { name: "Rejeter" }).click();
    await last.getByLabel("Motif du rejet").fill("Déjà traité avec un partenaire.");
    await last.getByRole("button", { name: "Rejeter" }).click();
    await expect(last.getByText("Rejetée")).toBeVisible();
  }
  for (const index of [0, 1]) {
    const accept = recommendations.nth(index).getByRole("button", { name: "Accepter" });
    if (await accept.isVisible()) {
      await accept.click();
      await expect(recommendations.nth(index).getByText("Acceptée")).toBeVisible();
    }
  }
  await page.getByRole("button", { name: /Générer le plan|Régénérer le plan/ }).click();
  await expect(page.getByText("Jours 1–30")).toBeVisible();
  await page.getByRole("button", { name: "Soumettre à validation" }).click();
  await page.getByRole("button", { name: "Valider (GUDE-PME)" }).click();
  await expect(page.getByText("En attente d'acceptation par la PME")).toBeVisible();
});

test("sans compte PME, le conseiller enregistre l'acceptation recueillie en entretien", async ({ page }) => {
  await loginStaff(page, "konan.conseiller@demo.test");
  await page.getByRole("link", { name: "PME", exact: true }).click();
  await page.getByRole("link", { name: /Délices/ }).first().click();
  await page.getByRole("tab", { name: "Plan & actions" }).click();
  const record = page.getByRole("button", { name: "Enregistrer l'acceptation de la PME" });
  await page.getByText(/Plan d'accompagnement|Recommandations/).first().waitFor();
  test.skip(!(await record.isVisible()), "Aucun plan en attente d'acceptation.");
  await record.click();
  await page.getByLabel(/Comment la PME a-t-elle accepté le plan/).fill("Accepté en entretien avec le gérant, PV signé.");
  await page.getByRole("button", { name: "Confirmer" }).click();
  await expect(page.getByText(/acceptation de la PME enregistrée par Konan Brou/)).toBeVisible();
});

test("la dirigeante démarre une action de son plan et dépose le livrable", async ({ page }) => {
  await loginPme(page, "aya.dirigeante@demo.test");
  await expect(page.getByRole("heading", { name: "Que dois-je faire maintenant ?" })).toBeVisible();
  await page.getByRole("link", { name: "Voir tout mon plan" }).click();
  await expect(page.getByRole("heading", { name: "Mon plan d'accompagnement" })).toBeVisible();
  await expect(page.getByText(/action\(s\) terminée\(s\) sur/)).toBeVisible();
  await page.getByRole("link", { name: /Contrôle interne et caisse/ }).click();
  await expect(page.getByRole("heading", { name: "Pourquoi cette action ?" })).toBeVisible();

  const start = page.getByRole("button", { name: "Je démarre cette action" });
  if (await start.isVisible()) await start.click();
  await expect(page.getByText("En cours").first()).toBeVisible();

  const deliverable = page.getByTestId("deliverable").filter({ hasText: CAISSE });
  await deliverable.getByText("Comment le préparer").click();
  await expect(deliverable.getByText("Ce que votre conseiller vérifiera :")).toBeVisible();
  const upload = deliverable.locator('input[type="file"]:not([capture])');
  test.skip((await upload.count()) === 0, "Livrable déjà déposé : relancer seed_demo sur une base neuve.");
  await upload.setInputFiles({ name: "procedure-caisse.pdf", mimeType: "application/pdf", buffer: demoPdf("PROCEDURE DE CAISSE - DEMONSTRATION") });
  await expect(deliverable.getByText("En vérification")).toBeVisible();
});

test("le conseiller vérifie le livrable : l'action avance", async ({ page }) => {
  await loginStaff(page, "konan.conseiller@demo.test");
  await page.getByRole("link", { name: "Documents à vérifier" }).click();
  await page.getByRole("main").getByRole("list").or(page.getByText("Aucun document en attente")).first().waitFor();
  const item = page.getByRole("link").filter({ hasText: CAISSE }).filter({ hasText: "Boutik Plus" });
  test.skip((await item.count()) === 0, "Aucun livrable en attente : lancer d'abord le test de dépôt.");
  await item.first().click();
  await page.getByLabel("Conforme", { exact: true }).check();
  await page.getByRole("button", { name: "Enregistrer la décision" }).click();
  await expect(page).toHaveURL(/\/verifications$/);

  await page.getByRole("link", { name: "PME", exact: true }).click();
  await page.getByRole("link", { name: /Boutik Plus/ }).first().click();
  await page.getByRole("tab", { name: "Plan & actions" }).click();
  const card = page.getByRole("link").filter({ hasText: "Contrôle interne et caisse" });
  await expect(card.getByText("Documents 1/2")).toBeVisible();
  await card.click();
  await expect(page.getByTestId("deliverable").filter({ hasText: CAISSE }).getByText("Conforme")).toBeVisible();
  await expect(page.getByText("Document demandé").first()).toBeVisible();
});

test("l'administrateur teste une règle de recommandation sur le portefeuille", async ({ page }) => {
  await loginStaff(page, "admin@demo.test");
  await page.getByRole("link", { name: "Accompagnement" }).click();
  await expect(page.getByRole("heading", { name: "Accompagnement" })).toBeVisible();
  const version = page.getByTestId("rule-version").first();
  await version.getByRole("button", { name: "Tester" }).click();
  await expect(version.getByText(/PME concernée\(s\) sur \d+/)).toBeVisible();
  await page.getByRole("tab", { name: "Offres" }).click();
  await expect(page.getByText("Tableau de trésorerie").first()).toBeVisible();
});
