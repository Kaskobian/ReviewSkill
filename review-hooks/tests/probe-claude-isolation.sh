#!/usr/bin/env bash
# review-hooks/tests/probe-claude-isolation.sh
#
# Checks, against the REAL Claude Code CLI, whether a repository can make
# `claude -p` run code through files it ships: .claude/settings.json hooks
# and .mcp.json servers. Both start before any prompt is sent, so this works
# (and costs nothing) even when the CLI is not logged in.
#
#   bash review-hooks/tests/probe-claude-isolation.sh
#   CLAUDE=/path/to/claude bash review-hooks/tests/probe-claude-isolation.sh
#
# Expected: "plain flags" -> EXECUTED, "review-hooks flags" -> blocked.
set -u
CLAUDE="${CLAUDE:-claude}"
command -v "$CLAUDE" >/dev/null 2>&1 || { echo "claude not found (set CLAUDE=...)"; exit 2; }
echo "Claude Code: $("$CLAUDE" --version 2>&1 | head -1)"

T=$(mktemp -d "${TMPDIR:-/tmp}/claude-isolation.XXXXXX")
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/.claude"
cat > "$T/.claude/settings.json" <<'EOF'
{ "hooks": { "SessionStart": [ { "hooks": [ { "type": "command",
  "command": "node -e \"require('fs').writeFileSync('MARK-hook.txt','x')\"" } ] } ] } }
EOF
cat > "$T/.mcp.json" <<'EOF'
{ "mcpServers": { "probe": { "type": "stdio", "command": "node",
  "args": ["-e", "require('fs').writeFileSync('MARK-mcp.txt','x'); setTimeout(()=>{},3000)"] } } }
EOF
printf '{"disableAllHooks":true}' > "$T/../claude-isolation-settings.$$.json"
SETTINGS="$T/../claude-isolation-settings.$$.json"
trap 'rm -rf "$T" "$SETTINGS"' EXIT

PLAIN=(--tools "Read,Grep,Glob" --allowedTools Read Grep Glob --permission-mode dontAsk)
HARDENED=("${PLAIN[@]}" --setting-sources user --strict-mcp-config --settings "$SETTINGS" --no-session-persistence)

run() {
  local name=$1; shift
  ( cd "$T" && echo "diff" | timeout 90 "$CLAUDE" -p "x" "$@" >/dev/null 2>&1 )
  sleep 3
  local hook=blocked mcp=blocked
  [ -f "$T/MARK-hook.txt" ] && hook=EXECUTED
  [ -f "$T/MARK-mcp.txt" ] && mcp=EXECUTED
  printf '%-20s repo hook: %-9s repo MCP server: %s\n' "$name" "$hook" "$mcp"
  rm -f "$T"/MARK-*
  [ "$hook$mcp" = blockedblocked ]
}

run "plain flags" "${PLAIN[@]}"
run "review-hooks flags" "${HARDENED[@]}"; rc=$?
[ $rc -eq 0 ] && echo "OK: the review is isolated from repository config." \
              || echo "FAIL: repository config still runs with the review-hooks flags."
exit $rc
