#!/usr/bin/env python3
#
# FILE            run.py
#
# Copyright 2026 Seamware
# SPDX-License-Identifier: Apache-2.0
#
# The evaluation: seeds each set (fleet, building) in a tenant of its own, asks every question through a
# model and corMcp, and scores each answer - right (the pass/fail), the tools a good answer uses, the number
# of calls - with the tokens and the time. A result file per run, so a change to a description is measured,
# not guessed.
#
#   run.py [--set fleet,building] [--provider anthropic_api] [--model M] [--broker URL] [--cases a,b]
#          [--parallel N] [--no-seed] [--label L] [--rescore <results file>]
#
import argparse, concurrent.futures, datetime, importlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "providers"))

SETS = ("fleet", "building")



DISCOVERY = ("list_types", "list_attributes")



def hostError(call):
  return call.get("isError") and "No such tool available" in (call.get("error") or "")



def summary(results):
  s = [r["score"] for r in results]
  return { "cases": len(s), "answers": sum(x["answerOk"] for x in s), "tools": sum(x["toolsOk"] for x in s), "callsOk": sum(x["callsOk"] for x in s),
           "calls": sum(sum(not hostError(c) for c in r["calls"]) for r in results),
           "toolErrors": sum(sum(c["isError"] and not hostError(c) for c in r["calls"]) for r in results),
           "hostErrors": sum(sum(bool(hostError(c)) for c in r["calls"]) for r in results) }



def line(name, m):
  n = m["cases"]
  return (f"{name:<9} answers {m['answers']}/{n} - tools {m['tools']}/{n} - within the call budget {m['callsOk']}/{n} - "
          f"{m['calls']} calls, {m['toolErrors']} failed, {m['hostErrors']} the host could not route")



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
  # a call the host could not route ("No such tool available": Claude Code prefixes MCP tools, mcp__<server>__,
  # and a model that writes a tool's bare name misses it) never reached corMcp - c³ uses the bare names
  names   = [c["name"] for c in result["calls"] if not hostError(c)]
  toolsOk = all(any(n in alt.split("|") for n in names) for alt in case["tools"])
  # discovery (list_types, list_attributes) is what a fresh conversation starts with - in c³ once per
  # conversation, here once per question: not counted in the budget unless the case is about it
  work    = [n for n in names if n not in DISCOVERY or any(n in alt.split("|") for alt in case["tools"])]
  callsOk = (case["calls"] == 0) or (len(work) <= case["calls"])
  return { "answerOk": not missing and not extra, "missing": missing, "extra": extra, "toolsOk": toolsOk, "callsOk": callsOk }



def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--set",      default=",".join(SETS))
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
    cases = { (s, c["id"]): c for s in SETS for c in importlib.import_module(s).CASES }
    for r in d["results"]:
      r["score"] = score(cases[(r.get("set", "fleet"), r["id"])], r)
      if not r["score"]["answerOk"]:
        print(f"  FAIL  {r['id']:<22} missing {r['score']['missing']} extra {r['score']['extra']}")
    for name in SETS:
      mine = [r for r in d["results"] if r.get("set", "fleet") == name]
      if mine:
        print(line(name, summary(mine)))
    print(a.rescore)
    return

  broker   = a.broker.rstrip("/")
  provider = importlib.import_module(a.provider)
  system   = open(os.path.join(HERE, "system.txt")).read().strip()
  todo     = []
  skipped  = 0

  for name in a.set.split(","):
    mod = importlib.import_module(name)
    if not a.no_seed:
      mod.seed(broker)
    temporal = mod.temporal(broker)
    mcpCmd   = [os.path.join(HERE, "..", "corMcp"), "--broker", broker, "--tenant", mod.TENANT]
    for c in mod.CASES:
      if a.cases and c["id"] not in a.cases.split(","):
        continue
      if c.get("temporal") and not temporal:
        skipped += 1
        continue
      todo.append(dict(c, set=name, mcpCmd=mcpCmd))

  print(f"{len(todo)} cases ({skipped} skipped: no temporal API), {a.set}, {a.provider} {a.model}, {broker}", flush=True)

  def one(case):
    try:
      r = provider.run(case["q"], system, case["mcpCmd"], a.model)
    except Exception as e:
      r = { "answer": "", "calls": [], "turns": 0, "usage": {}, "costUsd": None, "seconds": 0, "error": f"{type(e).__name__}: {e}" }
    r["score"] = score(case, r)
    s = r["score"]
    print(f"  {'ok  ' if s['answerOk'] else 'FAIL'}  {case['set'][:5]:<5} {case['id']:<22} tools {'ok' if s['toolsOk'] else '--'}  calls {len(r['calls'])}{'' if s['callsOk'] else '!'}  {r['seconds']}s"
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

  for name in a.set.split(","):
    print(line(name, summary([r for c, r in done if c["set"] == name])))
  print(f"\nanswers {answers}/{n} - tools {tools}/{n} - within the call budget {callsOk}/{n} - {calls} tool calls ({errs} errors) - "
        f"{secs:.0f} s" + (f" - ${cost:.2f}" if cost else ""))

  os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
  stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
  path  = os.path.join(HERE, "results", f"{stamp}-{a.provider}-{a.model}{'-' + a.label if a.label else ''}.json")
  with open(path, "w") as f:
    json.dump({ "provider": a.provider, "model": a.model, "broker": broker, "label": a.label, "sets": a.set,
                "summary": { "cases": n, "answers": answers, "tools": tools, "callsOk": callsOk, "calls": calls, "toolErrors": errs, "seconds": secs, "costUsd": cost },
                "results": [ dict(set=c["set"], id=c["id"], q=c["q"], **r) for c, r in done ] }, f, indent=1, ensure_ascii=False)
  print(path)



main()
