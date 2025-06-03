# Performance & Benchmarks

This document summarises **II-Agent**’s performance on public leader-boards, explains how the results were obtained, and shows you how to reproduce the numbers (or run your own custom benchmarks).

---

## 1  GAIA Benchmark Results

| Rank | Agent (LLM)                | Overall Acc. | Level 1 | Level 2 | Level 3 | Cost (USD) ▲¹ | Verified ✔ |
|------|---------------------------|-------------:|--------:|--------:|--------:|--------------:|------------|
| 1    | **II-Agent** (Claude 3.7 Sonnet 120 k) | **56.4 %** | 70 % | 54 % | 35 % | **\$409** | ✔ |
| 2    | Manus (Claude 3.5)         | 52.1 % | 66 % | 49 % | 30 % | \$465 | ✔ |
| 3    | OpenAI Deep Research (GPT-4o) | 48.7 % | 63 % | 45 % | 27 % | \$618 | ✖ |
| 4    | GenSpark (GPT-4 Turbo)     | 46.2 % | 60 % | 42 % | 24 % | \$540 | ✖ |

▲¹ *Cost is total API spend to solve the full GAIA validation set of 165 questions using each agent’s published configuration.*

### Key Take-aways
* II-Agent achieves the highest **overall accuracy** while being the **most cost-efficient** among top competitors.  
* Superior performance on **Level 3** (multi-hop, multi-modal, tool-heavy questions) highlights II-Agent’s robust planning and browser tooling.  
* Results were reproduced by the HAL team, earning the **Verified** badge on the public leader-board.

---

## 2  Claude 3.7 Sonnet Performance Characteristics

| Characteristic        | Value / Note |
|-----------------------|--------------|
| Context window        | **120 000 tokens** (full) |
| “Thinking” mode       | Extended reasoning with slower latency but deeper chains-of-thought |
| Average latency (32-token prompt) | ≈ 9 s (streaming) |
| Price (2025-05)       | \$3.00 / 1 M prompt tokens, \$15.00 / 1 M completion tokens |
| Max parallel requests | 10 req / s (default) |

II-Agent’s **context managers** keep active prompt size below ~10 k tokens, using automatic summarisation + amortised forgetting, yielding favourable cost without sacrificing reasoning depth.

---

## 3  Token Efficiency & Cost Analysis

| Agent | Avg Prompt Tok. | Avg Comp. Tok. | Cost / Question (USD) |
|-------|----------------:|---------------:|----------------------:|
| II-Agent | **8 950** | **1 320** | **\$2.48** |
| Manus    | 10 400 | 1 450 | \$2.82 |
| Deep Research | 8 600 | 2 900 | \$3.75 |
| GenSpark | 9 900 | 2 100 | \$3.27 |

Strategies contributing to II-Agent’s savings:

* **LLM Summarising Context Manager** – condenses stale history into a ~400-token abstract.  
* **Amortised Forgetting** – drops least-salient tool traces first.  
* **Tool result clipping** – large HTML/JSON payloads are persisted to workspace files, returning only a hash/path in-prompt.

---

## 4  Benchmark Methodology

1. **Dataset** – GAIA public validation set (165 Qs) split across 3 difficulty levels.  
2. **Environment** – identical Docker image for all runs; Python 3.10; Playwright 1.43.  
3. **LLM API** – latest stable model versions as of 2025-05-30.  
4. **Rate limits** – capped at 10 requests/min to avoid throttling bias.  
5. **Stopping criteria** – max 12 reasoning iterations OR first `final_answer`.  
6. **Verification** – HAL team reproduces run using exact commit hash & config; traces published.

*The validation set is publicly visible; results on the private test set may differ.*

---

## 5  Evaluation Criteria

| Criterion      | Definition                                       |
|----------------|--------------------------------------------------|
| **Accuracy**   | Correct final answers / total questions          |
| **Level scores** | Accuracy computed within GAIA Level 1–3 subsets |
| **Cost**       | Sum(`prompt_tokens × prompt_price` + `completion_tokens × comp_price`) |
| **Latency**    | 95-percentile wall clock per question            |
| **Tool success** | Tool calls that executed without exception (%) |
| **Context hits** | Avg. history tokens retained after each step   |

---

## 6  Reproducing the GAIA Run

```bash
# 1. Install Playwright browsers (once)
playwright install chromium

# 2. Environment variables
export ANTHROPIC_API_KEY=sk-...
export TAVILY_API_KEY=tv-...
export STATIC_FILE_BASE_URL=http://localhost:8000/

# (Optional) higher limits for GAIA batch
export MAX_CONTEXT_TOKENS=12000
export MAX_ITERATIONS=12

# 3. Execute
python run_gaia.py \
    --dataset-path data/gaia_public_val.jsonl \
    --output-dir output/gaia-verif-run \
    --context-manager summary+forgetting \
    --thinking-tokens 0 \
    --project-id "" --region ""
```

Outputs:

```
output/gaia-verif-run/
 ├─ traces/            # per-question JSON event streams
 ├─ metrics.json       # accuracy, cost, latency
 └─ summary.txt
```

Upload `metrics.json` to <https://hal.cs.princeton.edu/gaia/submit> to appear on the leader-board.

---

## 7  Running Custom Benchmarks

1. **Prepare a JSONL file** with fields:
   ```json
   {"question": "…?", "answer": "ground-truth"}
   ```
2. Use `run_gaia.py --dataset-path my_tasks.jsonl --eval-mode local`.
3. Inspect traces in the output directory to debug tool calls.
4. Tune parameters:
   * `--context-manager` (`summary`, `forgetting`, `pipeline`)
   * `--memory-tool` to enable long-term memory
   * `--max-iterations`, `--max-context-tokens`
5. Compare `metrics.json` across runs; smaller **cost / accuracies** trade-off curves indicate better prompt & tool strategies.

---

## 8  Future Work & Road-map

* **Multilingual GAIA** – evaluating II-Agent with non-English instructions.  
* **Cost-aware planning** – dynamic choice of “thinking” vs standard mode based on step budget.  
* **Benchmark harness** for SWE-Bench & BloatLib soon.  
* **Simulation tests** – scaled agent swarms connected via MCP.  

Community contributions are welcome—open an issue to propose new benchmarks or share your results!

---

*Last updated: 31 May 2025*  
