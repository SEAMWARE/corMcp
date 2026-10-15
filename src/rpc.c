//
// FILE            rpc.c
//
// Copyright 2026 Seamware
// SPDX-License-Identifier: Apache-2.0
//
// JSON-RPC 2.0 - one message in, one answer out (none for a notification). The MCP methods a tools-only
// server needs: initialize, ping, tools/list, tools/call.
//
#include <stdio.h>                               // fprintf
#include <string.h>                              // strcmp
#include <time.h>                                // clock_gettime

#include "corJson/CorJson.h"                     // CorJson
#include "corJson/corJsonCreate.h"               // corJsonCreate
#include "corJson/corJsonParse.h"                // corJsonParse
#include "corTree/corTreeBuilder.h"              // corTreeObject, corTreeString, ...
#include "corTree/corTreeLookup.h"               // corTreeLookup

#include "corMcp.h"



// -----------------------------------------------------------------------------
//
// protocolVersions - the MCP revisions this server speaks, the newest first
//
static const char* protocolVersions[] = { "2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05", NULL };



// -----------------------------------------------------------------------------
//
// JSON-RPC error codes
//
#define RPC_PARSE_ERROR       -32700
#define RPC_INVALID_REQUEST   -32600
#define RPC_METHOD_NOT_FOUND  -32601
#define RPC_INVALID_PARAMS    -32602



// -----------------------------------------------------------------------------
//
// answer - { jsonrpc, id, result | error }
//
static char* answer(CorAlloc* allocP, CorNode* idP, CorNode* resultP, int code, const char* message)
{
  CorNode* outP = corTreeObject(allocP, NULL);

  corTreeChildAdd(outP, corTreeString(allocP, "jsonrpc", "2.0"));

  if (idP != NULL)
  {
    idP->name = (char*) "id";
    idP->next = NULL;
    corTreeChildAdd(outP, idP);
  }
  else
    corTreeChildAdd(outP, corTreeNull(allocP, "id"));

  if (resultP != NULL)
  {
    resultP->name = (char*) "result";
    corTreeChildAdd(outP, resultP);
  }
  else
  {
    CorNode* errP = corTreeObject(allocP, "error");
    corTreeChildAdd(errP, corTreeInteger(allocP, "code", code));
    corTreeChildAdd(errP, corTreeString(allocP, "message", message));
    corTreeChildAdd(outP, errP);
  }

  return shapeRender(allocP, outP);
}



// -----------------------------------------------------------------------------
//
// initialize - the client's protocolVersion when this server speaks it, else the newest this server speaks
//
static CorNode* initialize(CorAlloc* allocP, CorNode* paramsP)
{
  CorNode*    versionP = (paramsP != NULL) ? corTreeLookup(paramsP, "protocolVersion") : NULL;
  const char* version  = protocolVersions[0];

  if ((versionP != NULL) && (versionP->type == CorString))
  {
    for (int ix = 0; protocolVersions[ix] != NULL; ix++)
    {
      if (strcmp(protocolVersions[ix], versionP->value.s) == 0)
        version = protocolVersions[ix];
    }
  }

  CorNode* resultP = corTreeObject(allocP, NULL);
  CorNode* capsP   = corTreeObject(allocP, "capabilities");
  CorNode* toolsP  = corTreeObject(allocP, "tools");
  CorNode* infoP   = corTreeObject(allocP, "serverInfo");

  corTreeChildAdd(toolsP, corTreeBoolean(allocP, "listChanged", false));
  corTreeChildAdd(capsP, toolsP);

  corTreeChildAdd(infoP, corTreeString(allocP, "name",    "corMcp"));
  corTreeChildAdd(infoP, corTreeString(allocP, "title",   "NGSI-LD broker"));
  corTreeChildAdd(infoP, corTreeString(allocP, "version", CORMCP_VERSION));

  corTreeChildAdd(resultP, corTreeString(allocP, "protocolVersion", version));
  corTreeChildAdd(resultP, capsP);
  corTreeChildAdd(resultP, infoP);
  corTreeChildAdd(resultP, corTreeString(allocP, "instructions", toolsInstructions));

  return resultP;
}



