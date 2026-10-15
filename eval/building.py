#
# FILE            building.py
#
# Copyright 2026 Seamware
# SPDX-License-Identifier: Apache-2.0
#
# The evaluation set "building": two office buildings in Berlin - rooms with temperature, CO2 and
# occupancy, the HVAC units that serve them, an energy meter per building with a day of history - and its
# cases. Nothing in it is in the fleet set or in corMcp's descriptions: what the model gets right here, the
# descriptions taught it, not the examples.
#
# "Now" is 2026-10-15T12:00:00Z - the system prompt says so.
#
import math, re
from common import *

TENANT = "mcpbuilding"

BRANDENBURG_GATE = (13.3777, 52.5163)



# -----------------------------------------------------------------------------
#
# Buildings - id, name, street, postal code, floors, (lon, lat)
#
BUILDINGS = [
  ("B1", "Alexanderhaus",   "Alexanderplatz 3",     "10178", 6, (13.4132, 52.5219)),
  ("B2", "Pariser Hof",     "Pariser Platz 6",      "10117", 4, (13.3810, 52.5165)),
]



# -----------------------------------------------------------------------------
#
# HVAC units - id, building, mode, setpoint (°C), power (kW)
#
HVAC = [
  ("H1", "B1", "heating", 21.0, 12.5),
  ("H2", "B1", "cooling", 23.0,  8.0),
  ("H3", "B2", "fault",   22.0,  0.0),
  ("H4", "B2", "heating", 20.5, 10.0),
]



# -----------------------------------------------------------------------------
#
# Rooms - id, building, floor, kind, German name, English name, capacity, occupancy, temperature (°C),
#         temperature accuracy (None: none), temperature observedAt, CO2 (ppm), HVAC unit
#
ROOMS = [
  ("A-101", "B1", 1, "office",  "Büro Nord",              "North office",        6,  4, 21.5, None, "2026-10-15T11:55:00Z",  620, "H1"),
  ("A-102", "B1", 1, "meeting", "Besprechungsraum Spree", "Spree meeting room", 10, 12, 24.8, 0.3,  "2026-10-15T11:58:00Z", 1350, "H1"),
  ("A-103", "B1", 1, "kitchen", "Küche",                  "Kitchen",             8,  2, 22.0, None, "2026-10-15T11:50:00Z",  540, "H1"),
  ("A-201", "B1", 2, "office",  "Büro Süd",               "South office",        6,  0, 20.1, None, "2026-10-15T09:20:00Z",  430, "H2"),
  ("A-202", "B1", 2, "meeting", "Besprechungsraum Havel", "Havel meeting room",  8,  0, 22.4, 0.3,  "2026-10-15T11:57:00Z",  480, "H2"),
  ("A-203", "B1", 2, "office",  "Großraumbüro",           "Open-plan office",   24, 19, 25.0, 1.5,  "2026-10-15T11:59:00Z", 1120, "H2"),
  ("A-301", "B1", 3, "meeting", "Besprechungsraum Dahme", "Dahme meeting room",  6,  0, 21.8, None, "2026-10-15T11:52:00Z",  450, "H2"),
  ("A-001", "B1", 0, "server",  "Serverraum",             "Server room",         2,  0, 19.5, None, "2026-10-15T11:59:00Z",  410, "H2"),
  ("P-101", "B2", 1, "office",  "Büro Linden",            "Linden office",       4,  3, 23.9, None, "2026-10-15T11:56:00Z",  880, "H3"),
  ("P-102", "B2", 1, "meeting", "Besprechungsraum Tor",   "Gate meeting room",  12,  0, 24.2, 2.0,  "2026-10-15T11:54:00Z",  700, "H3"),
  ("P-103", "B2", 1, "office",  "Büro Tiergarten",        "Tiergarten office",   4,  6, 26.1, None, "2026-10-15T11:58:00Z", 1480, "H3"),
  ("P-201", "B2", 2, "office",  "Büro Ost",               "East office",         6,  5, 21.2, None, "2026-10-15T10:40:00Z",  760, "H4"),
  ("P-202", "B2", 2, "kitchen", "Teeküche",               "Tea kitchen",         4,  1, 22.6, None, "2026-10-15T11:51:00Z",  590, "H4"),
  ("P-203", "B2", 2, "meeting", "Besprechungsraum Quadriga", "Quadriga meeting room", 8, 3, 22.9, None, "2026-10-15T11:53:00Z", 940, "H4"),
  ("P-301", "B2", 3, "office",  "Büro West",              "West office",         6,  0, 20.4, None, "2026-10-15T08:15:00Z",  420, "H4"),
  ("P-302", "B2", 3, "meeting", "Besprechungsraum Brandenburg", "Brandenburg meeting room", 16, 9, 23.1, None, "2026-10-15T11:49:00Z", 1010, "H4"),
]

# The server room's two temperature probes (datasetId)
SERVER_PROBES = [("urn:ngsi-ld:Probe:rack-front", 19.5), ("urn:ngsi-ld:Probe:rack-back", 23.5)]   # both below 24: not "warm"



