import { spawn } from "child_process";
import fs from "fs";
import path from "path";

const CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9222;
const APP_PORT = 8008;
const OUT_DIR = path.resolve("docs/screenshots");

fs.mkdirSync(OUT_DIR, { recursive: true });

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function sendCdp(ws, method, params = {}) {
  const id = Math.floor(Math.random() * 1000000);
  return new Promise((resolve, reject) => {
    const handler = (evt) => {
      const msg = JSON.parse(evt.data.toString());
      if (msg.id === id) {
        ws.removeEventListener("message", handler);
        if (msg.error) reject(new Error(msg.error.message));
        else resolve(msg.result);
      }
    };
    ws.addEventListener("message", handler);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(ws, expression) {
  const res = await sendCdp(ws, "Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  return res.result?.value;
}

async function waitForSelector(ws, selector, timeout = 10000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const exists = await evaluate(
      ws,
      `!!document.querySelector(${JSON.stringify(selector)})`
    );
    if (exists) return true;
    await sleep(200);
  }
  throw new Error(`Timeout waiting for selector: ${selector}`);
}

async function waitForCondition(ws, fnStr, timeout = 10000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const res = await evaluate(ws, `(${fnStr})()`);
    if (res) return res;
    await sleep(200);
  }
  throw new Error(`Timeout waiting for condition: ${fnStr}`);
}

async function capture(ws, filename, clip = null) {
  const params = { format: "png" };
  if (clip) params.clip = clip;
  const res = await sendCdp(ws, "Page.captureScreenshot", params);
  const buffer = Buffer.from(res.data, "base64");
  const filePath = path.join(OUT_DIR, filename);
  fs.writeFileSync(filePath, buffer);
  console.log(`Saved screenshot: ${filePath} (${buffer.length} bytes)`);
}

async function main() {
  console.log("Launching headless Chrome on port 9222...");
  const chrome = spawn(
    CHROME_PATH,
    [
      "--headless=new",
      `--remote-debugging-port=${PORT}`,
      "--disable-gpu",
      "--disable-extensions",
      "--no-sandbox",
      "--user-data-dir=/tmp/chrome-shot-profile",
      "--window-size=1440,960",
      "about:blank",
    ],
    { stdio: "ignore" }
  );

  await sleep(1500);

  try {
    const listRes = await fetch(`http://127.0.0.1:${PORT}/json/list`);
    const list = await listRes.json();
    const tab = list.find((x) => x.type === "page") || list[0];
    const ws = new WebSocket(tab.webSocketDebuggerUrl);

    await new Promise((resolve, reject) => {
      ws.addEventListener("open", resolve);
      ws.addEventListener("error", reject);
    });

    await sendCdp(ws, "Page.enable");
    await sendCdp(ws, "Runtime.enable");
    await sendCdp(ws, "Emulation.setDeviceMetricsOverride", {
      width: 1440,
      height: 960,
      deviceScaleFactor: 2,
      mobile: false,
    });

    console.log("1. Capturing Overview...");
    await sendCdp(ws, "Page.navigate", { url: `http://127.0.0.1:${APP_PORT}/#overview` });
    await waitForSelector(ws, "#overview-chart svg circle");
    await waitForCondition(
      ws,
      `() => document.getElementById("ov-samples")?.textContent !== "—"`
    );
    await sleep(800);
    await capture(ws, "overview.png");

    console.log("2. Capturing Sample Explorer...");
    await evaluate(ws, `render("samples")`);
    await waitForSelector(ws, "#sample-rows tr td strong");
    await sleep(600);
    await capture(ws, "sample-explorer.png");

    console.log("3. Capturing Sample Detail...");
    await evaluate(ws, `state.currentSample = "AST-LUNAR-2dd1d42aee7d4148"; render("sampleDetail");`);
    await waitForSelector(ws, "#sample-detail .data-table tr td");
    // Trigger measurement inspection for the first analysis
    await evaluate(ws, `
      const inspectBtn = document.querySelector("[data-view-analysis]");
      if (inspectBtn) inspectBtn.click();
    `);
    await sleep(800);
    await capture(ws, "sample-detail.png");

    console.log("4. Capturing Geochemical Workbench...");
    await evaluate(ws, `render("workbench")`);
    await waitForSelector(ws, "#workbench-chart svg circle");
    await waitForSelector(ws, "#wb-table tr td");
    // Click a point on the chart to populate the inspector
    await evaluate(ws, `
      const pt = document.querySelector("#workbench-chart circle.point");
      if (pt) pt.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    `);
    await sleep(800);
    await capture(ws, "workbench.png");

    console.log("5. Capturing REE Laboratory...");
    await evaluate(ws, `render("ree")`);
    await sleep(800);
    await evaluate(ws, `
      (async () => {
        const d = await api("samples/AST-LUNAR-ca384db9d3fbddc5/analyses?limit=50");
        document.getElementById("ree-samples").innerHTML =
          '<tr><th colspan="4">Select analyses from S2537 · each curve remains tied to a source row <button class="text-link" id="ree-back-samples" style="margin-left:12px">← Back to samples</button></th></tr>' +
          d.rows.map((a, idx) => '<tr><td><label><input type="checkbox" data-ree-analysis="' + a.analysis_id + '" ' + (idx < 5 ? 'checked' : '') + '> ' + a.analysis_id + '</label></td><td>' + (a.analyzed_material || 'bulk') + '</td><td>' + a.measurement_count + ' measurements</td><td>' + (a.citation_id || '—') + '</td></tr>').join("");
        await plotRee();
      })()
    `);
    await waitForSelector(ws, "#ree-chart svg polyline");
    await evaluate(ws, `
      document.querySelector(".section-heading:has(#ree-plot)")?.scrollIntoView() || document.getElementById("ree-chart").scrollIntoView();
    `);
    await sleep(800);
    await capture(ws, "ree-laboratory.png");

    console.log("6. Capturing Basalt Observatory...");
    await evaluate(ws, `render("basalts")`);
    await waitForSelector(ws, "#basalt-feo svg circle");
    await waitForSelector(ws, "#basalt-rows tr td");
    await sleep(1000);
    await capture(ws, "basalt-observatory.png");

    console.log("7. Capturing Data Quality Observatory...");
    await evaluate(ws, `render("quality")`);
    await waitForSelector(ws, "#dq-units tr td");
    await waitForSelector(ws, "#dq-flags-table tr td");
    await sleep(800);
    await capture(ws, "data-quality.png");

    ws.close();
    console.log("All screenshots captured successfully!");
  } finally {
    chrome.kill();
  }
}

main().catch((err) => {
  console.error("Capture failed:", err);
  process.exit(1);
});
