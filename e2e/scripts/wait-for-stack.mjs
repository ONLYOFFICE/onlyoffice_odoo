// Copyright (C) 2026 Ascensio System SIA
// Wait until the Document Server (with its generated fonts) and Odoo answer over HTTP.
const ODOO_URL = process.env.E2E_ODOO_URL ?? "http://localhost:8069"
const DS_URL = process.env.E2E_DS_PUBLIC_URL ?? "http://localhost:8080/"

async function waitFor(url) {
  for (let attempt = 0; attempt < 100; attempt++) {
    const ok = await fetch(url, { signal: AbortSignal.timeout(5_000) })
      .then((response) => response.ok)
      .catch(() => false)
    if (ok) {
      console.log(`ready: ${url}`)
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 3_000))
  }
  console.error(`timed out waiting for ${url}`)
  process.exit(1)
}

await waitFor(new URL("healthcheck", DS_URL).href)
await waitFor(new URL("sdkjs/common/AllFonts.js", DS_URL).href) // Generated on start; the editor cannot load without it
await waitFor(new URL("web/login", ODOO_URL).href)