# -----------------------------------------------------------------------------
#
# Energy - a meter per building, kWh by the hour on 2026-10-14
#
def energyDay(meter):
  base, peak = { "M1": (14, 30), "M2": (9, 22) }[meter]
  # one peak hour, 13:00 - so "when" has one answer
  return [base + (int(peak * math.sin(math.pi * (h - 7) / 11)) if 7 <= h <= 18 else 0) + (3 if h == 13 else 0) for h in range(24)]



# -----------------------------------------------------------------------------
#
# The NGSI-LD entities
#
def rid(short):
  return f"urn:ngsi-ld:Room:{short}"

def entities():
  out = []
  for (b, name, street, postal, floors, loc) in BUILDINGS:
    out.append({ "id": f"urn:ngsi-ld:Building:{b}", "type": "Building",
                 "name":     { "type": "Property", "value": name },
                 "address":  { "type": "Property", "value": { "streetAddress": street, "postalCode": postal, "addressLocality": "Berlin", "addressCountry": "DE" } },
                 "floors":   { "type": "Property", "value": floors },
                 "location": { "type": "GeoProperty", "value": { "type": "Point", "coordinates": list(loc) } } })

  for (h, b, mode, setpoint, power) in HVAC:
    out.append({ "id": f"urn:ngsi-ld:HvacUnit:{h}", "type": "HvacUnit",
                 "mode":     { "type": "Property", "value": mode, "observedAt": "2026-10-15T11:45:00Z" },
                 "setpoint": { "type": "Property", "value": setpoint, "unitCode": "CEL" },
                 "power":    { "type": "Property", "value": power, "unitCode": "KWT", "observedAt": "2026-10-15T11:45:00Z" },
                 "building": { "type": "Relationship", "object": f"urn:ngsi-ld:Building:{b}" } })

  for (short, b, floor, kind, de, en, cap, occ, temp, acc, obs, co2, hvac) in ROOMS:
    t = { "type": "Property", "value": temp, "unitCode": "CEL", "observedAt": obs }
    if acc is not None:
      t["accuracy"] = { "type": "Property", "value": acc, "unitCode": "CEL" }
    if short == "A-001":
      t = [ { "type": "Property", "value": v, "unitCode": "CEL", "observedAt": obs, "datasetId": ds } for ds, v in SERVER_PROBES ]
    out.append({ "id": rid(short), "type": "Room",
                 "name":        { "type": "LanguageProperty", "languageMap": { "de": de, "en": en } },
                 "roomType":    { "type": "Property", "value": kind },
                 "floor":       { "type": "Property", "value": floor },
                 "capacity":    { "type": "Property", "value": cap },
                 "occupancy":   { "type": "Property", "value": occ, "observedAt": obs },
                 "temperature": t,
                 "co2":         { "type": "Property", "value": co2, "unitCode": "59", "observedAt": obs },
                 "building":    { "type": "Relationship", "object": f"urn:ngsi-ld:Building:{b}" },
                 "hvac":        { "type": "Relationship", "object": f"urn:ngsi-ld:HvacUnit:{hvac}" } })

  for (m, b) in (("M1", "B1"), ("M2", "B2")):
    out.append({ "id": f"urn:ngsi-ld:EnergyMeter:{m}", "type": "EnergyMeter",
                 "energy":   { "type": "Property", "value": energyDay(m)[0], "unitCode": "KWH", "observedAt": "2026-10-14T00:00:00Z" },
                 "building": { "type": "Relationship", "object": f"urn:ngsi-ld:Building:{b}" } })
  return out



# -----------------------------------------------------------------------------
#
# seed / temporal
#
def seed(broker):
  history = [ (f"urn:ngsi-ld:EnergyMeter:{m}", "energy", [(energyDay(m)[h], f"2026-10-14T{h:02d}:00:00Z", "KWH") for h in range(1, 24)])
              for m in ("M1", "M2") ]
  seedSet(broker, TENANT, entities(), history, [])

def temporal(broker):
  return hasTemporal(broker, TENANT, "urn:ngsi-ld:EnergyMeter:M1", "energy")



# -----------------------------------------------------------------------------
#
# The cases - as in fleet.py
#
rooms        = [r[0] for r in ROOMS]
warm         = [r[0] for r in ROOMS if r[8] > 24]
highCo2      = [r[0] for r in ROOMS if r[11] > 1000]
overfull     = [r[0] for r in ROOMS if r[7] > r[6]]
emptyMeeting = [r[0] for r in ROOMS if r[3] == "meeting" and r[7] == 0]
stale        = [r[0] for r in ROOMS if r[10] < "2026-10-15T11:00:00Z"]
faulty       = [h for h in HVAC if h[2] == "fault"][0]
faultyRooms  = [r[0] for r in ROOMS if r[12] == faulty[0]]
b1Meetings   = [r[0] for r in ROOMS if r[1] == "B1" and r[3] == "meeting"]
b1People     = sum(r[7] for r in ROOMS if r[1] == "B1")
heating      = [h for h in HVAC if h[2] == "heating"]
heatAvg      = sum(h[3] for h in heating) / len(heating)
a203         = [r for r in ROOMS if r[0] == "A-203"][0]
nearestB     = min(BUILDINGS, key=lambda b: distanceM(b[5], BRANDENBURG_GATE))
m1Day        = energyDay("M1")
m1MaxH       = m1Day.index(max(m1Day))
m2Sum        = sum(energyDay("M2"))

