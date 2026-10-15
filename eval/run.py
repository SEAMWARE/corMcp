#!/usr/bin/env python3
#
# FILE            run.py
#
# Copyright 2026 Seamware
# SPDX-License-Identifier: Apache-2.0
#
# The evaluation: seeds the dataset in its own tenant, asks every question through a model and corMcp, and
# scores each answer - right (the pass/fail), the tools a good answer uses, the number of calls - with the
# tokens and the time. A result file per run, so a change to a description is measured, not guessed.
#
#   run.py [--provider anthropic_api] [--model M] [--broker URL] [--cases a,b] [--parallel N] [--no-seed]
#
import argparse, concurrent.futures, datetime, importlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "providers"))

import dataset
from cases import CASES



DISCOVERY = ("list_types", "list_attributes")



def score(case, result):
  text = result["answer"]
  missingText = [p for p in case.get("mustText", []) if not re.search(p, text, re.I)]
  if case.get("on") != "text":
    lines = [l for l in text.splitlines() if re.match(r"\W*ANSWER\W*:", l, re.I)]
    if not lines:
      return { "answerOk": False, "missing": ["the ANSWER line"], "extra": [], "toolsOk": False, "callsOk": False }
    text = lines[-1]
  missing = [p for p in case["must"]           if not re.search(p, text, re.I)] + missingText
  extra   = [p for p in case.get("mustNot", []) if re.search(p, text, re.I)]
  names   = [c["name"] for c in result["calls"]]
  toolsOk = all(any(n in alt.split("|") for n in names) for alt in case["tools"])
  # discovery (list_types, list_attributes) is what a fresh conversation starts with - in c³ once per
  # conversation, here once per question: not counted in the budget unless the case is about it
  work    = [n for n in names if n not in DISCOVERY or any(n in alt.split("|") for alt in case["tools"])]
  callsOk = (case["calls"] == 0) or (len(work) <= case["calls"])
  return { "answerOk": not missing and not extra, "missing": missing, "extra": extra, "toolsOk": toolsOk, "callsOk": callsOk }



def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--provider", default="anthropic_api")
  ap.add_argument("--model",    default="claude-sonnet-5-5")
  ap.add_argument("--broker",   default=os.environ.get("BROKER_URL", "http://127.0.0.1:1026"))
  ap.add_argument("--cases",    default="")
  ap.add_argument("--parallel", type=int, default=4)
  ap.add_argument("--no-seed",  action="store_true")
  ap.add_argument("--label",    default="")
  ap.add_argument("--rescore",  default="", help="a results file: scored again with the current cases, no model calls")
  a = ap.parse_args()

  if a.rescore:
    d     = json.load(open(a.rescore))
    cases = { c["id"]: c for c in CASES }
    ok    = 0
    for r in d["results"]:
      s = score(cases[r["id"]], r)
      ok += s["answerOk"]
      if not s["answerOk"]:
        print(f"  FAIL  {r['id']:<22} missing {s['missing']} extra {s['extra']}")
    print(f"answers {ok}/{len(d['results'])} (was {d['summary']['answers']}) - {a.rescore}")
    return

  broker   = a.broker.rstrip("/")
  provider = importlib.import_module(a.provider)
  system   = open(os.path.join(HERE, "system.txt")).read().strip()
  mcpCmd   = [os.path.join(HERE, "..", "corMcp"), "--broker", broker, "--tenant", dataset.TENANT]

  if not a.no_seed:
    dataset.seed(broker)
  temporal = dataset.hasTemporal(broker)

  cases = [c for c in CASES if not a.cases or c["id"] in a.cases.split(",")]
  todo  = [c for c in cases if temporal or not c.get("temporal")]
  print(f"{len(todo)} cases ({len(cases) - len(todo)} skipped: no temporal API), {a.provider} {a.model}, {broker}", flush=True)

  def one(case):
    try:
      r = provider.run(case["q"], system, mcpCmd, a.model)
    except Exception as e:
      r = { "answer": "", "calls": [], "turns": 0, "usage": {}, "costUsd": None, "seconds": 0, "error": f"{type(e).__name__}: {e}" }
    r["score"] = score(case, r)
    s = r["score"]
    print(f"  {'ok  ' if s['answerOk'] else 'FAIL'}  {case['id']:<22} tools {'ok' if s['toolsOk'] else '--'}  calls {len(r['calls'])}{'' if s['callsOk'] else '!'}  {r['seconds']}s"
          + (f"  missing {s['missing']}" if s["missing"] else "") + (f"  extra {s['extra']}" if s["extra"] else "")
          + (f"  ERROR {r['error']}" if r.get("error") else ""), flush=True)
    return case, r

  with concurrent.futures.ThreadPoolExecutor(a.parallel) as ex:
    done = list(ex.map(one, todo))

  n       = len(done)
  answers = sum(r["score"]["answerOk"] for _, r in done)
  tools   = sum(r["score"]["toolsOk"]  for _, r in done)
  callsOk = sum(r["score"]["callsOk"]  for _, r in done)
  calls   = sum(len(r["calls"]) for _, r in done)
  errs    = sum(sum(c["isError"] for c in r["calls"]) for _, r in done)
  cost    = sum((r.get("costUsd") or 0) for _, r in done)
  secs    = sum(r["seconds"] for _, r in done)

  print(f"\nanswers {answers}/{n} - tools {tools}/{n} - within the call budget {callsOk}/{n} - {calls} tool calls ({errs} errors) - "
        f"{secs:.0f} s" + (f" - ${cost:.2f}" if cost else ""))

  os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
  stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
  path  = os.path.join(HERE, "results", f"{stamp}-{a.provider}-{a.model}{'-' + a.label if a.label else ''}.json")
  with open(path, "w") as f:
    json.dump({ "provider": a.provider, "model": a.model, "broker": broker, "label": a.label,
                "summary": { "cases": n, "answers": answers, "tools": tools, "callsOk": callsOk, "calls": calls, "toolErrors": errs, "seconds": secs, "costUsd": cost },
                "results": [ dict(id=c["id"], q=c["q"], **r) for c, r in done ] }, f, indent=1, ensure_ascii=False)
  print(path)



main()
