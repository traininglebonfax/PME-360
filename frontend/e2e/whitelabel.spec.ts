import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, type Page, test } from "@playwright/test";

import { loginPme, loginStaff } from "./helpers";

const SLUG = "banque-atlantique";
const BACKEND = path.resolve(__dirname, "../../backend");
const PYTHON = path.join(BACKEND, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");

// Écrans de l'équipe parcourus : aucun ne doit laisser apparaître l'organisation d'origine.
const STAFF_PAGES = [
  "/tableau-de-bord",
  "/pme",
  "/portefeuille",
  "/analyses",
  "/rapports",
  "/verifications",
  "/alertes",
  "/referentiel",
  "/conformite",
  "/accompagnement",
  "/modeles-notification",
  "/workflows",
  "/identite",
  "/programmes",
  "/utilisateurs",
  "/audit",
  "/journal",
];

async function expectNoGude(page: Page, where: string) {
  await page.waitForLoadState("networkidle");
  const text = await page.locator("body").innerText();
  expect(text.toUpperCase(), `« GUDE » visible sur ${where}`).not.toContain("GUDE");
  expect(await page.title(), `titre de ${where}`).not.toContain("GUDE");
}

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  // Démo du prospect (idempotente : relancer ne duplique rien).
  execFileSync(PYTHON, ["manage.py", "create_demo_org", "--nom", "Banque Atlantique", "--couleur", "#0055A4"], {
    cwd: BACKEND,
    stdio: "ignore",
    timeout: 180_000,
  });
});

test("la démo du prospect ne laisse apparaître aucune trace de l'organisation d'origine (équipe)", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto(`/connexion?org=${SLUG}`);
  await expect(page.getByRole("tab", { name: "Équipe Banque Atlantique" })).toBeVisible();
  await expectNoGude(page, "la page de connexion");

  await loginStaff(page, `admin.${SLUG}@demo.test`);
  await expect(page).toHaveTitle("PME360");
  for (const href of STAFF_PAGES) {
    await page.goto(href);
    await expectNoGude(page, href);
  }
  // Une fiche PME et son plan.
  await page.goto("/pme");
  await page.getByRole("link", { name: "Boutik Plus Distribution SARL" }).first().click();
  await expectNoGude(page, "la fiche PME");
  // Couleur de la marque appliquée.
  const brandColor = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--color-brand-600").trim());
  expect(brandColor.toLowerCase()).toBe("#0055a4");

  // Déconnexion : retour à la page de connexion du prospect.
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page).toHaveURL(new RegExp(`/connexion\\?org=${SLUG}$`));
  await expect(page.getByRole("tab", { name: "Équipe Banque Atlantique" })).toBeVisible();
});

test("la démo du prospect côté PME est à son nom", async ({ page }) => {
  await loginPme(page, `aya.dirigeante.${SLUG}@demo.test`);
  await expect(page.getByText("Mon conseiller Banque Atlantique")).toBeVisible();
  await expectNoGude(page, "l'espace PME");
  for (const href of ["/espace/plan", "/espace/documents", "/espace/diagnostic"]) {
    await page.goto(href);
    await expectNoGude(page, href);
  }
});

test("La démo principale est neutre et la page de connexion neutre reste neutre", async ({ page }) => {
  await page.goto("/connexion?org=pme360-demo");
  await expect(page.getByRole("tab", { name: "Équipe PME360" })).toBeVisible();
  await expectNoGude(page, "la connexion de la démo principale");
  await page.goto("/connexion");
  await expect(page.getByRole("tab", { name: "Équipe d'accompagnement" })).toBeVisible();
  await expectNoGude(page, "la page de connexion neutre");
});
