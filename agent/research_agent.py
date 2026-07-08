#!/usr/bin/env python3
"""
research_agent.py
==================
The pipeline behind the Composio take-home dataset (apps.json).

WHAT THIS IS
------------
A two-pass research agent that takes a list of app names and produces the
schema the assignment asks for: category, one-line description, auth
method(s), self-serve vs gated, API surface + MCP status, a buildability
verdict, and an evidence URL - for every app.

Pass 1 ("baseline") asks the model cold, no tools. This is what you'd get
if you just asked an LLM "does X have an API." It's fast, free, and right
about 1/3 of the time on anything obscure, small, or younger than the
model's training cutoff (see /verification/verification.json for the
measured number).

Pass 2 ("verified") re-runs the SAME apps with a real web-search tool
attached and instructions to cite the actual docs page. This is what
actually produced the "verified"/"high" confidence rows in apps.json.

WHERE COMPOSIO FITS
--------------------
This script uses Anthropic's native `web_search` tool because that's what
was available in this environment. The integration point for Composio is
the `search_tool` argument to `run_pass()`: swap it for Composio's MCP
web-search/browser-use action (or a whole Composio toolkit, since
research one app is itself a tool-calling task: "look up this app's
docs, tell me its auth model") and nothing else in the pipeline changes.
That's also the natural next step if you wanted this to *self-register*
the toolkits it finds are buildable, rather than just writing a report
about them.

WHERE A HUMAN HAD TO STEP IN (see README for the full list)
-------------------------------------------------------------
- Judgment calls on the self_serve taxonomy itself (self_serve vs
  self_serve_paid vs approval vs partner_gated) - the agent classifies
  into this taxonomy, but a human defined the taxonomy and its boundaries.
- Catching a same-name collision (Pylon the support tool vs. Pylon the
  unrelated open-source GraphQL framework) - the agent's first search hit
  the wrong product silently; only a human diff against the actual
  category ("Support and Helpdesk") caught it.
- Deciding when "could not find public docs" should be reported as a
  finding (Pumble, Waterfall.io, Paygent Connect, iPayX) rather than
  re-queried indefinitely or guessed.
- Final accuracy scoring and the honest write-up of what's still
  low-confidence in the full 100-row set.

USAGE
-----
    export ANTHROPIC_API_KEY=sk-ant-...
    python research_agent.py --input apps_seed.csv --out apps.json --pass verified
    python research_agent.py --input apps_seed.csv --sample 9 --pass verify-diff

Requires: pip install anthropic --break-system-packages
"""
import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from typing import Optional

try:
    import anthropic
except ImportError:
    anthropic = None  # script can still be read/inspected without the dep installed

MODEL = "claude-sonnet-4-6"

SCHEMA_INSTRUCTIONS = """
You are a product-ops research agent. For the given app, research and return
ONLY a single JSON object (no prose, no markdown fences) with exactly these
keys:

  name              (string)
  category          (string, one of the 10 category names given)
  desc              (string, one line, what the product does)
  auth              (string, e.g. "OAuth2", "API key", "Basic auth", "None")
  self_serve        (one of: "self_serve", "self_serve_paid", "approval", "partner_gated", "not_applicable")
  self_serve_detail (string, 1-2 sentences: HOW you know - what a developer
                      actually has to do to get credentials, and any caveat)
  api_surface       (string, 1-2 sentences: REST/GraphQL/gRPC, roughly how
                      broad, whether an MCP server exists - "native" if the
                      vendor ships one, "community" if only third-party ones
                      exist, "none" if you found neither)
  buildability      (one of: "ready", "workaround", "blocked")
  blocker           (string, empty if buildability is "ready", otherwise the
                      single main thing standing in the way)
  evidence          (string, the actual docs URL you used - must be a URL you
                      found via search this turn, not a guess)
  confidence        (one of: "verified", "high", "medium", "low" - "verified"
                      ONLY if you actually fetched/read a docs page this turn;
                      "low" if you are guessing or could not find the product)

If you cannot find credible public documentation for the app after
searching, do not fabricate an answer: set self_serve to "not_applicable" or
your best category-level inference, set buildability to "blocked", set
confidence to "low", and say plainly in self_serve_detail that you could not
confirm it and a human should follow up directly. This is a correct and
useful answer, not a failure.
"""


