# Composio Take-home – AI Product Ops

This project automates research across 100 SaaS applications using a two-pass AI research pipeline. It captures authentication methods, developer onboarding, API readiness, MCP availability, buildability, and evidence, then verifies the results against official documentation before generating a single interactive HTML case study.

**Live Case Study:** https://asthak9.github.io/Composio-research/
**Repository:** https://github.com/AsthaK9/Composio-research)
**Dataset:** `data/apps.json` (100 rows, the full schema)
**Agent:** `agent/research_agent.py`
**Verification:** `verification/verification.json`

## Highlights

- 100 SaaS applications researched
- Two-pass AI research pipeline
- Verification against official documentation
- Interactive HTML case study
- Confidence scoring for every application

## What's here

```
data/
  apps_raw.py        the 100-app dataset as Python literals (source of truth)
  apps.json           same data, exported to JSON for the site
agent/
  research_agent.py   the two-pass research pipeline (baseline vs tool-verified)
  apps_seed.csv        input list: id, name, category
verification/
  verification.json   9-app deep-verification sample: pass-1 vs pass-2 per field,
                       plus the apps the agent honestly couldn't resolve
docs/
  index.html           the single-page case study (findings, patterns, agent,
                        proof, verification — all in one page, no build step)
```

## Running the agent yourself
Output:
- apps.json
- sample.diff.json (verification mode)

```bash
requirements.txt contains the Python dependencies needed to reproduce the research pipeline.

# Configure the required API credentials
Configure ANTHROPIC_API_KEY in your environment.

Linux/macOS:
export ANTHROPIC_API_KEY=<your_api_key>

Windows PowerShell:
$env:ANTHROPIC_API_KEY="<your_api_key>"

# Baseline pass: no tools, just model knowledge (fast, ~1/3 accurate on obscure apps)
python agent/research_agent.py --input agent/apps_seed.csv --pass baseline --out baseline.json

# Verified pass: web_search tool attached, cites real docs URLs
python agent/research_agent.py --input agent/apps_seed.csv --pass verified --out apps.json

# Verification spot-check: run both passes on N apps and print what changed
python agent/research_agent.py --input agent/apps_seed.csv --pass verify-diff --sample 9 --out sample.json
```

Each run is one app = one model call. 100 apps at the `verified` setting is
roughly 100 web-search-enabled completions; expect it to take a while and to
cost real API credits. The `--sample` flag exists so you can smoke-test on a
handful of apps before committing to a full run.

### Swapping in Composio

The whole point of the `search_tool` boundary in `run_pass()` is that it
doesn't care what does the looking-up. The research pipeline is built around a pluggable search interface. The current implementation uses an LLM with web-search capabilities, but the search layer can be replaced with Composio MCP or any equivalent tool without changing the rest of the pipeline. To use Composio instead:

1. Stand up Composio's MCP server (or a hosted toolkit) with a web-search /
   browser-use action.
2. In `run_pass()`, replace the `tools=[{"type": "web_search_20250305", ...}]`
   block with Composio's MCP tool definition (Anthropic's Messages API
   accepts MCP server configs directly — see Anthropic's MCP connector docs).
3. Everything downstream (the JSON schema, the diffing, the output files) is
   unchanged.

This is also the natural next step for Composio specifically: instead of the
agent producing *a report about* which apps are buildable, point it at
Composio's own SDK and have it register the "ready" ones as toolkits
directly. A natural extension would be replacing the current search layer with Composio's SDK to automatically register applications classified as "ready" as toolkits instead of only generating a report.


## Methodology

- Started from the provided list of 100 applications and target schema.
- Used a two-pass research pipeline:
  - Pass 1 generated structured metadata.
  - Pass 2 verified findings using official documentation where needed.
- Well-established platforms were accepted without additional searches only when the generated
output matched stable public documentation. Confidence levels indicate whether findings were live-verified or based on stable public information., while
  ambiguous or enterprise-focused products received additional verification.
- Confidence levels (`verified`, `high`, `medium`, `low`) are reported for every app.
- Seven applications could not be confidently resolved and are explicitly
  reported rather than guessed.

## Deploying the case study

`docs/index.html` is a single self-contained file (inline CSS/JS, data
embedded) — no build step. To get a live link, the fastest options are:

- **GitHub Pages**: push this repo, enable Pages on the `main` branch,
  point it at `/docs`, done.
- **Netlify/Vercel drop**: drag the `docs/` folder onto either dashboard.
- **Local**: just open `docs/index.html` in a browser — it renders fully
  offline since all data is embedded, no API calls at runtime.
