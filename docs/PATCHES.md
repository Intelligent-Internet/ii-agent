# Vendored Frontend Patches

This file documents changes made to the vendored ii-agent frontend to maintain build compatibility within the SCRIBE AI-Salon repository.

## 2025-10-10: Frontend Alias Resolution Fix

### Problem
The vendored ii-agent frontend's `app/layout.tsx` imports `@/providers`, but the `providers.tsx` file was missing, causing build failures with the error "Module not found: Can't resolve '@/providers'".

### Solution
Fixed the alias resolution issue through configuration changes only, without modifying upstream source code where possible:

1. **Created `frontend/providers.tsx`** - Root-level providers wrapper that exports theme and context providers
   - File: `frontend/providers.tsx`
   - Purpose: Provides ThemeProvider wrapper for the application
   - This is a minimal shim file that maintains compatibility with the vendored app structure

2. **Updated `frontend/tsconfig.json`** - Enhanced TypeScript path resolution
   - Added explicit `baseUrl: "."`
   - Enhanced paths mapping: `"@/*": ["./*", "./src/*", "./app/*"]`
   - Ensures TypeScript can resolve `@/providers` to multiple potential locations

3. **Updated `frontend/next.config.ts`** - Added webpack alias for runtime resolution
   - Added webpack config to map `@` to the frontend directory root
   - Ensures Next.js webpack can resolve the alias at build time
   - Belt-and-suspenders approach alongside TypeScript config

4. **Created root `package.json`** - npm workspaces setup
   - Established monorepo structure with frontend as a workspace
   - Added build scripts: `build:safe`, `build:scr`, `build:ii`
   - Allows independent building of SCRIBE code and vendored frontend

5. **Created `.github/workflows/ci.yml`** - CI pipeline
   - Builds both SCRIBE TypeScript and vendored frontend
   - Runs boundary checks to ensure no SCRIBE code imports from vendored frontend
   - Ensures build passes before merge

### Files Modified
- ✅ `frontend/providers.tsx` (created)
- ✅ `frontend/tsconfig.json` (baseUrl and paths updated)
- ✅ `frontend/next.config.ts` (webpack alias added)
- ✅ `package.json` (created at root with workspaces)
- ✅ `.github/workflows/ci.yml` (created)

### Files NOT Modified
- ❌ No changes to `frontend/app/layout.tsx` (upstream source preserved)
- ❌ No changes to other vendored React components
- ❌ No changes to routing or agent hosting logic

### Boundary Protection
The following boundary check ensures SCRIBE code doesn't import from the vendored frontend:

```bash
grep -rn "from ['\"].*agents/scribe-agent\|require(['\"].*agents/scribe-agent" . \
  --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" \
  --exclude-dir=node_modules --exclude-dir=agents --exclude-dir=frontend
```

### Testing
```bash
# Install dependencies
npm install

# Build SCRIBE + vendored frontend
npm run build:safe

# Run boundary checks (manual)
grep -rn "from ['\"].*agents/scribe-agent\|require(['\"].*agents/scribe-agent" . \
  --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" \
  --exclude-dir=node_modules --exclude-dir=agents --exclude-dir=frontend
```

### Future Considerations
- The vendored frontend is temporary for MVP development
- When transitioning to a separate frontend deployment, remove:
  - `frontend/` directory
  - `frontend` from workspaces in root `package.json`
  - `build:ii` script
  - Frontend build step from CI workflow
- Keep boundary checks in place to maintain separation of concerns

### Related Issues
- Original error: Module not found `@/providers`
- Resolution: Config-based alias fix + minimal shim file
- No functional changes to upstream vendored code

---

## Change Log

### 2025-10-10: Frontend alias resolution to support '@/providers' (tsconfig/webpack alias)
- Created `frontend/providers.tsx` shim to mirror theme provider exports
- Updated `frontend/tsconfig.json` with baseUrl and enhanced paths mapping
- Updated `frontend/next.config.ts` with webpack alias for @ resolution
- No logic changes to vendored source; config-only fix plus minimal re-export shim
