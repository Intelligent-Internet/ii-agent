# Meta Llama 4 Scout/Maverick - Large Context Signal Monitoring

**Task**: Continue researching real-world signals for Meta Llama 4 models with large contexts

**Next Steps**:

1. **Monitor Production Deployments** (online sources)
   - Reddit: r/LocalLLaMA, r/MachineLearning, r/ArtificialIntelligence
   - Twitter/X: `#Llama4`, `#LocalAI`, `#OpenSourceAI`
   - Hacker News: ShowHN, AskHN posts about Llama 4 deployments
   - Discord: LocalAI, Llama.cpp, Ollama communities
   - GitHub Issues: llama.cpp, ollama, vLLM repositories

2. **Track Key Signals** - What to look for:
   - **Haystack Testing**: Users reporting needle-in-haystack performance at various context lengths
   - **Effective Limits**: "I tried 500K context but only works reliably at 150K"
   - **Memory Usage**: RAM/VRAM requirements vs. advertised capacity
   - **Speed Degradation**: "At 200K tokens, inference slows to X tokens/sec"
   - **Quality Metrics**: "Code completion quality drops after 100K tokens"
   - **Training Claims**: Meta researchers discussing actual training data (256K vs. 10M)

3. **Specific Data Points to Capture**:
   - Model variant (Scout 17B-16E, Maverick 17B-128E)
   - Context length tested (actual, not just claimed)
   - Task type (RAG, code, reasoning, summarization)
   - Success rate (% of queries that work)
   - Hardware (A100, H100, RTX 4090, Mac Silicon)
   - Framework (llama.cpp, vLLM, TensorRT, MLX)
   - Quantization (Q4_0, Q6_K, FP16, AWQ)

4. **Tooling to Build**:
   - Web scraper for Reddit/HN posts (24h check)
   - Twitter API monitor for `#Llama4`
   - GitHub issue tracker for relevant repos
   - Results aggregator with date, source, model version

5. **Search Queries**:
   - "llama 4 scout context length" site:reddit.com OR site:news.ycombinator.com
   - "llama 4 10M tokens" "OOM" OR "out of memory"
   - "Llama 4 max context" "haystack" OR "needle"
   - "Scout 17B-16E" benchmarking OR "context window"

6. **Red Flags** (indicate marketing vs. reality):
   - "Never trained beyond 256K tokens"
   - "Virtual context extension"
   - "Extrapolated from training data"
   - "Synthetic longer context"

7. **Power User Sources** (most reliable signals):
   - Papers With Code: Llama 4 benchmark results
   - ArXiv: Meta's actual training papers
   - Hugging Face: Model cards with real-world testing
   - Together AI/LMStudio: Hosted performance data
   - Perplexity Labs: Live model comparisons

**Storage**: Store findings in `self._harmonic_miss_tracker` with format:
```json
{
  "model_id": "meta-llama/Llama-4-Scout-17B-16E",
  "error_type": "haystack_failure",
  "context_tokens": 128000,
  "evidence_type": "user_report",
  "evidence_url": "https://reddit.com/r/LocalLLaMA/comments/...",
  "timestamp": "2025-11-20T15:30:00Z"
}
```

**Output**: Automated weekly summary of Llama 4 signals, aggregated by context length and success rate.
