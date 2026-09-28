// Copyright (C) 2026 Ascensio System SIA
// Wait until the Document Server has finished starting and Odoo answers over HTTP.
const ODOO_URL = process.env.E2E_ODOO_URL ?? "http://localhost:8069"
const DS_URL = process.env.E2E_DS_PUBLIC_URL ?? "http://localhost:8080/"

async function waitFor(url) {
  for (let attempt = 0; attempt < 200; attempt++) {
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

// On start the Document Server generates AllFonts.js, then presentation themes (minutes), then restarts docservice and
// converter: meanwhile nginx answers 502. Waiting for a response.
await waitFor(new URL("sdkjs/common/AllFonts.js.gz", DS_URL).href)
await waitFor(new URL("healthcheck", DS_URL).href) // Docservice is up again after the restart
await waitFor(new URL("web/login", ODOO_URL).href)
