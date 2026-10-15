#
# FILE            cases.py
#
# Copyright 2026 Seamware
# SPDX-License-Identifier: Apache-2.0
#
# The evaluation cases: a question in plain language, how its answer is checked, and the tools that
# answer it best. The expected answers come from dataset.py.
#
#   must     - patterns the answer must contain (regular expressions, case-insensitive)
#   mustNot  - patterns it must not contain (an id that does not belong in the list)
#   mustText - patterns the whole answer must contain (the other part of a two-part question)
#   tools    - the tools a good answer uses (scored apart from the answer: "X is for Y")
#   calls    - the most tool calls a good answer needs
#   temporal - needs the broker's temporal API
#   on       - "text": checked on the whole answer; default: on its last line, "ANSWER: ..." (the ids or the
#              number alone - what the model adds around it, "the next lowest is CAR-03", is not scored)
#
import re
from dataset import *



WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "twenty-one"]

def num(x, decimals=None):
  # 30 -> 30, 30.0, 30,0 ; 0.62 -> 0.62, 62 %; with decimals: rounded to that many, or to an integer
  if isinstance(x, float) and not x.is_integer():
    if decimals is not None:
      opts = { f"{x:.{decimals}f}", f"{round(x)}" }
      return "(" + "|".join(re.escape(o).replace(r"\.", r"[.,]") for o in opts) + r")\b"
    return re.escape(f"{x:g}").replace(r"\.", r"[.,]") + r"\b"
  word = rf"|\b{WORDS[int(x)]}\b" if 0 <= int(x) < len(WORDS) else ""
  return rf"((?<![\d.]){int(x)}([.,]0+)?(?![\d]){word})"

def ids(shorts):
  return [re.escape(s) for s in shorts]

NONE = r"\b(no|none|zero|0|not any|there are no|there is no|isn't|aren't)\b"

moving       = [v[0] for v in VEHICLES if v[5] == "moving"]
over90       = [v[0] for v in VEHICLES if v[2] > 90]
fastest      = max(VEHICLES, key=lambda v: v[2])
lowFuel      = [v[0] for v in VEHICLES if v[6] < 0.2]
nearSol      = [v[0] for v in VEHICLES if distanceM(v[9], SOL) <= 1000]
freeNearPM   = [p[0] for p in PARKING if p[1] == "free" and distanceM(p[2], PLAZA_MAYOR) <= 300]
free         = [p[0] for p in PARKING if p[1] == "free"]
occupied     = [p[0] for p in PARKING if p[1] == "occupied"]
vallecas     = [v[0] for v in VEHICLES if v[10] == "D2"]
mercedes     = [v[0] for v in VEHICLES if v[7] == "Mercedes"]
inaccurate   = [v[0] for v in VEHICLES if v[3] is not None and v[3] > 2]
recent       = [v[0] for v in VEHICLES if v[4] > "2026-10-15T11:45:00Z"]
retiroDay    = no2Day("AQ-Retiro")
espanaDay    = no2Day("AQ-PlazaEspana")
retiroMaxH   = retiroDay.index(max(retiroDay))
espanaAvg    = sum(espanaDay) / 24
worstPm10    = max(STATIONS, key=lambda s: s[3])
nearestDepot = min(DEPOTS, key=lambda d: distanceM(d[5], SOL))
buses        = [v for v in VEHICLES if v[1] == "bus"]
leastFuelBus = min(buses, key=lambda v: v[6])
van04        = [v for v in VEHICLES if v[0] == "VAN-04"][0]
car03        = [v for v in VEHICLES if v[0] == "CAR-03"][0]

