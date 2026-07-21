/**
 * Build a Node.js Single Executable Application (SEA) for the Baileys sidecar.
 *
 * Steps:
 *   1. Bundle the TS source via esbuild → dist/index.cjs
 *   2. Generate the SEA blob via `node --experimental-sea-config`
 *   3. Copy `node.exe` to `baileys-sidecar.exe`
 *   4. Inject the blob via `postject`
 *
 * Output: baileys-sidecar.exe (~80MB, includes full Node runtime)
 *
 * Requires: Node 20+ on PATH (any modern version).
 */

const { execSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = __dirname;
const BLOB = path.join(ROOT, "baileys-sidecar.blob");
const OUT_EXE = path.join(ROOT, "baileys-sidecar.exe");
const SEA_CONFIG = path.join(ROOT, "sea-config.json");
const NODE_EXE = process.execPath;

function run(cmd, opts = {}) {
  console.log(`> ${cmd}`);
  execSync(cmd, { stdio: "inherit", cwd: ROOT, ...opts });
}

function tryUnlink(p) {
  try { fs.unlinkSync(p); } catch { /* ignore */ }
}

(async () => {
  // 1. Bundle
  run("npm run build");

  // 2. Generate blob
  tryUnlink(BLOB);
  run(`node --experimental-sea-config "${SEA_CONFIG}"`);

  // 3. Copy node.exe
  tryUnlink(OUT_EXE);
  fs.copyFileSync(NODE_EXE, OUT_EXE);
  console.log(`Copied ${NODE_EXE} → ${OUT_EXE}`);

  // 4. Inject blob
  run(
    `npx --yes postject "${OUT_EXE}" NODE_SEA_BLOB "${BLOB}" ` +
      `--sentinel-fuse NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2`
  );

  console.log(`\n✓ Built ${OUT_EXE}`);
})().catch((err) => {
  console.error("SEA build failed:", err.message);
  process.exit(1);
});