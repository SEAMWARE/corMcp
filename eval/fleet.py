#
# FILE            fleet.py
#
# Copyright 2026 Seamware
# SPDX-License-Identifier: Apache-2.0
#
# The evaluation set "fleet": a small Madrid fleet - vehicles, depots, parking spots, air-quality stations
# with a day of history, one subscription - and its cases. Fixed values, so every answer is known; the cases
# compute their expected answers from these tables, never from hand-typed numbers.
#
# "Now" is 2026-10-15T12:00:00Z - the system prompt says so.
#
import math, re
from common import *

NOW    = "2026-10-15T12:00:00Z"
TENANT = "mcpeval"

SOL         = (-3.7038, 40.4169)                 # Puerta del Sol
PLAZA_MAYOR = (-3.7074, 40.4155)



# -----------------------------------------------------------------------------
#
# Vehicles - id, kind, speed (km/h), speed accuracy (km/h, None: none), observedAt, status, fuel (0..1),
#            brand, model, (lon, lat), depot
#
VEHICLES = [
  ("BUS-01", "bus",  45, 1.0,  "2026-10-15T11:58:00Z", "moving",      0.62, "Mercedes", "Citaro",  (-3.7035, 40.4170), "D1"),
  ("BUS-02", "bus",   0, None, "2026-10-15T07:30:00Z", "maintenance", 0.80, "Mercedes", "Citaro",  (-3.6500, 40.3900), "D2"),
  ("BUS-03", "bus",  38, 3.5,  "2026-10-15T11:55:00Z", "moving",      0.18, "Irizar",   "ie tram", (-3.7090, 40.4150), "D1"),
  ("BUS-04", "bus",   0, None, "2026-10-14T18:00:00Z", "maintenance", 0.55, "Irizar",   "ie tram", (-3.6400, 40.3950), "D2"),
  ("VAN-01", "van",  92, 2.5,  "2026-10-15T11:52:00Z", "moving",      0.40, "Ford",     "Transit", (-3.6900, 40.4300), "D3"),
  ("VAN-02", "van", 108, None, "2026-10-15T11:59:00Z", "moving",      0.12, "Ford",     "Transit", (-3.6000, 40.4500), "D3"),
  ("VAN-03", "van",   0, None, "2026-10-15T09:10:00Z", "parked",      0.90, "Renault",  "Master",  (-3.7040, 40.4180), "D1"),
  ("VAN-04", "van",  61, None, "2026-10-15T11:40:00Z", "moving",      0.33, "Renault",  "Master",  (-3.7500, 40.4000), "D2"),
  ("CAR-01", "car", 125, 0.5,  "2026-10-15T11:57:00Z", "moving",      0.71, "Tesla",    "Model 3", (-3.5800, 40.4700), "D3"),
  ("CAR-02", "car",   0, None, "2026-10-15T08:00:00Z", "parked",      0.05, "Tesla",    "Model 3", (-3.7030, 40.4165), "D1"),
  ("CAR-03", "car",  74, None, "2026-10-15T11:30:00Z", "moving",      0.27, "Seat",     "Leon",    (-3.6800, 40.4100), "D2"),
  ("CAR-04", "car",   0, None, "2026-10-15T06:45:00Z", "parked",      0.66, "Seat",     "Leon",    (-3.6700, 40.4450), "D3"),
]

# BUS-01's two temperature sensors (datasetId)
BUS01_TEMPERATURE = [("urn:ngsi-ld:Sensor:cabin", 21.5), ("urn:ngsi-ld:Sensor:engine", 88.0)]



# -----------------------------------------------------------------------------
#
# Depots - id, name (es), name (en), street, capacity, (lon, lat)
#
DEPOTS = [
  ("D1", "Depósito Centro",   "Central Depot",  "Calle de Atocha 10",           30, (-3.7010, 40.4120)),
  ("D2", "Depósito Vallecas", "Vallecas Depot", "Avenida de la Albufera 300",   45, (-3.6450, 40.3920)),
  ("D3", "Depósito Barajas",  "Airport Depot",  "Avenida de la Hispanidad 2",   60, (-3.5900, 40.4650)),
]



# -----------------------------------------------------------------------------
#
# Parking spots - 25: ten around Plaza Mayor (within ~250 m), fifteen 2-4 km away; 21 free
#
def parkingSpots():
  spots = []
  for i in range(25):
    if i < 10:
      a, r = i * 2 * math.pi / 10, 0.0018           # ~150-200 m around Plaza Mayor
      lon, lat = PLAZA_MAYOR[0] + r * math.cos(a), PLAZA_MAYOR[1] + r * math.sin(a) * 0.76
    else:
      a, r = i * 2 * math.pi / 15, 0.03             # ~2.5 km out
      lon, lat = PLAZA_MAYOR[0] + r * math.cos(a), PLAZA_MAYOR[1] + r * math.sin(a) * 0.76
    status = "occupied" if i in (2, 7, 13, 21) else "free"
    spots.append((f"P-{i + 1:02d}", status, (round(lon, 6), round(lat, 6))))
  return spots

PARKING = parkingSpots()



# -----------------------------------------------------------------------------
#
# Air quality - id, name, (lon, lat), PM10 now; NO2 by the hour on 2026-10-14 (µg/m³) for two stations
#
STATIONS = [
  ("AQ-Retiro",       "Retiro",        (-3.6820, 40.4150), 22),
  ("AQ-PlazaEspana",  "Plaza de España", (-3.7120, 40.4240), 41),
  ("AQ-Castellana",   "Castellana",    (-3.6900, 40.4400), 35),
]

