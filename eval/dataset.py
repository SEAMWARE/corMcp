#
# FILE            dataset.py
#
# Copyright 2026 Seamware
# SPDX-License-Identifier: Apache-2.0
#
# The evaluation's data: a small Madrid fleet - vehicles, depots, parking spots, air-quality stations with
# a day of history, one subscription. Fixed values, so every answer is known; the cases compute their
# expected answers from these tables, never from hand-typed numbers.
#
# "Now" is 2026-10-15T12:00:00Z - the system prompt says so.
#
import json, math, urllib.error, urllib.request

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
def distanceM(a, b):
  lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
  h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
  return 2 * 6371000 * math.asin(math.sqrt(h))

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
# seed - the tenant emptied of the dataset's ids, then everything created; the history by PATCHes
#
def http(broker, method, path, body=None):
  req = urllib.request.Request(broker + "/ngsi-ld/v1" + path, method=method, data=json.dumps(body).encode() if body is not None else None)
  req.add_header("Content-Type", "application/json")
  req.add_header("NGSILD-Tenant", TENANT)
  try:
    with urllib.request.urlopen(req) as r:
      return r.status
  except urllib.error.HTTPError as e:
    return e.code

def seed(broker):
  ents = entities()
  http(broker, "POST", "/entityOperations/delete", [e["id"] for e in ents])
  for e in ents:                                 # the history of an earlier run, or a run's answers repeat
    http(broker, "DELETE", "/temporal/entities/" + e["id"])
  http(broker, "DELETE", "/subscriptions/" + SUBSCRIPTION["id"])

  status = http(broker, "POST", "/entityOperations/create", ents)
  if status not in (200, 201):
    raise RuntimeError(f"POST /entityOperations/create answered {status}")

  for station in ("AQ-Retiro", "AQ-PlazaEspana"):
    day   = no2Day(station)
    steps = [(day[h], f"2026-10-14T{h:02d}:00:00Z") for h in range(1, 24)] + [(NO2_NOW[station], "2026-10-15T11:00:00Z")]
    for value, at in steps:
      s = http(broker, "PATCH", f"/entities/urn:ngsi-ld:AirQualityObserved:{station}/attrs",
               { "NO2": { "type": "Property", "value": value, "unitCode": "GQ", "observedAt": at } })
      if s != 204:
        raise RuntimeError(f"PATCH NO2 answered {s}")

  status = http(broker, "POST", "/subscriptions", SUBSCRIPTION)
  if status != 201:
    raise RuntimeError(f"POST /subscriptions answered {status}")

def hasTemporal(broker):
  req = urllib.request.Request(broker + "/ngsi-ld/v1/temporal/entities/urn:ngsi-ld:AirQualityObserved:AQ-Retiro?attrs=NO2&lastN=1")
  req.add_header("NGSILD-Tenant", TENANT)
  try:
    with urllib.request.urlopen(req) as r:
      return r.status == 200
  except urllib.error.HTTPError:
    return False