CASES = [
  # Discovery
  { "id": "types", "q": "What kinds of things does the broker hold?",
    "must": ["Vehicle", "Depot", "ParkingSpot", "AirQualityObserved"], "tools": ["list_types"], "calls": 1 },
  { "id": "vehicleAttrs", "on": "text", "q": "What information is there about each vehicle?",
    "must": ["speed", "fuel", "brand", "depot"], "tools": ["list_types|list_attributes"], "calls": 1 },

  # Counting
  { "id": "countVehicles", "q": "How many vehicles are there?",
    "must": [num(len(VEHICLES))], "tools": ["count_entities"], "calls": 1 },
  { "id": "countMoving", "q": "How many vehicles are moving right now?",
    "must": [num(len(moving))], "tools": ["count_entities"], "calls": 1 },
  { "id": "countNotMoving", "q": "How many vehicles are not moving?",
    "must": [num(len(VEHICLES) - len(moving))], "tools": ["count_entities|query_entities"], "calls": 2 },
  { "id": "countMercedes", "q": "How many of the vehicles are Mercedes?",
    "must": [num(len(mercedes))], "tools": ["count_entities|query_entities"], "calls": 2 },
  { "id": "countBusesMaintenance", "q": "How many buses are in maintenance, and which ones?",
    "must": ids(["BUS-02", "BUS-04"]), "mustText": [num(2)], "tools": ["query_entities"], "calls": 1 },
  { "id": "countFreeSpots", "q": "How many parking spots are free?",
    "must": [num(len(free))], "tools": ["count_entities"], "calls": 1 },

  # Filters
  { "id": "over90", "q": "Which vehicles are going faster than 90 km/h?",
    "must": ids(over90), "mustNot": ids([v[0] for v in VEHICLES if v[0] not in over90]), "tools": ["query_entities"], "calls": 1 },
  { "id": "fastest", "q": "Which vehicle is the fastest right now, and how fast is it going?",
    "must": ids([fastest[0]]), "mustText": [num(fastest[2])], "tools": ["query_entities"], "calls": 1 },
  { "id": "lowFuel", "q": "Which vehicles have less than 20% fuel left?",
    "must": ids(lowFuel), "mustNot": ids([v[0] for v in VEHICLES if v[0] not in lowFuel]), "tools": ["query_entities"], "calls": 1 },
  { "id": "leastFuelBus", "q": "Which bus has the least fuel?",
    "must": ids([leastFuelBus[0]]), "tools": ["query_entities"], "calls": 1 },
  { "id": "inaccurate", "q": "Which vehicles report their speed with an accuracy worse than 2 km/h?",
    "must": ids(inaccurate), "mustNot": ids([v[0] for v in VEHICLES if v[0] not in inaccurate]), "tools": ["query_entities"], "calls": 1 },
  { "id": "recent", "q": "Which vehicles have reported their speed in the last 15 minutes?",
    "must": ids(recent), "mustNot": ids([v[0] for v in VEHICLES if v[0] not in recent]), "tools": ["query_entities"], "calls": 1 },

  # One entity
  { "id": "van04Speed", "q": "What is the speed of VAN-04, and when was it measured?",
    "must": [num(van04[2]), r"11:40"], "tools": ["get_entity|query_entities"], "calls": 1 },
  { "id": "van02Ms", "q": "How fast is VAN-02 going, in metres per second?",
    "must": [num(30)], "tools": ["get_entity|query_entities"], "calls": 1 },
  { "id": "bus01Temperature", "q": "BUS-01 has two temperature sensors. What does each of them read?",
    "must": [num(21.5), num(88)], "tools": ["get_entity|query_entities"], "calls": 1 },

  # Relationships, object values, languages
  { "id": "car03Depot", "q": "Which depot does CAR-03 belong to, and what is its address?",
    "must": [r"Albufera"], "mustText": [r"Vallecas|\bD2\b"], "tools": ["get_entity", "get_entity|query_entities"], "calls": 2 },
  { "id": "vallecasVehicles", "q": "Which vehicles belong to the Vallecas depot?",
    "must": ids(vallecas), "mustNot": ids([v[0] for v in VEHICLES if v[0] not in vallecas]), "tools": ["query_entities"], "calls": 2 },
  { "id": "depotEnglish", "q": "What is the English name of the depot on Avenida de la Hispanidad?",
    "must": [r"Airport Depot"], "tools": ["query_entities"], "calls": 1 },

  # Geography
  { "id": "nearSol", "q": "Which vehicles are within 1 km of Puerta del Sol?",
    "must": ids(nearSol), "mustNot": ids([v[0] for v in VEHICLES if v[0] not in nearSol]), "tools": ["query_entities"], "calls": 1 },
  { "id": "freeNearPlazaMayor", "q": "How many free parking spots are there within 300 metres of Plaza Mayor?",
    "must": [num(len(freeNearPM))], "tools": ["count_entities|query_entities"], "calls": 1 },
  { "id": "nearestDepot", "q": "Which depot is closest to Puerta del Sol?",
    "must": [re.escape(nearestDepot[1]) + "|" + re.escape(nearestDepot[2]) + rf"|\b{nearestDepot[0]}\b"], "tools": ["query_entities"], "calls": 1 },

  # Paging
  { "id": "freeSpotIds", "q": "List the ids of all the free parking spots.",
    "must": ids(free), "mustNot": ids(occupied), "tools": ["query_entities"], "calls": 2 },

  # History
  { "id": "retiroMax", "q": "What was the highest NO2 level at the Retiro station on 14 October 2026, and at what time?",
    "must": [num(max(retiroDay)), rf"{retiroMaxH:02d}:00|{retiroMaxH}\s*(h|:00|am|pm)|{retiroMaxH - 12}\s*pm"], "tools": ["temporal"], "calls": 2, "temporal": True },
  { "id": "espanaAvg", "q": "What was the average NO2 at Plaza de España on 14 October 2026?",
    "must": [num(espanaAvg, 1)], "tools": ["temporal"], "calls": 2, "temporal": True },
  { "id": "retiroLast3", "q": "Show me the last three NO2 readings at Retiro.",
    "must": [num(NO2_NOW["AQ-Retiro"]), num(retiroDay[23]), num(retiroDay[22])], "tools": ["temporal"], "calls": 2, "temporal": True },
  { "id": "worstPm10", "q": "Which air-quality station has the worst PM10 right now?",
    "must": [re.escape(worstPm10[1]) + "|" + re.escape(worstPm10[0])], "tools": ["query_entities"], "calls": 1 },

  # The broker itself
  { "id": "subscriptions", "on": "text", "q": "Is anyone being notified of changes? What do they watch?",
    "must": [r"speed", r"100", r"example\.org/alerts|alerts"], "tools": ["list_subscriptions"], "calls": 1 },
  { "id": "registrations", "q": "Does any of the data come from other brokers or sources?",
    "must": [NONE], "tools": ["query_registrations"], "calls": 2 },

  # What is not there, what cannot be done
  { "id": "trains", "q": "How many trains are there?",
    "must": [NONE], "tools": ["list_types|count_entities"], "calls": 2 },
  { "id": "otherTenant", "on": "text", "q": "Show me the vehicles of tenant acme.",
    "must": [r"tenant"], "mustNot": ids(["BUS-01", "VAN-01", "CAR-01"]), "tools": [], "calls": 0 },
]