def no2Day(station):
  base = { "AQ-Retiro": 18, "AQ-PlazaEspana": 30 }[station]
  # a morning and an evening peak; integers, so max/avg are exact
  return [base + int(20 * math.exp(-((h - 8) ** 2) / 6) + 25 * math.exp(-((h - 19) ** 2) / 5)) for h in range(24)]

NO2_NOW = { "AQ-Retiro": 27, "AQ-PlazaEspana": 44, "AQ-Castellana": 33 }   # observed 2026-10-15T11:00:00Z



# -----------------------------------------------------------------------------
#
# Helpers the cases use
#
def vid(short):
  return f"urn:ngsi-ld:Vehicle:{short}"



# -----------------------------------------------------------------------------
#
# The NGSI-LD entities
#
def entities():
  out = []
  for (short, kind, speed, acc, obs, status, fuel, brand, model, loc, depot) in VEHICLES:
    sp = { "type": "Property", "value": speed, "unitCode": "KMH", "observedAt": obs }
    if acc is not None:
      sp["accuracy"] = { "type": "Property", "value": acc, "unitCode": "KMH" }
    e = { "id": vid(short), "type": "Vehicle",
          "vehicleType": { "type": "Property", "value": kind },
          "speed":       sp,
          "status":      { "type": "Property", "value": status, "observedAt": obs },
          "fuelLevel":   { "type": "Property", "value": fuel, "unitCode": "P1", "observedAt": obs },
          "brand":       { "type": "Property", "value": { "name": brand, "model": model } },
          "location":    { "type": "GeoProperty", "value": { "type": "Point", "coordinates": list(loc) }, "observedAt": obs },
          "depot":       { "type": "Relationship", "object": f"urn:ngsi-ld:Depot:{depot}", "objectType": "Depot" } }
    if short == "BUS-01":
      e["temperature"] = [ { "type": "Property", "value": v, "unitCode": "CEL", "datasetId": ds, "observedAt": obs } for ds, v in BUS01_TEMPERATURE ]
    out.append(e)

  for (short, es, en, street, cap, loc) in DEPOTS:
    out.append({ "id": f"urn:ngsi-ld:Depot:{short}", "type": "Depot",
                 "name":     { "type": "LanguageProperty", "languageMap": { "es": es, "en": en } },
                 "address":  { "type": "Property", "value": { "streetAddress": street, "addressLocality": "Madrid", "addressCountry": "ES" } },
                 "capacity": { "type": "Property", "value": cap },
                 "location": { "type": "GeoProperty", "value": { "type": "Point", "coordinates": list(loc) } } })

  for (short, status, loc) in PARKING:
    out.append({ "id": f"urn:ngsi-ld:ParkingSpot:{short}", "type": "ParkingSpot",
                 "status":   { "type": "Property", "value": status, "observedAt": "2026-10-15T11:50:00Z" },
                 "location": { "type": "GeoProperty", "value": { "type": "Point", "coordinates": list(loc) } } })

  for (short, name, loc, pm10) in STATIONS:
    first = no2Day(short)[0] if short in ("AQ-Retiro", "AQ-PlazaEspana") else NO2_NOW[short]
    firstAt = "2026-10-14T00:00:00Z" if short in ("AQ-Retiro", "AQ-PlazaEspana") else "2026-10-15T11:00:00Z"
    out.append({ "id": f"urn:ngsi-ld:AirQualityObserved:{short}", "type": "AirQualityObserved",
                 "name":     { "type": "Property", "value": name },
                 "NO2":      { "type": "Property", "value": first, "unitCode": "GQ", "observedAt": firstAt },
                 "PM10":     { "type": "Property", "value": pm10, "unitCode": "GQ", "observedAt": "2026-10-15T11:00:00Z" },
                 "location": { "type": "GeoProperty", "value": { "type": "Point", "coordinates": list(loc) } } })
  return out

SUBSCRIPTION = {
  "id": "urn:ngsi-ld:Subscription:speeding",
  "type": "Subscription",
  "description": "Speeding alert",
  "entities": [ { "type": "Vehicle" } ],
  "watchedAttributes": [ "speed" ],
  "q": "speed>100",
  "notification": { "attributes": [ "speed", "location" ], "endpoint": { "uri": "http://example.org/alerts", "accept": "application/json" } }
}



# -----------------------------------------------------------------------------
#
# seed / temporal - the set into the broker; does the broker keep history
#
def seed(broker):
  history = []
  for station in ("AQ-Retiro", "AQ-PlazaEspana"):
    day = no2Day(station)
    history.append((f"urn:ngsi-ld:AirQualityObserved:{station}", "NO2",
                    [(day[h], f"2026-10-14T{h:02d}:00:00Z", "GQ") for h in range(1, 24)] + [(NO2_NOW[station], "2026-10-15T11:00:00Z", "GQ")]))
  seedSet(broker, TENANT, entities(), history, [SUBSCRIPTION])

def temporal(broker):
  return hasTemporal(broker, TENANT, "urn:ngsi-ld:AirQualityObserved:AQ-Retiro", "NO2")



# -----------------------------------------------------------------------------
#
# The cases - a question, how its answer is checked, the tools that answer it best
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
