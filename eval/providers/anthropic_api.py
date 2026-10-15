#
# FILE            anthropic_api.py
#
# Copyright 2026 Seamware
# SPDX-License-Identifier: Apache-2.0
#
# The Anthropic Messages API as the model: the runner is the MCP host - corMcp's tools offered to the model,
# its tool calls passed to corMcp, until the model answers. The key: $ANTHROPIC_API_KEY.
#
import json, os, subprocess, time, urllib.request

API = "https://api.anthropic.com/v1/messages"
MAX_TURNS = 12



class Mcp:
  def __init__(self, cmd):
    self.p  = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    self.id = 0
    self.call("initialize", { "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": { "name": "corMcp-eval", "version": "0" } })
    self.p.stdin.write(json.dumps({ "jsonrpc": "2.0", "method": "notifications/initialized" }) + "\n")
    self.p.stdin.flush()

  def call(self, method, params=None):
    self.id += 1
    self.p.stdin.write(json.dumps({ "jsonrpc": "2.0", "id": self.id, "method": method, "params": params or {} }) + "\n")
    self.p.stdin.flush()
    return json.loads(self.p.stdout.readline())

  def close(self):
    self.p.stdin.close()
    self.p.wait()



def messages(key, body):
  req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST")
  req.add_header("x-api-key", key)
  req.add_header("anthropic-version", "2023-06-01")
  req.add_header("content-type", "application/json")
  with urllib.request.urlopen(req, timeout=300) as r:
    return json.loads(r.read())



def run(question, system, mcpCmd, model):
  key = os.environ.get("ANTHROPIC_API_KEY")
  if not key:
    raise RuntimeError("ANTHROPIC_API_KEY is not set")

  t0    = time.time()
  mcp   = Mcp(mcpCmd)
  tools = [ { "name": t["name"], "description": t["description"], "input_schema": t["inputSchema"] }
            for t in mcp.call("tools/list")["result"]["tools"] ]
  msgs  = [ { "role": "user", "content": question } ]
  calls = []
  usage = { "input": 0, "output": 0, "cacheRead": 0 }
  answer = ""

  try:
    for turn in range(MAX_TURNS):
      resp = messages(key, { "model": model, "max_tokens": 4096, "system": system, "tools": tools, "messages": msgs })
      u = resp.get("usage", {})
      usage["input"]     += u.get("input_tokens", 0)
      usage["output"]    += u.get("output_tokens", 0)
      usage["cacheRead"] += u.get("cache_read_input_tokens", 0)

      msgs.append({ "role": "assistant", "content": resp["content"] })
      uses = [b for b in resp["content"] if b["type"] == "tool_use"]
      if not uses:
        answer = "".join(b.get("text", "") for b in resp["content"] if b["type"] == "text")
        break

      results = []
      for b in uses:
        r = mcp.call("tools/call", { "name": b["name"], "arguments": b["input"] })
        res = r.get("result") or { "content": [{ "type": "text", "text": json.dumps(r.get("error")) }], "isError": True }
        calls.append({ "name": b["name"], "input": b["input"], "isError": bool(res.get("isError")) })
        if res.get("isError"):
          calls[-1]["error"] = res["content"][0]["text"][:500]
        results.append({ "type": "tool_result", "tool_use_id": b["id"], "content": res["content"][0]["text"], "is_error": bool(res.get("isError")) })
      msgs.append({ "role": "user", "content": results })
  finally:
    mcp.close()

  return { "answer": answer, "calls": calls, "turns": turn + 1, "usage": usage, "costUsd": None, "seconds": round(time.time() - t0, 1) }
