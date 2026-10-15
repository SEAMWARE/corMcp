# corMcp - an MCP server for NGSI-LD brokers

corMcp gives an AI model read access to an NGSI-LD context broker (ETSI TS 104 175) through the
[Model Context Protocol](https://modelcontextprotocol.io). The model asks in tools - "the vehicles faster
than 90 km/h near Sol" - and corMcp makes the NGSI-LD requests: `GET /entities?type=Vehicle&q=speed>90&georel=...`.

It works with any NGSI-LD broker over HTTP. The model never runs in corMcp: it runs at its provider, and an
MCP host (c³, Claude Code, ...) passes its tool calls to corMcp.

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

| Option | |
|---|---|
| `--broker`, `-b` | the broker's base URL (required) |
| `--tenant`, `-t` | the tenant every request goes to (`NGSILD-Tenant`); default: the broker's default tenant |
| `--context`, `-ctx` | the @context URL the short names (`Vehicle`, `speed`) expand with, sent as `Link`; default: the core context |
| `--token-env`, `-te` | the environment variable holding a bearer token, sent as `Authorization` - never a command-line argument |
| `--limit-max`, `-lm` | the largest `limit` a tool call may ask for (default 100); a larger one is lowered |

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
| `list_types` | `GET /types?details=true` |
| `list_attributes` | `GET /attributes?details=true`, or `GET /types/{type}` |
| `query_entities` | `GET /entities` - type, ids, idPattern, q, scopeQ, geoQ, csf, attrs, pick, omit, datasetId, lang, format, limit, offset |
| `get_entity` | `GET /entities/{id}` |
| `count_entities` | `GET /entities?count=true&limit=0` |
| `temporal` | `GET /temporal/entities[/{id}]` - timerel, timeAt, endTimeAt, timeproperty, lastN, aggrMethods, aggrPeriodDuration |
| `list_subscriptions` | `GET /subscriptions` |
| `query_registrations` | `GET /csourceRegistrations` (NGSI-LD wants at least one filter, § 5.10.2.4) |

What a tool returns:
- **concise** by default - lossless: sub-attributes, `unitCode`, `observedAt`, `datasetId`, Property and
  Relationship all kept. `format: simplified` (the values alone) only when the model asks.
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
for that"). A fixed dataset (a Madrid fleet: 12 vehicles, 3 depots, 25 parking spots, 3 air-quality stations
with a day of NO2 history, a subscription) is seeded in the tenant `mcpeval`, and 32 questions in plain
language are asked, each in a fresh conversation:

```
ANTHROPIC_API_KEY=... python3 eval/run.py --broker http://localhost:1026 [--model M] [--cases a,b] [--label L]
```

Each answer is scored: right or wrong (the expected answers are computed from the dataset), the tools a
good answer uses, and the tool calls against a budget; tokens and seconds are recorded. A run writes
`eval/results/<time>-<provider>-<model>[-label].json`; `--rescore <file>` scores a run again with the current
cases, without calling the model. The questions that need the temporal API are skipped on a broker without
one.

## Licence

Apache-2.0