// -----------------------------------------------------------------------------
//
// toolCall - tools/call, logged: tool, arguments, milliseconds, ok or error
//
static char* toolCall(CorAlloc* allocP, CorNode* idP, CorNode* paramsP)
{
  CorNode* nameP = (paramsP != NULL) ? corTreeLookup(paramsP, "name")      : NULL;
  CorNode* argsP = (paramsP != NULL) ? corTreeLookup(paramsP, "arguments") : NULL;

  if ((nameP == NULL) || (nameP->type != CorString))
    return answer(allocP, idP, NULL, RPC_INVALID_PARAMS, "tools/call needs params.name");

  char* args = (argsP != NULL) ? shapeRender(allocP, argsP) : "{}";

  struct timespec t0, t1;
  clock_gettime(CLOCK_MONOTONIC, &t0);

  bool     unknown;
  CorNode* resultP = toolsCall(allocP, nameP->value.s, argsP, &unknown);

  clock_gettime(CLOCK_MONOTONIC, &t1);
  long ms = (t1.tv_sec - t0.tv_sec) * 1000 + (t1.tv_nsec - t0.tv_nsec) / 1000000;

  if (unknown)
  {
    char message[256];
    snprintf(message, sizeof(message), "Unknown tool: %s", nameP->value.s);
    fprintf(stderr, "corMcp: tool %s - unknown\n", nameP->value.s);
    return answer(allocP, idP, NULL, RPC_INVALID_PARAMS, message);
  }

  fprintf(stderr, "corMcp: tool %s %s - %s, %ld ms\n", nameP->value.s, args, (corTreeLookup(resultP, "isError") != NULL) ? "error" : "ok", ms);
  return answer(allocP, idP, resultP, 0, NULL);
}



// -----------------------------------------------------------------------------
//
// rpcHandle - one message; NULL: nothing to answer (a notification, a response)
//
char* rpcHandle(CorAlloc* allocP, char* line)
{
  CorJson json;

  corJsonCreate(&json, allocP);
  CorNode* msgP = corJsonParse(&json, line);

  if (msgP == NULL)
    return answer(allocP, NULL, NULL, RPC_PARSE_ERROR, "Parse error");

  if (msgP->type != CorObject)                   // a batch (an array) is not part of MCP since 2025-06-18
    return answer(allocP, NULL, NULL, RPC_INVALID_REQUEST, "Invalid Request: one JSON-RPC object per message");

  CorNode* idP     = corTreeLookup(msgP, "id");
  CorNode* methodP = corTreeLookup(msgP, "method");
  CorNode* paramsP = corTreeLookup(msgP, "params");

  if ((methodP == NULL) || (methodP->type != CorString))
  {
    if (idP == NULL)
      return answer(allocP, NULL, NULL, RPC_INVALID_REQUEST, "Invalid Request: no method");
    return NULL;                                 // a response to a request of ours - there are none: ignored
  }

  if (idP == NULL)                               // a notification: notifications/initialized, notifications/cancelled
    return NULL;

  if ((idP->type != CorString) && (idP->type != CorInt))
    return answer(allocP, NULL, NULL, RPC_INVALID_REQUEST, "Invalid Request: the id must be a string or an integer");

  const char* method = methodP->value.s;

  if (strcmp(method, "initialize") == 0)
    return answer(allocP, idP, initialize(allocP, paramsP), 0, NULL);
  if (strcmp(method, "ping") == 0)
    return answer(allocP, idP, corTreeObject(allocP, NULL), 0, NULL);
  if (strcmp(method, "tools/list") == 0)
    return answer(allocP, idP, toolsList(allocP), 0, NULL);
  if (strcmp(method, "tools/call") == 0)
    return toolCall(allocP, idP, paramsP);

  char message[256];
  snprintf(message, sizeof(message), "Method not found: %s", method);
  return answer(allocP, idP, NULL, RPC_METHOD_NOT_FOUND, message);
}
