import { expect, test } from "@playwright/test";

const email = process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const password = process.env.E2E_ADMIN_PASSWORD ?? "ChangeMe123!";

async function login(page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/dashboard/);
  await expect(page.getByText("MISP ingestion")).toBeVisible();
}

test("login, queues, AI workflow, reviews, catalog, and health pages render", async ({ page }) => {
  await login(page);

  for (const [path, title] of [
    ["/dashboard", "Dashboard"],
    ["/threats", "Threat Queue"],
    ["/ai", "AI"],
    ["/ai-workflow", "AI Workflow"],
    ["/reviews", "Review Queue"],
    ["/detections", "Detection"],
    ["/attack", "ATT&CK"],
    ["/health", "System Health"]
  ]) {
    await page.goto(path);
    await expect(page.getByText(title, { exact: false }).first()).toBeVisible();
    await page.screenshot({ path: `artifacts/e2e/${path.replace("/", "") || "dashboard"}.png`, fullPage: true });
  }
});

test("threat queue ingestion controls are available", async ({ page }) => {
  await login(page);
  await page.goto("/threats");
  await expect(page.getByRole("button", { name: /Refresh/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Ingest Selected/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Ingest All New/i })).toBeVisible();
});

test("unauthorized user is redirected to login", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/login/);
});