@dataclass
class AppResult:
    id: int
    name: str
    category: str
    desc: str
    auth: str
    self_serve: str
    self_serve_detail: str
    api_surface: str
    buildability: str
    blocker: str
    evidence: str
    confidence: str
    pass_type: str  # "baseline" or "verified"


def load_seed(path: str):
    """CSV with columns: id,name,category (the 100-app source list)."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({"id": int(row["id"]), "name": row["name"], "category": row["category"]})
    return rows


def run_pass(app: dict, client, use_search: bool) -> AppResult:
    """Run one app through the model, with or without the web_search tool."""
    prompt = (
        f"App: {app['name']}\nCategory: {app['category']}\n\n"
        + SCHEMA_INSTRUCTIONS
    )
    tools = [{"type": "web_search_20250305", "name": "web_search"}] if use_search else []

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        tools=tools,
        messages=[{"role": "user", "content": prompt}],
    )

    # Pull the final text block (after any tool_use/tool_result round trips
    # the SDK already resolved server-side for web_search).
    text_blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    raw = "\n".join(text_blocks).strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Model didn't return clean JSON - a human reviews these, they are
        # not silently discarded.
        data = {
            "name": app["name"], "category": app["category"],
            "desc": "PARSE_ERROR - needs human review",
            "auth": "unknown", "self_serve": "not_applicable",
            "self_serve_detail": raw[:300], "api_surface": "unknown",
            "buildability": "blocked", "blocker": "agent output could not be parsed",
            "evidence": "", "confidence": "low",
        }

    return AppResult(
        id=app["id"], pass_type="verified" if use_search else "baseline", **data
    )


def diff_passes(baseline: AppResult, verified: AppResult) -> dict:
    """Field-level hit/miss between the two passes, for the verification report."""
    fields = ["auth", "self_serve", "buildability"]
    out = {"app": baseline.name, "changes": []}
    for f in fields:
        b, v = getattr(baseline, f), getattr(verified, f)
        if b.strip().lower() != v.strip().lower():
            out["changes"].append({"field": f, "pass1": b, "pass2": v})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="CSV: id,name,category")
    ap.add_argument("--out", default="apps.json")
    ap.add_argument("--pass", dest="pass_type", choices=["baseline", "verified", "verify-diff"],
                     default="verified")
    ap.add_argument("--sample", type=int, default=None,
                     help="Only run the first N apps (used for --pass verify-diff spot checks)")
    args = ap.parse_args()

    if anthropic is None:
        sys.exit("pip install anthropic --break-system-packages")
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    apps = load_seed(args.input)
    if args.sample:
        apps = apps[: args.sample]

    results = []
    diffs = []
    for i, app in enumerate(apps, 1):
        print(f"[{i}/{len(apps)}] {app['name']}...", file=sys.stderr)
        if args.pass_type == "verify-diff":
            base = run_pass(app, client, use_search=False)
            time.sleep(0.5)
            ver = run_pass(app, client, use_search=True)
            diffs.append(diff_passes(base, ver))
            results.append(asdict(ver))
        else:
            r = run_pass(app, client, use_search=(args.pass_type == "verified"))
            results.append(asdict(r))
        time.sleep(0.5)  # be polite to rate limits across 100 apps

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote {len(results)} rows to {args.out}", file=sys.stderr)

    if diffs:
        diff_path = args.out.replace(".json", ".diff.json")
        with open(diff_path, "w") as f:
            json.dump(diffs, f, indent=2)
        changed = sum(1 for d in diffs if d["changes"])
        print(f"{changed}/{len(diffs)} apps changed at least one field between "
              f"passes -> {diff_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
