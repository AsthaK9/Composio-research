# Composio take-home - 100-app API research

**Live case study:** `docs/index.html` (open directly, or deploy — see below)
**Dataset:** `data/apps.json` (100 rows, the full schema)
**Agent:** `agent/research_agent.py`
**Verification:** `verification/verification.json`

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

```bash
pip install anthropic --break-system-packages
export ANTHROPIC_API_KEY=sk-ant-...

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
doesn't care what does the looking-up. This script uses Anthropic's built-in
`web_search` tool because that's what was available in the environment this
was built in. To use Composio instead:

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
directly. That's a half-day follow-up, not a rebuild.

## How this was actually built (honest version)

1. I was given the 100-app list and the schema the assignment asks for.
2. I ran real web searches (not memory) against every app I wasn't
   confident about — new/small vendors, anything where "gated vs self-serve"
   wasn't obvious from the name, and anything where getting it wrong would
   be embarrassing (see the DealCloud and Pylon stories in the case study —
   those are the two best examples of why this step matters).
3. For very well-known, extremely stable developer platforms (Stripe,
   GitHub, Slack, Notion, and the like) I used verified general knowledge
   rather than re-searching every single one — that's a deliberate choice to
   spend the research budget where it moves accuracy, not a shortcut taken
   silently. Every row's `confidence` field tells you which apps are
   `verified` (checked live docs this pass), `high` (extremely stable/
   canonical, not re-checked but reliable), `medium` (plausible, not
   re-checked), or `low` (uncertain, said so on the page).
4. `research_agent.py` is the reusable, runnable version of the same
   process — point it at ANTHROPIC_API_KEY and it reproduces the pipeline
   end to end, including the pass-1-vs-pass-2 diffing that produced the
   verification numbers on the case study page.
5. Seven apps defeated the research entirely (Pumble, Waterfall.io, Paygent
   Connect, iPayX, and lower-confidence findings on Otter AI, Consensus, and
   Grain) — the page says so, with the specific reason for each, instead of
   quietly filling in a plausible-sounding guess.

## Deploying the case study

`docs/index.html` is a single self-contained file (inline CSS/JS, data
embedded) — no build step. To get a live link, the fastest options are:

- **GitHub Pages**: push this repo, enable Pages on the `main` branch,
  point it at `/docs`, done.
- **Netlify/Vercel drop**: drag the `docs/` folder onto either dashboard.
- **Local**: just open `docs/index.html` in a browser — it renders fully
  offline since all data is embedded, no API calls at runtime.
