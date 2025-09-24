Great—let’s treat this like a small system-design job. I’ll first carve their repo into software components (what they *are* and what they *should* be), then propose a refactored, swappable high-level architecture with clean interfaces and deployment slices.

---

# 1) What’s in their repo today (component inventory)

From the repo layout and README, we can infer the runtime “boxes” and the glue between them: reasoning LLM + prover LLM via vLLM, a Lean/Mathlib toolchain, per-step formalisation + ATP wrappers, a state-sequence scorer (LSTM aggregator), optional PRMs, and orchestration scripts. ([GitHub][1])

**A. Orchestration / pipelines**

* `collect_trace.py` — generates multiple solutions, splits into steps, dumps traces (train/test).
* `benchmark.py`, `benchmark_ensemble.py` — score and select best-of-N using retrospective (aggregator) and optional PRM score.
* `aggregator.py` — trains/uses the LSTM over step-state sequences.
* `divide_steps.py` — step segmentation of CoT. ([GitHub][1])

**B. Formal verification path**

* `formalize.py` — turns a natural-language step into a Lean statement + basic REPL checks.
* `verifier.py` — runs formalise→prove, emits the four discrete step states.
* `prover/`, `copra_helper.py`, `deepseek_prover_helper.py` — call the LLM provers and validate via Lean REPL.
* `prompts/` — few-shot / system prompts for formalisation. ([GitHub][1])

**C. Prospective reward models (optional)**

* `rm_shepherd.py`, `rm_rlhflow.py`, `rm_armo.py`, `rm_skywork.py` — step/trajectory scoring alternatives. ([GitHub][1])

**D. Models, data, utils**

* `models.py`, `data_loader.py`, `utils.py`, `datasets/`, `download.py` (PRM800K). ([GitHub][1])

**E. Environment / runtime**

* `compose.yml` — brings up separate vLLM services for the reasoning model and the prover.
* **Images**: the README suggests a prebuilt Lean+Python+mathlib image (`ghcr.io/liuchengwucn/safe:1.0.0`) and a vLLM image (`vllm/vllm-openai`), both orchestrated via Docker Compose, with multiple GPUs. ([GitHub][1])

---

# 2) What makes the current implementation hard to swap

Without nit-picking specific lines in their Dockerfile, the pain is structural:

* **Tight packaging of concerns**: Lean, mathlib cache, Python deps, and app code in one big image → any change (Lean version, mathlib, Python dep) forces a heavyweight rebuild and retest of everything. The README hints at this by recommending the prebuilt image with cached mathlib. ([GitHub][2])
* **Runtime contracts live in scripts**: Orchestration (`collect_trace.py`, `benchmark*.py`) directly imports helpers instead of calling services via stable APIs; swapping, say, COPRA vs DeepSeek Prover means changing Python code rather than re-pointing a client to a different service. ([GitHub][1])
* **Process-coupled scheduling**: Long-running operations (sampling N, per-step formalise→prove) are synchronous loops rather than message-driven jobs, making scale-out and retries awkward. (You can see the two model services and the “safe” container in Compose, but the Python entrypoints aren’t service boundaries.) ([GitHub][1])

---

# 3) Refactored, high-level architecture (swappable, testable, scale-able)

Think **five services** + **two infrastructure bits**. Each service is independently deployable and testable; the orchestrator talks HTTP/gRPC to everything. The **interfaces** are deliberately thin (JSON schemas included below).

## Services

1. **Orchestrator** (Python FastAPI)

* Responsibilities: sample N solutions from the **Reasoning LLM**; call **Step Parser**; fan-out steps to **Formaliser** → **Prover**; collect step states; call **Aggregator**; optionally call **PRM**; fuse scores and return the selected trajectory + audit trail.
* Interfaces it calls: Reasoning LLM (OpenAI/vLLM-OpenAI), Step Parser, Formaliser, Prover, Aggregator, PRM.

2. **Step Parser**

* Deterministic splitter of CoT into steps; optional normalisation/repair.
* `POST /parse`: `{ "text": "...full_CoT..." } → { "steps": ["s1","s2",...,"sk"] }`.

3. **Formaliser**

* LLM-driven Lean generation with Lean REPL syntax check.
* `POST /formalise`: `{ "step_text": "s_i", "context": {...} } → { "lean": "theorem ...", "well_typed": true|false, "messages":[...] }`.

