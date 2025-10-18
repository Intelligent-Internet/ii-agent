#!/usr/bin/env python3
import json, os, sys, subprocess, time

ROOT = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
QUEUE = os.path.join(ROOT, ".claude", "task_queue.json")
LEDGER = os.path.join(ROOT, ".claude", "budget_ledger.jsonl")
SPAWNER = os.path.join(ROOT, "scripts", "spawn_new_session.sh")

THRESHOLD = float(os.environ.get("CLAUDE_SESSION_BUDGET", "0.60"))  # 60%

def read_last_percent():
    if not os.path.exists(LEDGER): return None
    try:
        *_, last = open(LEDGER, "r").read().strip().splitlines()
        j = json.loads(last)
        return float(j.get("percent_of_window"))
    except Exception:
        return None

def next_task_and_advance():
    if not os.path.exists(QUEUE): return None
    try:
        q = json.load(open(QUEUE))
        queue  = q.get("queue", [])
        cursor = int(q.get("cursor", 0))
        if cursor < len(queue):
            nxt = queue[cursor]
            q["cursor"] = cursor + 1
            json.dump(q, open(QUEUE, "w"))
            return nxt
        return None
    except Exception:
        return None

def spawn_new_session(next_task):
    # You can customize the CLI via env CLAUDE_CMD, defaults below.
    cmd = os.environ.get("CLAUDE_CMD", "claude --dangerously-skip-permission")
    sid = os.environ.get("CLAUDE_NEW_SESSION_ID") or f"scribe-{int(time.time())}"
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = ROOT
    env["CLAUDE_NEW_SESSION_ID"] = sid
    # Optional: pass a bootstrap instruction via STDIN if your CLI supports it.
    boot = f"Resume at {next_task}. Keep each block ≤60% context. Use the existing queue and plan."
    launcher = SPAWNER if os.path.exists(SPAWNER) else None
    try:
        if launcher:
            subprocess.Popen([launcher, next_task or ""], env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            # Start detached; adjust to your CLI if needed
            subprocess.Popen(cmd, shell=True, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Write handoff note so the new session has a crisp starting cue
        with open(os.path.join(ROOT, ".claude", "handoff.md"), "w") as f:
            f.write(f"NEXT: {next_task}\n{boot}\n")
        return True
    except Exception:
        return False

def main():
    # Validate input from Claude hooks engine (not used, but ensures well-formed)
    try: _ = json.load(sys.stdin)
    except Exception:
        print(json.dumps({"decision": None}), end=""); return

    percent = read_last_percent()
    nxt = next_task_and_advance()

    # If we exceeded the budget, roll over to a new session and ALLOW stop
    if percent is not None and percent >= THRESHOLD:
        if nxt:
            spawn_new_session(nxt)
        print(json.dumps({"decision": None}), end="")   # end this session
        return

    # Otherwise, if there’s a next task, BLOCK stop and auto-continue
    if nxt:
        print(json.dumps({"decision": "block",
                          "reason": f"Continue with next task: {nxt}. Stay under 60% of context, then Stop again."}), end="")
        return

    # No next task → allow stop
    print(json.dumps({"decision": None}), end="")

if __name__ == "__main__":
    main()