def other(chosen):
  return ids([r for r in rooms if r not in chosen])

CASES = [
  { "id": "types", "q": "What is in the broker?",
    "must": ["Building", "Room", "HvacUnit", "EnergyMeter"], "tools": ["list_types"], "calls": 1 },
  { "id": "countRooms", "q": "How many rooms are there?",
    "must": [num(len(ROOMS))], "tools": ["count_entities"], "calls": 1 },
  { "id": "warm", "q": "Which rooms are warmer than 24 °C?",
    "must": ids(warm), "mustNot": other(warm), "tools": ["query_entities"], "calls": 1 },
  { "id": "highCo2", "q": "Where is the CO2 above 1000 ppm?",
    "must": ids(highCo2), "mustNot": other(highCo2), "tools": ["query_entities"], "calls": 1 },
  { "id": "overfull", "q": "Which rooms have more people in them than they are meant for?",
    "must": ids(overfull), "mustNot": other(overfull), "tools": ["query_entities"], "calls": 1 },
  { "id": "emptyMeeting", "q": "Which meeting rooms are free right now?",
    "must": ids(emptyMeeting), "mustNot": other(emptyMeeting), "tools": ["query_entities"], "calls": 1 },
  { "id": "stale", "q": "Which rooms have not reported their temperature in the last hour?",
    "must": ids(stale), "mustNot": other(stale), "tools": ["query_entities"], "calls": 1 },
  { "id": "fault", "q": "Is any HVAC unit broken? Which rooms does it serve?",
    "must": ids(faultyRooms), "mustNot": other(faultyRooms), "mustText": [re.escape(faulty[0]) + r"\b"], "tools": ["query_entities"], "calls": 2 },
  { "id": "b1Meetings", "q": "How many meeting rooms does the Alexanderhaus have?",
    "must": [num(len(b1Meetings))], "tools": ["count_entities|query_entities"], "calls": 2 },
  { "id": "b1People", "q": "How many people are in the Alexanderhaus right now?",
    "must": [num(b1People)], "tools": ["query_entities"], "calls": 2 },
  { "id": "fahrenheit", "q": "What is the temperature in room A-203, in Fahrenheit?",
    "must": [num(a203[8] * 9 / 5 + 32)], "tools": ["get_entity|query_entities"], "calls": 1 },
  { "id": "accuracy", "q": "How precise is the temperature reading in A-203?",
    "must": [num(a203[9])], "tools": ["get_entity|query_entities"], "calls": 1 },
  { "id": "serverProbes", "q": "The server room has two temperature probes. What do they read?",
    "must": [num(SERVER_PROBES[0][1]), num(SERVER_PROBES[1][1])], "tools": ["query_entities|get_entity"], "calls": 2 },
  { "id": "germanName", "q": "What is the German name of the Quadriga meeting room?",
    "must": [r"Besprechungsraum Quadriga"], "tools": ["query_entities"], "calls": 1 },
  { "id": "nearestBuilding", "q": "Which of the buildings is closest to the Brandenburg Gate?",
    "must": [re.escape(nearestB[1]) + rf"|\b{nearestB[0]}\b"], "tools": ["query_entities"], "calls": 1 },
  { "id": "address", "q": "What is the address of the building room P-203 is in?",
    "must": [r"Pariser Platz 6"], "tools": ["get_entity", "get_entity|query_entities"], "calls": 2 },
  { "id": "heatAvg", "q": "What is the average setpoint of the HVAC units that are heating?",
    "must": [num(heatAvg, 2)], "tools": ["query_entities"], "calls": 1 },
  { "id": "energyPeak", "q": "When did the Alexanderhaus use the most energy on 14 October 2026, and how much?",
    "must": [num(max(m1Day))], "mustText": [rf"{m1MaxH:02d}:00|{m1MaxH}\s*(h|:00|am|pm)|{m1MaxH - 12}\s*pm"], "tools": ["temporal"], "calls": 2, "temporal": True },
  { "id": "energySum", "q": "How much energy did the Pariser Hof use in total on 14 October 2026?",
    "must": [num(m2Sum)], "tools": ["temporal"], "calls": 2, "temporal": True },
  { "id": "printers", "q": "How many printers are there?",
    "must": [NONE], "tools": ["list_types|count_entities"], "calls": 2 },
  { "id": "noSubscriptions", "q": "Is anyone notified when a room changes?",
    "must": [NONE], "tools": ["list_subscriptions"], "calls": 1 },
]