4. **Prover**

* Runs LLM prover(s) to produce a Lean proof; verified via Lean REPL.
* `POST /prove`: `{ "lean": "theorem ..."} → { "proved": true|false, "time_ms": ..., "trace": "...", "repl_log": "..." }`.

5. **Aggregator**

* LSTM over step states (small, easily containerised).
* `POST /score_retrospective`: `{ "states": ["no-check","formalise-fail","proved","proof-fail", ...] } → { "score": float }`.

6. **PRM** (optional)

* Wrap 1+ reward models behind one façade.
* `POST /score_prospective`: `{ "steps":[...], "model":"shepherd|rlhflow|..." } → { "score": float }`.

## Infrastructure

* **Model Gateways** (vLLM OpenAI-compatible endpoints)

  * `reasoning-llm` (e.g., Llama-3.1-8B-Instruct / DeepSeek-Math-7B)
  * `prover-llm` (DeepSeek-Prover-V1.5-RL / COPRA)
    These already exist in their Compose flow; keep them isolated. ([GitHub][1])

* **Lean Runtime**

  * A dedicated, minimal Lean+Mathlib image that exposes a local REPL over a small RPC (or keep it a sidecar called by Formaliser/Prover) instead of baking Lean into every app image.

### Why this helps

* Swap **prover** (DeepSeek ↔ COPRA) by changing a container/image or a flag, not code.
* Version and upgrade **Lean** independently.
* Scale bottlenecks (Prover, Formaliser) horizontally via a queue.
* Capture **audit trails** (per-step Lean statements, proof logs) as first-class artefacts.

---

# 4) Suggested repo layout (modules → packages → services)

```
safe/
  services/
    orchestrator/            # FastAPI app, fan-out/in logic, fusion
    step_parser/             # pure Python splitter
    formaliser/              # LLM prompt+REPL client
    prover/                  # LLM prover client + REPL verifier
    aggregator/              # LSTM model server (TorchScript or ONNX)
    prm/                     # façade over reward models (optional)
  libs/
    lean_client/             # tiny RPC or CLI wrapper around Lean REPL
    prompts/                 # prompt templates for formalisation and provers
    scoring/                 # ensemble logic, calibration, tie-breaking
    data_io/                 # datasets, trace formats, load/save
  deploy/
    docker/
      base-python/           # slim base, pinned Python + uv or pip-tools
      lean-runtime/          # elan + lean + mathlib cache (small)
      orchestrator/
      formaliser/
      prover/
      aggregator/
      prm/
    compose/
      docker-compose.yml     # wires GPUs, networks, volumes
      overrides/
        local.yml            # dev mount + hot reload
  tests/
    unit/
    contract/                # HTTP/gRPC interface tests (golden JSON)
    e2e/
```

Map from their files to services/libs:

* `collect_trace.py`, `benchmark*.py` → **orchestrator** (CLI entrypoints that call HTTP services).
* `divide_steps.py` → **step\_parser**.
* `formalize.py`, `verifier.py` → **formaliser** (formalise) and **prover** (prove+verify) services.
* `copra_helper.py`, `deepseek_prover_helper.py`, `prover/` → move into **prover** service.
* `aggregator.py` → **aggregator** service (export the LSTM as TorchScript/ONNX).
* `rm_*.py` → **prm** service behind one consistent API.
* `models.py`, `utils.py`, `data_loader.py` → **libs/** (shared).
* `datasets/`, `download.py` → **libs/data\_io** + a tiny CLI.
  This refactor preserves semantics while introducing clean boundaries. ([GitHub][1])

---

# 5) Clean interfaces (copy-paste-able JSON contracts)

* **/parse**
  Request: `{ "text": "…full CoT…" }`
  Response: `{ "steps": ["…","…"] }`

* **/formalise**
  Request: `{ "step_text": "…", "context": {"problem": "…", "prev_results": [...]}}`
  Response: `{ "lean": "theorem …", "well_typed": true, "messages": ["…"] }`

* **/prove**
  Request: `{ "lean": "theorem …", "prover": "deepseek-v1.5-rl|copra", "timeout_s": 20 }`
  Response: `{ "proved": true, "proof": "by …", "repl_log": "…", "tokens_used": 1234 }`

