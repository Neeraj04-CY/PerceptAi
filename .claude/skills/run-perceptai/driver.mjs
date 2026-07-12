#!/usr/bin/env node
/**
 * PerceptAI agent driver — drives the REAL running platform.
 *
 * No mocks. It signs up/signs in against the live FastAPI backend (real
 * Supabase), injects the real JWT into the browser the way the app does
 * (localStorage + `perceptai_token` cookie — the Next.js middleware gates
 * /dashboard on the cookie), then navigates the real dashboard and screenshots.
 *
 *   node driver.mjs health          API reachable + engine/db status
 *   node driver.mjs auth            real signup/signin -> prints a JWT
 *   node driver.mjs shot [pages...] screenshot dashboard pages (default: all)
 *   node driver.mjs smoke           health + auth + screenshot every page
 *
 * Env overrides: API (default http://127.0.0.1:8000), WEB (http://localhost:3000)
 */
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SHOTS = join(HERE, "shots");
const API = process.env.API || "http://127.0.0.1:8000";
const WEB = process.env.WEB || "http://localhost:3000";

// A stable throwaway account. Signup is idempotent-ish: if it already exists we
// just sign in. Nothing here touches a customer tenant.
const EMAIL = process.env.SMOKE_EMAIL || "agent-smoke@perceptai.dev";
const PASSWORD = process.env.SMOKE_PASSWORD || "SmokeTest123!";

// Every page the dashboard exposes. `run` is intentionally NOT auto-driven:
// starting a task takes over the real mouse/keyboard on this machine.
const PAGES = {
  dashboard: "/dashboard",
  workforce: "/dashboard/workforce",
  evidence: "/dashboard/evidence",
  operations: "/dashboard/operations",
  templates: "/dashboard/templates",
  approvals: "/dashboard/approvals",
  answers: "/dashboard/answers",
  settings: "/dashboard/settings",
  analytics: "/dashboard/analytics",
  runners: "/dashboard/runners",
  org: "/dashboard/org",
  keys: "/dashboard/keys",
};

const j = (r) => r.json();

/**
 * Wait until the page has actually PAINTED its data.
 *
 * Every dashboard page is a client component that fetches after mount and shows
 * `animate-pulse` skeletons meanwhile. `networkidle` alone is not enough — you
 * will screenshot skeletons (Studio and the workflow editor do this reliably).
 * Wait for the skeletons to go away, then let React paint.
 */
async function settle(page) {
  await page.waitForLoadState("networkidle", { timeout: 20000 }).catch(() => {});
  await page
    .waitForFunction(() => document.querySelectorAll(".animate-pulse").length === 0,
                     { timeout: 15000 })
    .catch(() => {}); // empty states legitimately have none; never hang on this
  await page.waitForTimeout(500);
}

async function health() {
  const r = await fetch(`${API}/api/v1/platform/health`).then(j);
  console.log("API health:", JSON.stringify(r));
  if (r.status !== "healthy") throw new Error("API not healthy");
  return r;
}

async function token() {
  // Signup returns a token directly; if the user exists, fall back to signin.
  const body = JSON.stringify({ email: EMAIL, password: PASSWORD, name: "Agent Smoke" });
  const hdr = { "Content-Type": "application/json" };
  let res = await fetch(`${API}/api/v1/auth/signup`, { method: "POST", headers: hdr, body });
  let data = await res.json().catch(() => ({}));
  if (!data.access_token) {
    res = await fetch(`${API}/api/v1/auth/signin`, {
      method: "POST", headers: hdr,
      body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
    });
    data = await res.json().catch(() => ({}));
  }
  if (!data.access_token) throw new Error(`auth failed: ${JSON.stringify(data).slice(0, 200)}`);
  return data.access_token;
}

async function shot(names) {
  const tok = await token();
  mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 1200 },
    colorScheme: "dark",
  });
  // The app reads the JWT from localStorage; middleware.ts gates /dashboard on
  // the cookie. Set BOTH or you get bounced to /signin.
  await ctx.addCookies([{ name: "perceptai_token", value: tok, url: WEB }]);
  await ctx.addInitScript((t) => localStorage.setItem("perceptai_token", t), tok);

  const failures = [];
  for (const name of names) {
    const path = PAGES[name];
    if (!path) { console.log(`skip unknown page: ${name}`); continue; }
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(`${WEB}${path}`, { waitUntil: "domcontentloaded" });
    await settle(page);
    const url = page.url();
    const bounced = url.includes("/signin");
    const file = join(SHOTS, `${name}.png`);
    await page.screenshot({ path: file, fullPage: true });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2);
    const status = bounced ? "BOUNCED-TO-SIGNIN" : errors.length ? `PAGEERR: ${errors[0]}` : "ok";
    if (bounced || errors.length) failures.push(`${name}: ${status}`);
    console.log(`${name.padEnd(10)} ${status}${overflow ? "  H-OVERFLOW" : ""}  -> shots/${name}.png`);
    await page.close();
  }
  await browser.close();
  writeFileSync(join(SHOTS, "_summary.txt"),
    failures.length ? failures.join("\n") : "all pages ok\n");
  if (failures.length) { console.error("\nFAILURES:\n" + failures.join("\n")); process.exit(1); }
}

/**
 * A real click-through: Studio -> pick a template -> workflow editor.
 * This CREATES a workflow row (POST /workflows) in the real DB. It is pure
 * CRUD — it does NOT execute anything, so it never touches the mouse/screen.
 */
async function flow() {
  const tok = await token();
  mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 }, colorScheme: "dark" });
  await ctx.addCookies([{ name: "perceptai_token", value: tok, url: WEB }]);
  await ctx.addInitScript((t) => localStorage.setItem("perceptai_token", t), tok);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.log("PAGEERR:", e.message));

  await page.goto(`${WEB}/dashboard/templates`, { waitUntil: "domcontentloaded" });
  await settle(page);
  // IMPORTANT: after this has run once, the workflow it created also appears in
  // "Your workflows" — so the template's title matches TWICE and getByText()
  // throws a strict-mode violation. Template cards are <button>, saved
  // workflows are <a>. Target the button so the driver stays idempotent.
  await page.getByRole("button", { name: /Post invoice to the ERP/ }).click();

  // Creating from a template navigates to /dashboard/studio/<new-id>
  await page.waitForURL(/\/dashboard\/studio\/[0-9a-f-]{8,}/, { timeout: 20000 });
  // Wait for the EDITOR to paint, not just for the network. Playwright locators
  // auto-wait, so an assertion can pass while the screenshot still shows a
  // skeleton — screenshot only after the real textarea is visible.
  await page.locator("textarea").first().waitFor({ state: "visible", timeout: 20000 });
  await settle(page);
  await page.screenshot({ path: join(SHOTS, "flow-workflow-editor.png"), fullPage: true });

  const instruction = await page.locator("textarea").first().inputValue();
  console.log("created workflow:", page.url());
  console.log("instruction loaded:", JSON.stringify(instruction.slice(0, 70)));
  if (!instruction.includes("invoice")) throw new Error("template did not load into the editor");
  console.log("-> shots/flow-workflow-editor.png");
  await browser.close();
}

const [cmd = "smoke", ...rest] = process.argv.slice(2);
const names = rest.length ? rest : Object.keys(PAGES);

if (cmd === "health") await health();
else if (cmd === "auth") console.log(await token());
else if (cmd === "shot") await shot(names);
else if (cmd === "flow") await flow();
else if (cmd === "smoke") { await health(); await shot(names); await flow(); console.log("\nSMOKE OK"); }
else { console.error(`unknown command: ${cmd}`); process.exit(2); }
