#!/usr/bin/env python3
#
# FILE            mcpClient.py
#
# Copyright 2026 Seamware
# SPDX-License-Identifier: Apache-2.0
#
# A minimal MCP client over stdio, for the tests: starts corMcp with the given arguments, initializes,
# then sends each request given on stdin (one JSON object a line: { "method": ..., "params": ... }) and
# prints each answer's result (or error), one JSON line each.
#
#   mcpClient.py <corMcp> <corMcp args...> < requests
#
import json, subprocess, sys

proc = subprocess.Popen(sys.argv[1:], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
nextId = 1

def call(method, params=None):
    global nextId
    msg = { "jsonrpc": "2.0", "id": nextId, "method": method }
    if params is not None:
        msg["params"] = params
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        print("corMcp closed stdout", file=sys.stderr)
        sys.exit(1)
    answer = json.loads(line)
    if answer.get("id") != nextId:
        print("wrong id in", line.strip(), file=sys.stderr)
        sys.exit(1)
    nextId += 1
    return answer

init = call("initialize", { "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": { "name": "mcpClient", "version": "0" } })
proc.stdin.write(json.dumps({ "jsonrpc": "2.0", "method": "notifications/initialized" }) + "\n")
proc.stdin.flush()
print(json.dumps(init, sort_keys=True))

for line in sys.stdin:
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("RAW "):                  # sent as is - for the protocol errors
        proc.stdin.write(line[4:] + "\n")
        proc.stdin.flush()
        print(proc.stdout.readline().strip())
        continue
    req = json.loads(line)
    print(json.dumps(call(req["method"], req.get("params")), sort_keys=True))

proc.stdin.close()
proc.wait()
