import { spawn } from "node:child_process";
import { mkdirSync, existsSync, createWriteStream } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const frontend = fileURLToPath(new URL(".", import.meta.url));
const root = fileURLToPath(new URL("..", import.meta.url));
const externalRoot = "/Volumes/XcodeSSD";
const dataRoot = join(externalRoot, "Hollow-DevData");

if (!existsSync(join(root, "backend")) || !existsSync(dataRoot)) {
  console.error("LIFELINE or Hollow-DevData is unavailable. Mount XcodeSSD first.");
  process.exit(1);
}

for (const path of [
  join(dataRoot, "caches", "python-pycache"),
  join(dataRoot, "caches", "pip"),
  join(dataRoot, "caches", "npm"),
  join(dataRoot, "logs"),
  join(dataRoot, "temp"),
]) {
  mkdirSync(path, { recursive: true });
}

const environment = {
  ...process.env,
  PYTHONPYCACHEPREFIX: join(dataRoot, "caches", "python-pycache"),
  PIP_CACHE_DIR: join(dataRoot, "caches", "pip"),
  npm_config_cache: join(dataRoot, "caches", "npm"),
  TMPDIR: join(dataRoot, "temp"),
};
const log = createWriteStream(join(dataRoot, "logs", "dev-server.log"), { flags: "a" });
const api = spawn(
  join(root, "backend", ".venv", "bin", "python"),
  ["-m", "engine.api"],
  { cwd: join(root, "backend"), env: environment, stdio: ["ignore", "pipe", "pipe"] },
);
const vite = spawn(
  process.execPath,
  [join(frontend, "node_modules", "vite", "bin", "vite.js"), "--host", "127.0.0.1"],
  { cwd: frontend, env: environment, stdio: ["ignore", "pipe", "pipe"] },
);
for (const child of [api, vite]) {
  child.stdout.pipe(process.stdout);
  child.stdout.pipe(log, { end: false });
  child.stderr.pipe(process.stderr);
  child.stderr.pipe(log, { end: false });
}

let stopping = false;
let exited = 0;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  api.kill("SIGTERM");
  vite.kill("SIGTERM");
  process.exitCode = code;
  if (exited === 2) log.end();
}

for (const child of [api, vite]) {
  child.on("error", (error) => {
    console.error(`LIFELINE development process failed: ${error.message}`);
    stop(1);
  });
  child.on("exit", (code) => {
    exited += 1;
    if (!stopping) stop(code ?? 1);
    else if (exited === 2) log.end();
  });
}

process.on("SIGINT", () => stop(0));
process.on("SIGTERM", () => stop(0));
