#
# FILE            common.py
#
# Copyright 2026 Seamware
# SPDX-License-Identifier: Apache-2.0
#
# What the evaluation's sets share: the broker requests that seed a set, and the patterns the cases check
# answers with.
#
import json, math, re, urllib.error, urllib.request



# -----------------------------------------------------------------------------
#
# The broker
#
def http(broker, tenant, method, path, body=None):
  req = urllib.request.Request(broker + "/ngsi-ld/v1" + path, method=method, data=json.dumps(body).encode() if body is not None else None)
  req.add_header("Content-Type", "application/json")
  req.add_header("NGSILD-Tenant", tenant)
  try:
    with urllib.request.urlopen(req) as r:
      return r.status
  except urllib.error.HTTPError as e:
    return e.code



def seedSet(broker, tenant, ents, history, subscriptions):
  # the tenant emptied of the set's ids and their history (an earlier run's history repeats the answers),
  # everything created, the history by PATCHes: [(entity id, attribute, [(value, observedAt, unitCode)])]
  http(broker, tenant, "POST", "/entityOperations/delete", [e["id"] for e in ents])
  for e in ents:
    http(broker, tenant, "DELETE", "/temporal/entities/" + e["id"])
  for s in subscriptions:
    http(broker, tenant, "DELETE", "/subscriptions/" + s["id"])

  status = http(broker, tenant, "POST", "/entityOperations/create", ents)
  if status not in (200, 201):
    raise RuntimeError(f"POST /entityOperations/create answered {status}")

  for eid, attr, steps in history:
    for value, at, unit in steps:
      s = http(broker, tenant, "PATCH", f"/entities/{eid}/attrs", { attr: { "type": "Property", "value": value, "unitCode": unit, "observedAt": at } })
      if s != 204:
        raise RuntimeError(f"PATCH {eid} {attr} answered {s}")

  for sub in subscriptions:
    s = http(broker, tenant, "POST", "/subscriptions", sub)
    if s != 201:
      raise RuntimeError(f"POST /subscriptions answered {s}")



def hasTemporal(broker, tenant, eid, attr):
  req = urllib.request.Request(f"{broker}/ngsi-ld/v1/temporal/entities/{eid}?attrs={attr}&lastN=1")
  req.add_header("NGSILD-Tenant", tenant)
  try:
    with urllib.request.urlopen(req) as r:
      return r.status == 200
  except urllib.error.HTTPError:
    return False



def distanceM(a, b):
  lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
  h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
  return 2 * 6371000 * math.asin(math.sqrt(h))



# -----------------------------------------------------------------------------
#
# The patterns
#
WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "twenty-one"]

def num(x, decimals=None):
  # 30 -> 30, 30.0, 30,0, thirty ; 0.62 -> 0.62 ; with decimals: rounded to that many, or to an integer
  if isinstance(x, float) and not x.is_integer():
    if decimals is not None:
      opts = { f"{x:.{decimals}f}", f"{round(x)}" }
      return "(" + "|".join(re.escape(o).replace(r"\.", r"[.,]") for o in opts) + r")\b"
    return re.escape(f"{x:g}").replace(r"\.", r"[.,]") + r"\b"
  word = rf"|\b{WORDS[int(x)]}\b" if 0 <= int(x) < len(WORDS) else ""
  return rf"((?<![\d.]){int(x)}([.,]0+)?(?![\d]){word})"

def ids(shorts):
  return [re.escape(s) + r"\b" for s in shorts]

NONE = r"\b(no|none|zero|0|not any|there are no|there is no|isn't|aren't)\b"
