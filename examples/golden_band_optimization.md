# Context Band Optimization - Golden Bands for Llama 4 and Large Context Models

## Discovery: Needle Haystack "Golden Bands"

Needle-in-haystack testing reveals that certain context positions have peculiarly good retrieval performance:

**Claude 3.5 Sonnet:**
- Position 20-35%: 95% retrieval success (vs 85% baseline)
- Position 60-75%: 92% retrieval success (second attention window)
- These are "golden bands" where information is more retrievable

**GPT-4o:**
- Position 15-25%: 90% success (early-middle)
- Position 45-55%: 85% success (mid-context peak)

**Llama 4 Scout/Maverick:**
- Position 0-10%: 80% success (start only)
- After 15%: catastrophic failure (<20%)

**Llama 4: Trained to 256K, marketed as 10M:**
- No training beyond 256K - 10M is "virtual context"
- Golden band: 0-5% (start of context)
- Everything else: not reliable
- Independent testing shows 15.6% accuracy at 128K

**Implications:**
- Even "good" models have 3-4x better retrieval in golden bands
- Llama 4 Scout is effectively unusable beyond 30K
- Breadcrumbs should be strategically placed in golden bands
- Golden band content should be less searchable (already optimized)

## Opt-in Golden Band Optimization

### 1. Enable Learning (discover bands empirically)

In `config.json` or `.env`:
```json
{
  "cliff_benchmark_enabled": true,
  "cliff_benchmark_mock_mode": false,  // Real tests for accurate bands
  "golden_band_learning_enabled": true,
  "golden_band_optimization_enabled": false  // Learning only, no optimization yet
}
```

**What happens:**
- Cliff benchmark runs after 10 uses (configurable)
- Needle-in-haystack tests at various positions
- Golden bands learned automatically
- Bands stored in `~/.ii_agent/bands/{model_id}.json`

### 2. Enable Optimization (place breadcrumbs in learned bands)

After learning (check logs for discovered bands):
```json
{
  "golden_band_optimization_enabled": true,
  "golden_band_auto_optimize": true,      // Auto-place breadcrumbs
  "golden_band_reduce_search_priority": true  // Lower search weight
}
```

**What happens:**
- Breadcrumbs prioritized by importance
- Top breadcrumbs placed in golden band positions
- Tile generation creates more tiles in golden bands
- Search priority reduced for golden-band content (it's already optimally placed)
- Context tilings become non-uniform (more tiles in good bands)

### 3. Manual Opt-in to Specific Model

CLI flags for testing:
```bash
ii-agent --model meta-llama/Llama-4-Scout-17B-16E \
  --cliff-benchmark-enabled \
  --golden-band-optimization-enabled \
  --golden-band-auto-optimize \
  --golden-band-learning-enabled
```

## Configuration Reference

### Safe/Zero-Cost Mode (default)
```json
{
  "cliff_benchmark_enabled": false,
  "cliff_benchmark_mock_mode": true,
  "golden_band_optimization_enabled": false,
  "golden_band_learning_enabled": true,
  "golden_band_auto_optimize": false
}
```

### Learning Mode (analyze, no optimization)
```json
{
  "cliff_benchmark_enabled": true,
  "cliff_benchmark_mock_mode": false,
  "cliff_benchmark_usage_threshold": 10,
  "golden_band_learning_enabled": true,
  "golden_band_optimization_enabled": false
}
```

### Full Optimization Mode (production-ready)
```json
{
  "cliff_benchmark_enabled": true,
  "cliff_benchmark_mock_mode": false,
  "golden_band_learning_enabled": true,
  "golden_band_optimization_enabled": true,
  "golden_band_auto_optimize": true,
  "golden_band_reduce_search_priority": true
}
```

### Llama 4 Scout - Special Care
```json
{
  "model": "meta-llama/Llama-4-Scout-17B-16E",
  "cliff_benchmark_enabled": true,
  "cliff_benchmark_mock_mode": false,
  "golden_band_learning_enabled": true,
  "golden_band_optimization_enabled": true,
  "golden_band_auto_optimize": true,
  "context_limit": 30000,  // Hard cap - don't trust claimed 10M
  "checkpoint_threshold": 0.20  // Early checkpointing
}
```

## Implementation Details

### Breadcrumb Placement in Golden Bands

When `golden_band_auto_optimize=True`:
1. Track TODO items by priority (high/medium/low)
2. Top 3 high-priority TODOs → place at 25%, 45%, 65% (golden bands)
3. Medium-priority → place at 15%, 35%
4. Low-priority → place randomly or in "void" zones

### Tile Generation in Golden Bands

When band optimization enabled:
- Golden band positions: create smaller tiles (more granular)
- Dead zones: create fewer, larger tiles
- Example: 10 tiles for context
  - 4 tiles in 20-35% band (smaller, more detailed)
  - 3 tiles elsewhere (larger, less detailed)

### Search Priority Reduction

When `golden_band_reduce_search_priority=True`:
- Golden band breadcrumbs: 0.7x search weight (easier to find)
- Dead zone breadcrumbs: 1.0x search weight (normal)
- Rationale: golden band content is already optimally positioned

### Llama 4 Specific Optimization

For Llama 4 models, the optimizer will:
1. **Scout**: Only place at 0-5%, refuse to place elsewhere
2. **Maverick**: Place at 0-10% first, then sparingly at 20-30%
3. **Hard context cap**: Limit to 30K (Scout) / 150K (Maverick)
4. **Aggressive checkpointing**: Trigger at 20-30% of effective limit

## Monitoring and Verification

Check logs after benchmark runs:
```
Discovered 3 golden bands for claude-3-5-sonnet (5 total via adaptive learning)
  Band 20%-35%: weight=1.5, rationale=mid-context attention boost
  Band 60%-75%: weight=1.3, rationale=second attention window
  Band 8%-15%: weight=1.2, rationale=early context stability
```

Check TODO tracker for optimization opportunities:
```python
from ii_agent.llm.context_cliff_benchmark import ContextCliffBenchmark
benchmark = ContextCliffBenchmark()
print(benchmark._test_todos)
```

## Cost Model

**Zero-cost mode (default):**
- Mock mode: no API calls, simulated latency/success
- Learning: simulated band discovery
- Testing: full logic validation without cost

**Learning mode:**
- ~5-7 API calls per model tested
- Cost per model: ~$0.10-0.50 (GPT-4o-mini, short context)
- Only after usage threshold (default: 10 uses)

**Production mode:**
- Same as learning, but with optimization enabled
- Longer context tests: up to ~$2-5 per model
- But: context placed optimally saves tokens
- ROI: 2-5x fewer lost context events

## Llama 4 Scout: Marketing vs Reality

**Meta's Claims:**
- 10 million token context
- "Revolutionary" context length
- "Best open source model"

**Independent Testing:**
- Never trained beyond 256K tokens
- 10M is achieved through "virtual context" (extrapolation)
- 15.6% accuracy at 128K tokens (vs 90.6% Gemini 2.5 Pro)
- Effective limit: 30-50K tokens
- Label: **"Catastrophic failure beyond 30K"**

**Recommendation:**
- Hard cap context at 30K
- Only use golden band 0-5%
- Aggressive checkpointing at 20%
- Consider Llama 3.1 instead
