// review-hooks/lib/agent.mjs - run an AI CLI (or any command) safely.
//
// The agent gets the review request on stdin and must print Markdown on
// stdout. Nothing here decides pass/fail from what the model says.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";

const isWin = process.platform === "win32";

/** Resolve a command on PATH the way a shell would (PATHEXT on Windows). */
export function findExecutable(name, envPath = process.env.PATH || "") {
  if (path.isAbsolute(name) || name.includes("/") || name.includes("\\"))
    return fs.existsSync(name) ? name : null;
  const exts = isWin
    ? (process.env.PATHEXT || ".COM;.EXE;.BAT;.CMD").split(";").filter(Boolean)
    : [""];
  for (const raw of envPath.split(path.delimiter)) {
    const dir = raw.replace(/^"|"$/g, "");
    if (!dir) continue;
    for (const ext of exts) {
      const p = path.join(dir, name + ext);
      try {
        if (!fs.statSync(p).isFile()) continue;
        if (!isWin) fs.accessSync(p, fs.constants.X_OK);
        return p;
      } catch { /* keep looking */ }
    }
  }
  return null;
}

/**
 * Flags for Claude Code's headless mode. The code under review is untrusted:
 * without the isolation flags, `claude -p` loads hooks from the repo's
 * .claude/settings.json and starts servers from its .mcp.json without asking
 * (shown against the real CLI by tests/probe-claude-isolation.sh).
 */
export function claudeArgs(settingsFile, extra = []) {
  return [
    "-p", "Review the change described on standard input.",
    "--tools", "Read,Grep,Glob",                       // only these tools exist
    "--allowedTools", "Read", "Grep", "Glob",          // and need no approval
    "--permission-mode", "dontAsk",                    // anything else is denied
    "--setting-sources", "user",                       // ignore the repo's .claude/
    "--strict-mcp-config",                             // ignore the repo's .mcp.json
    "--settings", settingsFile,                        // {"disableAllHooks": true}
    "--no-session-persistence",                        // no transcript on disk
    ...extra,
  ];
}

/** Build {command, args, cleanup} for the configured agent. */
export function agentCommand(cfg) {
  if (cfg.agent === "claude" || cfg.agent == null) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "review-hooks-claude-"));
    const settingsFile = path.join(dir, "settings.json");
    fs.writeFileSync(settingsFile, JSON.stringify({ disableAllHooks: true }));
    return {
      name: "claude",
      command: "claude",
      args: claudeArgs(settingsFile, cfg.claudeExtraArgs || []),
      cleanup: () => fs.rmSync(dir, { recursive: true, force: true }),
    };
  }
  if (typeof cfg.agent === "object" && cfg.agent.command) {
    return {
      name: cfg.agent.name || path.basename(cfg.agent.command),
      command: cfg.agent.command,
      args: cfg.agent.args || [],
      cleanup: () => {},
    };
  }
  throw new Error(`agent must be "claude" or { "command": ..., "args": [...] }`);
}

function killTree(child) {
  if (!child.pid) return;
  if (isWin) spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { windowsHide: true });
  else {
    try { process.kill(-child.pid, "SIGKILL"); } catch { try { child.kill("SIGKILL"); } catch { /* gone */ } }
  }
}

/**
 * @returns {Promise<{status: number|null, stdout: string, stderr: string,
 *   timedOut: boolean, error?: {code: string, message: string}}>}
 */
export function runAgent({ command, args, input, cwd, timeoutMs, env = process.env }) {
  return new Promise(resolve => {
    const resolved = findExecutable(command, env.PATH ?? env.Path);
    if (!resolved)
      return resolve({ status: null, stdout: "", stderr: "", timedOut: false,
        error: { code: "ENOENT", message: `${command} not found on PATH` } });

    let file = resolved, argv = args;
    const opts = { cwd, env, windowsHide: true, stdio: ["pipe", "pipe", "pipe"] };
    if (isWin && /\.(cmd|bat)$/i.test(resolved)) {
      // npm installs CLIs as .cmd launchers, which Windows cannot start
      // without cmd.exe. Refuse arguments cmd.exe would reinterpret.
      for (const a of [resolved, ...args])
        if (/["%^&|<>!\r\n]/.test(a))
          return resolve({ status: null, stdout: "", stderr: "", timedOut: false,
            error: { code: "EUNSAFE", message: `cannot pass ${JSON.stringify(a)} through cmd.exe` } });
      file = process.env.ComSpec || "cmd.exe";
      argv = ["/d", "/s", "/c", `"${[resolved, ...args].map(a => `"${a}"`).join(" ")}"`];
      opts.windowsVerbatimArguments = true;
    } else if (!isWin) {
      opts.detached = true; // own process group, so a timeout kills the whole tree
    }

    let stdout = "", stderr = "", timedOut = false, done = false;
    const LIMIT = 10 * 1024 * 1024;
    let child;
    try { child = spawn(file, argv, opts); }
    catch (e) { return resolve({ status: null, stdout, stderr, timedOut, error: { code: e.code || "ESPAWN", message: e.message } }); }

    const timer = setTimeout(() => { timedOut = true; killTree(child); }, timeoutMs);
    const finish = r => { if (done) return; done = true; clearTimeout(timer); resolve(r); };
    child.stdout.on("data", d => { if (stdout.length < LIMIT) stdout += d; });
    child.stderr.on("data", d => { if (stderr.length < LIMIT) stderr += d; });
    child.on("error", e => finish({ status: null, stdout, stderr, timedOut, error: { code: e.code || "ESPAWN", message: e.message } }));
    child.on("close", status => finish({ status, stdout, stderr, timedOut }));
    child.stdin.on("error", () => { /* agent closed stdin early */ });
    child.stdin.end(input);
  });
}
