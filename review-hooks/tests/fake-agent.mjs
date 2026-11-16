// review-hooks/tests/fake-agent.mjs - stands in for an AI CLI in tests.
// Behaviour comes from FAKE_AGENT_MODE: ok | fail | notloggedin | empty | hang
// Every call appends one JSON line to FAKE_AGENT_LOG (args, cwd, stdin size).
import fs from "node:fs";

const mode = process.env.FAKE_AGENT_MODE || "ok";
let input = "";
try { input = fs.readFileSync(0, "utf8"); } catch { /* no stdin */ }
if (process.env.FAKE_AGENT_LOG) {
  fs.appendFileSync(process.env.FAKE_AGENT_LOG, JSON.stringify({
    args: process.argv.slice(2), cwd: process.cwd(), stdinBytes: Buffer.byteLength(input),
    hasDiff: input.includes("```diff"), sawUncommitted: fs.existsSync("UNCOMMITTED.txt"),
  }) + "\n");
}
switch (mode) {
  case "fail": console.error("fake: model error"); process.exit(3);
  case "notloggedin": console.log("Not logged in · Please run /login"); process.exit(1);
  case "empty": process.exit(0);
  case "hang": setTimeout(() => {}, 1e9); break;
  default:
    console.log("## Findings\n\n- **nit** `app.js:1`: example finding.\n\nVERDICT: approve");
}
