// Start de backend voor e2e-tests met een verse tijdelijke datamap.
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const backend = path.join(root, "backend");
const py = process.platform === "win32" ? path.join(backend, ".venv", "Scripts", "python.exe") : path.join(backend, ".venv", "bin", "python");
const dataDir = mkdtempSync(path.join(tmpdir(), "vetera-e2e-"));
const child = spawn(py, ["run.py"], {
  cwd: backend,
  stdio: "inherit",
  env: { ...process.env, VETERA_PORT: "3100", VETERA_DATA_DIR: dataDir, ANTHROPIC_API_KEY: "", VETERA_ANTHROPIC_API_KEY: "" },
});
const stop = () => child.kill();
process.on("SIGTERM", stop);
process.on("SIGINT", stop);
process.on("exit", stop);