* **/score\_retrospective**
  Request: `{ "states": ["proved","proof-fail",…] }`
  Response: `{ "score": 0.731 }`

* **/score\_prospective**
  Request: `{ "steps": ["…","…"], "model": "shepherd" }`
  Response: `{ "score": 0.412 }`

* **/solve (orchestrator)**
  Request: `{ "problem": "…", "N": 16, "ensemble_alpha": 0.5, "use_prm": true }`
  Response:

  ```json
  {
    "chosen": {"solution": "…", "steps": ["…"], "states": ["…"], "scores": {"retro": 0.73, "prm": 0.41}},
    "alternatives": [...],
    "evidence": [{"step": 3, "lean": "…", "proved": true, "repl_log": "…"}]
  }
  ```

---

# 6) Deployment slices (containers you can swap independently)

**Images (multi-stage, slim):**

* `safe/lean-runtime`: elan + lean + mathlib cache. No app code.
* `safe/formaliser`: FROM python-slim + `lean_client` + HTTP app; connect to `lean-runtime` via RPC/CLI.
* `safe/prover`: same pattern; add vLLM client (OpenAI API) for selected prover model.
* `safe/aggregator`: Torch runtime only; expose `/score_retrospective`.
* `safe/prm`: thin façade; points to local or remote PRMs.
* `safe/orchestrator`: FastAPI; no heavy ML deps.

**Compose (sketch):**

* `reasoning-llm` (vLLM, GPU 0), `prover-llm` (vLLM, GPU 1) — as in their README.
* `lean-runtime` (CPU OK), `formaliser` (CPU), `prover` (CPU + calls to `prover-llm`), `aggregator` (CPU), `prm` (CPU), `orchestrator` (CPU).
* Mount `~/.cache/huggingface` into the two vLLM containers; keep app images HF-offline.
  Their README already separates the vLLM endpoints and a “safe” container; we’re decomposing that “safe” box into 4–5 smaller boxes. ([GitHub][1])

---

# 7) Configuration & testing

* **Strict version pinning**: `uv` or `pip-tools` for lockfiles; pin Lean + mathlib.
* **Contract tests**: golden JSON for each endpoint; CI runs them against every PR.
* **E2E replay**: save a small seed of problems + expected states; run nightly.

---

# 8) Migration plan (no big-bang)

1. Extract **Step Parser** as a pure function → tiny FastAPI service.
2. Extract **Aggregator**: export LSTM, wrap `/score_retrospective`.
3. Wrap **Formaliser** around existing `formalize.py`; add Lean client lib.
4. Wrap **Prover** around existing helpers; make the REPL call explicit in the service.
5. Move orchestration logic from `collect_trace.py`/`benchmark*.py` into the **Orchestrator** service; keep the CLIs as thin HTTP clients.
6. Optional: unify `rm_*.py` behind the **PRM** façade.

---

# 9) Notes on their Dockerfile and Compose

* The project expects **two vLLM services** (reasoning + prover) and a separate **“safe” image** that bundles the Lean/Python world; they even recommend pre-pulling both vLLM and their own `safe:1.0.0` image. That’s a tell that the app image is heavy and tightly coupled to Lean + mathlib. Our split makes Lean a separate runtime so the app images stay small. ([GitHub][1])

---

## TL;DR

* Treat **Formaliser**, **Prover**, **Aggregator**, **PRM** as swappable services behind tiny JSON contracts; keep **Orchestrator** thin.
* Isolate **Lean** into a runtime image; keep vLLM endpoints exactly as they have them.
* Move current scripts to CLI clients that call services → you can replace any single component (e.g., COPRA ↔ DeepSeek Prover, LSTM ↔ another classifier) without touching the others.

If you want, I can also sketch concrete Dockerfiles and a `docker-compose.yml` for this split so you can lift-and-shift with minimal churn.

[1]: https://github.com/liuchengwucn/Safe "GitHub - liuchengwucn/Safe: (ACL 2025 Main) Safe: Enhancing Mathematical Reasoning in Large Language Models via Retrospective Step-aware Formal Verification - Official Implementation & Dataset"
[2]: https://github.com/liuchengwucn/Safe/blob/main/README.md "Safe/README.md at main · liuchengwucn/Safe · GitHub"
