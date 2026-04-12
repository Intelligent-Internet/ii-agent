#!/bin/bash
# Create SEATS Dark Theme Slide Template
# This creates a template based on the ELSKI Series website dark mode styling

API_URL="${API_URL:-http://localhost:8000}"

echo "=== Creating SEATS Dark Theme Slide Template ==="
echo "API URL: $API_URL"
echo

# Step 1: Dev login to get access token
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

# Step 2: Create the template
echo "Step 2: Creating slide template..."

# The template content contains styling guidelines and example HTML
TEMPLATE_CONTENT=$(cat << 'TEMPLATE_EOF'
# SEATS Dark Theme - Slide Template

## Design System (Extracted from ELSKI Series Website)

### Color Palette (Dark Mode)

**Background Colors:**
- Primary Background: `hsl(240 10% 3.9%)` → `#0a0a0f` (near black with blue tint)
- Secondary Background: `#111827` (gray-900)
- Card Background: `#1f2937` (gray-800)
- Elevated Surface: `#374151` (gray-700)

**Gradient Backgrounds:**
- Hero Gradient: `from-slate-950 via-blue-950 to-purple-950`
  - slate-950: `#020617`
  - blue-950: `#172554`
  - purple-950: `#3b0764`

**Text Colors:**
- Primary Text: `hsl(0 0% 98%)` → `#fafafa` (near white)
- Secondary Text: `#d1d5db` (gray-300)
- Muted Text: `#9ca3af` (gray-400)
- Subtle Text: `#6b7280` (gray-500)

**Accent Colors (Gradients):**
- Primary CTA: `from-blue-600 to-purple-600` (#2563eb → #9333ea)
- Phase 1 (Blue-Cyan): `from-blue-500 to-cyan-500` (#3b82f6 → #06b6d4)
- Phase 2 (Purple-Pink): `from-purple-500 to-pink-500` (#a855f7 → #ec4899)
- Phase 3 (Orange-Red): `from-orange-500 to-red-500` (#f97316 → #ef4444)
- Phase 4 (Green-Emerald): `from-green-500 to-emerald-500` (#22c55e → #10b981)

**Border Colors:**
- Default Border: `hsl(240 3.7% 15.9%)` → `#27272a`
- Subtle Border: `#374151` (gray-700)
- Accent Border: `#3b82f6` (blue-500)

### Typography

**Font Family:** Inter (sans-serif fallback: system-ui, -apple-system, sans-serif)

**Font Sizes (for 1280x720 slides):**
- Mega Title: 72px (4.5rem) - Hero headlines
- Title: 48px (3rem) - Section headers
- Subtitle: 36px (2.25rem) - Card titles
- Large Text: 24px (1.5rem) - Descriptions
- Body: 18px (1.125rem) - Regular content
- Small: 14px (0.875rem) - Labels, captions
- Tiny: 12px (0.75rem) - Tags, metadata

**Font Weights:**
- Bold: 700 (headings, emphasis)
- Semibold: 600 (subheadings, buttons)
- Medium: 500 (labels)
- Regular: 400 (body text)

### Layout Principles

**Spacing Scale (rem):**
- xs: 0.5rem (8px)
- sm: 0.75rem (12px)
- md: 1rem (16px)
- lg: 1.5rem (24px)
- xl: 2rem (32px)
- 2xl: 3rem (48px)
- 3xl: 4rem (64px)

**Border Radius:**
- Small: 0.375rem (6px) - tags, small buttons
- Medium: 0.75rem (12px) - cards
- Large: 1rem (16px) - feature cards
- XL: 1.5rem (24px) - hero sections
- Full: 9999px - pills, avatars

**Shadows (Dark Mode):**
- Subtle: `0 4px 6px -1px rgba(0,0,0,0.3)`
- Medium: `0 10px 15px -3px rgba(0,0,0,0.4)`
- Large: `0 25px 50px -12px rgba(0,0,0,0.5)`

### Visual Effects

**Glassmorphism:**
- backdrop-blur: blur(24px)
- background: rgba(15,23,42,0.7) (slate-900/70)

**Gradient Text:**
- Use `bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent`

**Animated Elements:**
- Subtle pulse on badges: `animation: pulse 2s cubic-bezier(.4,0,.6,1) infinite`
- Hover lift: `transform: translateY(-0.5rem)`
- Hover scale: `transform: scale(1.05)`

---

## Slide Templates

### 1. Title Slide
```html
<div style="width: 1280px; min-height: 720px; background: linear-gradient(135deg, #020617 0%, #172554 50%, #3b0764 100%); padding: 80px; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; font-family: Inter, system-ui, sans-serif; position: relative; overflow: hidden;">
  <!-- Decorative blur orbs -->
  <div style="position: absolute; top: -100px; left: 25%; width: 300px; height: 300px; background: rgba(37,99,235,0.1); border-radius: 50%; filter: blur(64px);"></div>
  <div style="position: absolute; bottom: -100px; right: 25%; width: 300px; height: 300px; background: rgba(147,51,234,0.1); border-radius: 50%; filter: blur(64px);"></div>
  
  <!-- Badge -->
  <div style="background: rgba(30,58,138,0.3); padding: 8px 24px; border-radius: 9999px; margin-bottom: 32px;">
    <span style="color: #93c5fd; font-size: 14px; font-weight: 600;">[BADGE TEXT]</span>
  </div>
  
  <!-- Title -->
  <h1 style="font-size: 72px; font-weight: 700; color: #fafafa; margin: 0 0 24px 0; line-height: 1.1;">
    [MAIN TITLE]
  </h1>
  
  <!-- Subtitle with gradient -->
  <h2 style="font-size: 48px; font-weight: 700; background: linear-gradient(90deg, #2563eb, #9333ea, #db2777); -webkit-background-clip: text; background-clip: text; color: transparent; margin: 0 0 32px 0;">
    [GRADIENT SUBTITLE]
  </h2>
  
  <!-- Description -->
  <p style="font-size: 20px; color: #d1d5db; max-width: 800px; line-height: 1.6; margin: 0;">
    [DESCRIPTION TEXT]
  </p>
</div>
```

### 2. Content Slide with Icon Cards
```html
<div style="width: 1280px; min-height: 720px; background: linear-gradient(135deg, #020617 0%, #172554 50%, #3b0764 100%); padding: 60px; font-family: Inter, system-ui, sans-serif;">
  <!-- Header -->
  <div style="text-align: center; margin-bottom: 48px;">
    <h2 style="font-size: 48px; font-weight: 700; color: #fafafa; margin: 0 0 16px 0;">[SECTION TITLE]</h2>
    <p style="font-size: 20px; color: #9ca3af;">[SECTION SUBTITLE]</p>
  </div>
  
  <!-- Three Column Cards -->
  <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px;">
    <!-- Card 1 -->
    <div style="background: linear-gradient(135deg, #1f2937 0%, #111827 100%); border-radius: 16px; padding: 32px; border: 1px solid #374151;">
      <div style="width: 48px; height: 48px; background: linear-gradient(135deg, #3b82f6, #06b6d4); border-radius: 12px; display: flex; align-items: center; justify-content: center; margin-bottom: 16px;">
        <!-- Icon placeholder -->
        <span style="color: white; font-size: 24px;">✦</span>
      </div>
      <h3 style="font-size: 20px; font-weight: 700; color: #fafafa; margin: 0 0 8px 0;">[CARD TITLE]</h3>
      <p style="font-size: 16px; color: #d1d5db; margin: 0; line-height: 1.5;">[CARD DESCRIPTION]</p>
    </div>
    <!-- Repeat for cards 2 and 3 -->
  </div>
</div>
```

### 3. Phase/Process Slide
```html
<div style="width: 1280px; min-height: 720px; background: linear-gradient(135deg, #020617 0%, #172554 50%, #3b0764 100%); padding: 60px; font-family: Inter, system-ui, sans-serif;">
  <h2 style="font-size: 48px; font-weight: 700; color: #fafafa; text-align: center; margin: 0 0 48px 0;">[PROCESS TITLE]</h2>
  
  <!-- Two Column Process Cards -->
  <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 24px;">
    <!-- Phase Card -->
    <div style="background: linear-gradient(135deg, #1f2937 0%, #111827 100%); border-radius: 24px; padding: 32px; border: 2px solid #374151; display: flex; gap: 24px;">
      <!-- Phase Icon -->
      <div style="width: 64px; height: 64px; background: linear-gradient(135deg, #3b82f6, #06b6d4); border-radius: 16px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
        <span style="color: white; font-size: 28px; font-weight: 700;">01</span>
      </div>
      <div>
        <span style="background: rgba(30,58,138,0.3); color: #93c5fd; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 600;">[PHASE LABEL]</span>
        <h3 style="font-size: 24px; font-weight: 700; color: #fafafa; margin: 12px 0 8px 0;">[PHASE TITLE]</h3>
        <p style="font-size: 16px; color: #d1d5db; margin: 0; line-height: 1.5;">[PHASE DESCRIPTION]</p>
      </div>
    </div>
    <!-- Repeat for other phases -->
  </div>
</div>
```

### 4. Image + Text Split Slide
```html
<div style="width: 1280px; min-height: 720px; background: #111827; display: grid; grid-template-columns: 1fr 1fr; font-family: Inter, system-ui, sans-serif;">
  <!-- Image Side -->
  <div style="position: relative; overflow: hidden;">
    <img src="[IMAGE_URL]" style="width: 100%; height: 100%; object-fit: cover;" />
    <div style="position: absolute; inset: 0; background: linear-gradient(90deg, transparent 60%, #111827 100%);"></div>
  </div>
  
  <!-- Content Side -->
  <div style="padding: 60px; display: flex; flex-direction: column; justify-content: center;">
    <span style="background: linear-gradient(90deg, #3b82f6, #06b6d4); color: white; padding: 6px 16px; border-radius: 9999px; font-size: 12px; font-weight: 600; width: fit-content; margin-bottom: 24px;">[CATEGORY]</span>
    <h2 style="font-size: 40px; font-weight: 700; color: #fafafa; margin: 0 0 16px 0; line-height: 1.2;">[TITLE]</h2>
    <p style="font-size: 18px; color: #d1d5db; line-height: 1.6; margin: 0 0 24px 0;">[DESCRIPTION]</p>
    
    <!-- Key Points -->
    <div style="display: flex; flex-direction: column; gap: 12px;">
      <div style="display: flex; align-items: center; gap: 12px;">
        <span style="color: #22c55e; font-size: 20px;">✓</span>
        <span style="color: #fafafa; font-size: 16px;">[POINT 1]</span>
      </div>
      <!-- Repeat for more points -->
    </div>
  </div>
</div>
```

### 5. Stats/Data Slide
```html
<div style="width: 1280px; min-height: 720px; background: linear-gradient(135deg, #020617 0%, #172554 50%, #3b0764 100%); padding: 80px; font-family: Inter, system-ui, sans-serif;">
  <h2 style="font-size: 48px; font-weight: 700; color: #fafafa; text-align: center; margin: 0 0 64px 0;">[STATS TITLE]</h2>
  
  <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 32px;">
    <!-- Stat Card -->
    <div style="text-align: center;">
      <div style="font-size: 64px; font-weight: 700; background: linear-gradient(135deg, #3b82f6, #06b6d4); -webkit-background-clip: text; background-clip: text; color: transparent;">[NUMBER]</div>
      <div style="font-size: 18px; color: #9ca3af; margin-top: 8px;">[STAT LABEL]</div>
    </div>
    <!-- Repeat for other stats -->
  </div>
</div>
```

### 6. Closing/CTA Slide
```html
<div style="width: 1280px; min-height: 720px; background: #111827; padding: 80px; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; font-family: Inter, system-ui, sans-serif;">
  <h2 style="font-size: 56px; font-weight: 700; color: #fafafa; margin: 0 0 24px 0;">[CLOSING TITLE]</h2>
  <p style="font-size: 20px; color: #9ca3af; max-width: 600px; margin: 0 0 48px 0;">[CLOSING MESSAGE]</p>
  
  <!-- CTA Button Style -->
  <div style="background: linear-gradient(90deg, #2563eb, #9333ea); padding: 16px 48px; border-radius: 9999px; display: inline-block;">
    <span style="color: white; font-size: 18px; font-weight: 600;">[CTA TEXT]</span>
  </div>
  
  <!-- Footer Info -->
  <div style="margin-top: 64px; color: #6b7280; font-size: 14px;">
    [FOOTER TEXT / CONTACT INFO]
  </div>
</div>
```

---

## Usage Guidelines

1. **Maintain Consistency:** Use the exact color values and gradients across all slides
2. **Typography Hierarchy:** Always use larger, bolder text for headlines
3. **Spacing:** Use generous padding (60-80px) to avoid crowded layouts
4. **Icons:** Use simple line icons or filled solid icons in white/accent colors
5. **Images:** Use high-quality images with gradient overlays for text readability
6. **Cards:** Round corners (16-24px) with subtle borders and gradient backgrounds
7. **Accents:** Use gradient backgrounds for badges, icons, and CTAs
8. **Animations:** Keep animations subtle - hover effects only

TEMPLATE_EOF
)

# Escape the content for JSON
TEMPLATE_JSON=$(echo "$TEMPLATE_CONTENT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')

# Create the template
CREATE_RESPONSE=$(curl -s -X POST "$API_URL/slide-templates" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "slide_template_name": "SEATS Dark Theme",
    "slide_content": '"$TEMPLATE_JSON"',
    "slide_template_images": []
  }')

echo "Response: $CREATE_RESPONSE"

# Extract template ID
TEMPLATE_ID=$(echo "$CREATE_RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$TEMPLATE_ID" ]; then
    echo "ERROR: Failed to create template"
    exit 1
fi

echo
echo "=== Template Created Successfully ==="
echo
echo "Template ID: $TEMPLATE_ID"
echo "Template Name: SEATS Dark Theme"
echo
echo "To use this template:"
echo "1. Start a new SLIDE session"
echo "2. Select 'SEATS Dark Theme' from the template dropdown"
echo "3. The agent will use these styling guidelines"
echo
