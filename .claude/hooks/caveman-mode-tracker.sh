#!/usr/bin/env bash
# caveman — Claude Code UserPromptSubmit hook (bash port).
# Reads {prompt, ...} JSON from stdin, updates the .caveman-active flag based
# on /caveman commands or natural language activation, and emits a per-turn
# reminder so the active mode stays anchored across long sessions.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./caveman-config.sh
. "$SCRIPT_DIR/caveman-config.sh"

input=$(cat)
if command -v jq >/dev/null 2>&1; then
    prompt=$(printf '%s' "$input" | jq -r '.prompt // ""' 2>/dev/null || printf '')
elif command -v python3 >/dev/null 2>&1; then
    prompt=$(printf '%s' "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('prompt',''))" 2>/dev/null || printf '')
else
    printf 'caveman-mode-tracker: jq and python3 both missing — prompt parsing disabled\n' >&2
    prompt=""
fi
prompt=$(printf '%s' "$prompt" | tr '[:upper:]' '[:lower:]' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')

# Natural-language activation: explicit phrases only ("activate caveman",
# "talk like caveman", "enable caveman mode"). Generic mentions like
# "how does caveman mode work?" must not trigger activation.
if printf '%s' "$prompt" | grep -qE '\b(activate|enable|turn on|start|talk like)\b.*\bcaveman\b'; then
    if ! printf '%s' "$prompt" | grep -qE '\b(stop|disable|turn off|deactivate)\b'; then
        m=$(caveman_default_mode)
        if [ "$m" != "off" ]; then
            caveman_write_flag "$m"
        fi
    fi
fi

# Slash-command parsing.
case "$prompt" in
    /caveman*)
        cmd=$(printf '%s' "$prompt" | awk '{print $1}')
        arg=$(printf '%s' "$prompt" | awk '{print $2}')
        new_mode=""
        case "$cmd" in
            /caveman-commit) new_mode=commit ;;
            /caveman-review) new_mode=review ;;
            /caveman-compress|/caveman:caveman-compress|/caveman:compress) new_mode=compress ;;
            /caveman|/caveman:caveman)
                if [ -z "$arg" ]; then
                    new_mode=$(caveman_default_mode)
                else
                    case "$arg" in
                        off|stop|disable) new_mode=off ;;
                        wenyan-full) new_mode=wenyan ;;
                        *)
                            if caveman_is_valid_mode "$arg" && ! caveman_is_independent_mode "$arg"; then
                                new_mode=$arg
                            fi ;;
                    esac
                fi ;;
        esac
        if [ "$new_mode" = "off" ]; then
            caveman_clear_flag
        elif [ -n "$new_mode" ]; then
            caveman_write_flag "$new_mode"
        fi
        ;;
esac

# Deactivation triggers (slash + natural language).
if printf '%s' "$prompt" | grep -qE '\b(stop|disable|deactivate|turn off)\b.*\bcaveman\b|\bcaveman\b.*\b(stop|disable|deactivate|turn off)\b|\bnormal mode\b'; then
    caveman_clear_flag
fi

# Per-turn reinforcement. Independent modes get a brief reminder instead of
# the full caveman rules (which conflict with their own skill behavior).
active=$(caveman_read_flag) || active=""
if [ -n "$active" ]; then
    if caveman_is_independent_mode "$active"; then
        ctx="CAVEMAN MODE ACTIVE — independent mode: $active. Apply /$active skill behavior this turn."
    else
        ctx="CAVEMAN MODE ACTIVE ($active). Drop articles/filler/pleasantries/hedging. Fragments OK. Code/commits/security: write normal."
    fi
    if command -v jq >/dev/null 2>&1; then
        jq -nc --arg ctx "$ctx" \
            '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $ctx}}'
    else
        printf '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"%s"}}' "$ctx"
    fi
fi

exit 0
