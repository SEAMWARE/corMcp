# corMcp - an MCP server for NGSI-LD brokers

corMcp gives an AI model read access to an NGSI-LD context broker (ETSI TS 104 175) through the
[Model Context Protocol](https://modelcontextprotocol.io). The model asks in tools - "the vehicles faster
than 90 km/h near Sol" - and corMcp makes the NGSI-LD requests: `GET /entities?type=Vehicle&q=speed>90&georel=...`.

It works with any NGSI-LD broker over HTTP. The model never runs in corMcp: it runs at its provider, and an
MCP host (Claude Code, for one) passes its tool calls to corMcp.

## Build

corMcp is built on the cor-libs, as coraine is - sibling checkouts (`../corRest`, `../corJson`, ...), each
built there:

```
make                  # ./corMcp
make install          # /usr/local/bin/corMcp (PREFIX=..., DESTDIR=...)
```

`COR_LIBS=<dir>` for cor-libs checked out elsewhere.

## Run

```
corMcp --broker http://localhost:1026 [--tenant T] [--context URL] [--token-env VAR] [--limit-max N]
```

| Option | Environment | |
|---|---|---|
| `--broker`, `-b` | `CORMCP_BROKER` | the broker's base URL (required) |
| `--tenant`, `-t` | `CORMCP_TENANT` | the tenant every request goes to (`NGSILD-Tenant`); default: the broker's default tenant |
| `--context`, `-ctx` | `CORMCP_CONTEXT` | the @context URL the short names (`Vehicle`, `speed`) expand with, sent as `Link`; default: the core context |
| `--token-env`, `-te` | `CORMCP_TOKEN_ENV` | the environment variable holding a bearer token, sent as `Authorization` - never a command-line argument |
| `--limit-max`, `-lm` | `CORMCP_LIMIT_MAX` | the largest `limit` a tool call may ask for: 1-1000, default 100 (another value: corMcp does not start); a tool call asking for more gets this many |

An option on the command line wins over its environment variable; an environment variable set to a value
the option does not take stops corMcp all the same. `-u` lists the options, `-U` with their environment
variables and defaults.

The transport is stdio: one JSON-RPC message a line on stdin, the answers on stdout, the log on stderr
(every tool call: the tool, its arguments, ok or error, milliseconds).

A session is bound to one broker, one tenant, one @context and one token. No tool takes a tenant or an
@context: the model cannot reach a tenant the user did not choose.

Claude Code, for example:

```
claude mcp add ngsild -- corMcp --broker http://localhost:1026
```

## Tools

All read-only.

| Tool | NGSI-LD |
|---|---|
| Tool | NGSI-LD | Arguments (required in bold) |
|---|---|---|
| `list_types` | `GET /types?details=true` | - |
| `list_attributes` | `GET /attributes?details=true`, or `GET /types/{type}` | type |
| `query_entities` | `GET /entities` | type, ids, idPattern, q, scopeQ, geoQ, csf, pick, omit, datasetId, lang, format, limit, offset |
| `get_entity` | `GET /entities/{id}` | **id**, pick, omit, datasetId, lang, format |
| `count_entities` | `GET /entities?count=true&limit=0` | type, ids, idPattern, q, scopeQ, geoQ, csf |
| `temporal` | `GET /temporal/entities[/{id}]` | **timerel** (`before`, `after`, `between`), **timeAt**, endTimeAt (**required with `between`**), id, type, ids, idPattern, q, scopeQ, geoQ, csf, attrs, timeproperty (default `observedAt`), lastN, aggrMethods, aggrPeriodDuration, pick, omit, datasetId, lang, format, limit, offset |
| `list_subscriptions` | `GET /subscriptions` | limit, offset |
| `query_registrations` | `GET /csourceRegistrations` (NGSI-LD wants at least one filter, § 5.10.2.4) | type, ids, idPattern, attrs, q, csf, limit, offset |

`geoQ` is an object: **georel**, **geometry**, **coordinates**, and geoproperty (default `location`).
A required argument that is missing is a tool error before anything is sent: `'timeAt' is required (a string)`.

What a tool returns:
- **concise** by default - lossless: sub-attributes, `unitCode`, `observedAt`, `datasetId`, Property and
  Relationship all kept. `format: simplified` (the values alone) only when the model asks.
- `temporal` is **normalized** by default (each instance in full); `format: temporalValues` gives
  `[value, time]` pairs, `concise` the concise form. With `aggrMethods` (`totalCount`, `distinctCount`,
  `sum`, `avg`, `min`, `max`, `stddev`, `sumsq`) the request is `options=aggregatedValues` and `format` is
  not used.
- `pick` always keeps `id` and `type`.
- A list: `{ count, returned, more, <items> }`; `limit` 20 by default.
- A string longer than 1000 characters and an array longer than 100 items are cut, with a marker:
  `…[+513 characters cut]`, `…[+51 items cut]`.
- The result is `structuredContent`, and the same JSON, compact, as the text content.
- A broker error is a tool error (`isError`) with the broker's status, title and detail - text the model can
  act on. A bad argument too: `'limit' must be an integer, 1 or more`.

## MCP

The MCP revisions 2025-11-25, 2025-06-18, 2025-03-26 and 2024-11-05: `initialize` answers with the
client's revision when corMcp speaks it, else the newest. Methods: `initialize`, `ping`, `tools/list`,
`tools/call`; notifications are accepted and not answered. No batches (removed from MCP in 2025-06-18).

## Tests

```
BROKER_URL=http://localhost:1026 make test
```

The tests make entities of their own (a type with a per-run suffix), check every tool and the protocol
errors, and delete the entities. A check the broker cannot pass (a broker with no temporal API) is reported
as skipped, with the broker's answer.

## Evaluation

`eval/` measures how well a model answers with corMcp's tools - what the descriptions teach it ("this tool is
for that"). Two sets of fixed data, each seeded in a tenant of its own, and questions in plain language, each
asked in a fresh conversation:

| Set | Tenant | Data | Questions |
|---|---|---|---|
| `fleet` | `mcpeval` | Madrid: 12 vehicles, 3 depots, 25 parking spots, 3 air-quality stations with a day of NO2 history, a subscription | 32 |
| `building` | `mcpbuilding` | Berlin: 2 office buildings, 16 rooms, 4 HVAC units, 2 energy meters with a day of history | 21 |

No example in corMcp's descriptions comes from either set (they use shops: `Store`, `stock`, the Eiffel
Tower), so what a model gets right, the descriptions taught it.

```
ANTHROPIC_API_KEY=... python3 eval/run.py --broker http://localhost:1026 [--set fleet,building] [--model M] [--cases a,b] [--label L]
```

Each answer is scored: right or wrong (the expected answers are computed from the data; lists and numbers
are read from the answer's last line, `ANSWER: ...`, which the evaluation's system prompt asks for), the tools
a good answer uses, and the tool calls against a budget; tokens and seconds are recorded. A call the host
could not route to corMcp (a tool name the model wrote without the host's prefix) is counted apart. A run writes
`eval/results/<time>-<provider>-<model>[-label].json`; `--rescore <file>` scores a run again with the current
cases, without calling the model. The questions that need the temporal API are skipped on a broker without
one.

## Licence

Apache-2.0
