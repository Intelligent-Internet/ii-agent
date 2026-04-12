#!/bin/bash
# Rework RCTCOP title slide to match ELSKI title slide layout
# Sends a message to the existing RCTCOP session via the ii-agent API

API_URL="${API_URL:-http://localhost:8000}"
SESSION_ID="7d313d92-20db-4659-a9ff-07519a9460f3"
MODEL_ID="anthropic"

echo "=== RCTCOP Title Slide Rework ==="
echo "API URL: $API_URL"
echo "Session: $SESSION_ID"
echo

# Step 1: Dev login
echo "Step 1: Logging in..."
LOGIN_RESPONSE=$(curl -s -X GET "$API_URL/auth/dev/login")
ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -z "$ACCESS_TOKEN" ]; then
    echo "ERROR: Failed to get access token"
    echo "Response: $LOGIN_RESPONSE"
    exit 1
fi
echo "✓ Logged in successfully"
echo

# Step 2: Send the slide edit request
echo "Step 2: Sending title slide rework request to ii-agent..."
echo "  (This will stream SSE events — the agent will edit slide 1 in the sandbox)"
echo

# The prompt includes the ELSKI title slide HTML as the reference layout
MESSAGE=$(cat << 'PROMPT_EOF'
Please rework Slide 1 (the title slide) of this RCTCOP presentation to match the layout and styling of the ELSKI series title slide. Here is the ELSKI title slide HTML that should be used as the template:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ELSKI Professional Training Series</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', system-ui, sans-serif; overflow: hidden; }
        .slide {
            width: 1280px; height: 720px;
            background: linear-gradient(135deg, #020617 0%, #0c1838 50%, #1e1b4b 100%);
            padding: 60px 80px; display: flex; flex-direction: column;
            justify-content: center; align-items: center; text-align: center;
            position: relative; overflow: hidden;
        }
        .decoration-orb-1 { position: absolute; top: -120px; right: 10%; width: 400px; height: 400px; background: rgba(59,130,246,0.08); border-radius: 50%; filter: blur(90px); z-index: 0; }
        .decoration-orb-2 { position: absolute; bottom: -120px; left: 10%; width: 400px; height: 400px; background: rgba(168,85,247,0.08); border-radius: 50%; filter: blur(90px); z-index: 0; }
        .content { z-index: 2; max-width: 1000px; }
        .badge { background: rgba(59,130,246,0.15); border: 1px solid rgba(59,130,246,0.3); padding: 8px 24px; border-radius: 9999px; display: inline-block; margin-bottom: 24px; }
        .badge-text { color: #93c5fd; font-size: 13px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; }
        .series-label { font-size: 18px; font-weight: 600; color: #60a5fa; margin-bottom: 12px; letter-spacing: 1px; }
        .main-title { font-size: 64px; font-weight: 800; color: #fafafa; margin: 0 0 20px 0; line-height: 1.1; }
        .subtitle { font-size: 24px; font-weight: 600; color: #d1d5db; margin: 0 0 40px 0; line-height: 1.3; }
        .highlight { background: linear-gradient(90deg, #60a5fa, #a78bfa); -webkit-background-clip: text; background-clip: text; color: transparent; }
        .stats-row { display: flex; gap: 48px; justify-content: center; margin-top: 40px; }
        .stat-box { text-align: center; }
        .stat-number { font-size: 56px; font-weight: 700; background: linear-gradient(135deg, #3b82f6, #06b6d4); -webkit-background-clip: text; background-clip: text; color: transparent; display: block; margin-bottom: 8px; }
        .stat-label { font-size: 16px; color: #9ca3af; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }
        .divider { width: 2px; height: 60px; background: linear-gradient(180deg, transparent, rgba(96,165,250,0.3), transparent); }
    </style>
</head>
<body>
    <div class="slide">
        <div class="decoration-orb-1"></div>
        <div class="decoration-orb-2"></div>
        <div class="content">
            <div class="badge"><span class="badge-text">SEATS Professional Training • Advanced Fabrication</span></div>
            <div class="series-label">ELSKI VIDEO SERIES</div>
            <h1 class="main-title">Master Safety-Critical<br>Sit Ski Fabrication</h1>
            <h2 class="subtitle">Complete <span class="highlight">14-Video Training</span> in Aluminum Bumper-Handle<br>Assembly for Mountain Man Adaptive Skiing Equipment</h2>
            <div class="stats-row">
                <div class="stat-box"><span class="stat-number">14</span><span class="stat-label">Video Lessons</span></div>
                <div class="divider"></div>
                <div class="stat-box"><span class="stat-number">4</span><span class="stat-label">Learning Phases</span></div>
                <div class="divider"></div>
                <div class="stat-box"><span class="stat-number">Advanced</span><span class="stat-label">Skill Level</span></div>
            </div>
        </div>
    </div>
</body>
</html>
```

Keep the EXACT same CSS structure, class names, styling, and layout from the ELSKI slide above. Only change the text content to match the RCTCOP series:

1. Badge text: "SEATS Professional Training • Adaptive Equipment"
2. Series label: "RCTCOP VIDEO SERIES"
3. Main title: "Converting Bodypoint Straps<br>into Custom Wrist Cuffs"
4. Subtitle: Complete <highlight>9-Video Training</highlight> in Professional Wheelchair<br>Safety Strap Conversion for Adaptive Equipment
5. Stats row: 9 Video Lessons | 3 Learning Phases | Intermediate Skill Level
6. Page title: "RCTCOP Professional Training Series"

Use the same background gradient (#020617 → #0c1838 → #1e1b4b), the same orb decorations, same badge border styling, same stats-row layout with dividers — everything structurally identical to ELSKI, just with RCTCOP content. Please edit slide 1 only.
PROMPT_EOF
)

# Use curl to send the message and stream the response
curl -s -N -X POST "$API_URL/v1/chat/conversations" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d "$(jq -n \
    --arg content "$MESSAGE" \
    --arg model_id "$MODEL_ID" \
    --arg session_id "$SESSION_ID" \
    '{content: $content, model_id: $model_id, session_id: $session_id}'
  )" | while IFS= read -r line; do
    # Parse SSE events for user-friendly output
    if [[ "$line" == data:* ]]; then
        data="${line#data: }"
        # Show key events
        status=$(echo "$data" | jq -r '.status // empty' 2>/dev/null)
        case "$status" in
            "start")
                event_type=$(echo "$data" | jq -r '.name // "content"' 2>/dev/null)
                echo "  ▶ Started: $event_type"
                ;;
            "delta")
                # Print content deltas inline
                delta=$(echo "$data" | jq -r '.delta // empty' 2>/dev/null)
                if [ -n "$delta" ]; then
                    printf "%s" "$delta"
                fi
                ;;
            "done"|"complete")
                echo
                echo "  ✓ Agent completed"
                ;;
            "info")
                tool_name=$(echo "$data" | jq -r '.name // empty' 2>/dev/null)
                if [ -n "$tool_name" ]; then
                    echo "  ℹ Tool result: $tool_name"
                fi
                ;;
        esac
    fi
done

echo
echo "=== Done ==="
echo
echo "Next steps:"
echo "  1. Open the ii-agent frontend (http://192.168.2.2:3000)"
echo "  2. Navigate to the RCTCOP session to verify the updated title slide"
echo "  3. To generate a PDF, run:"
echo "     python scripts/html_to_pdf.py --session-id $SESSION_ID"
echo
