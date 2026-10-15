#ifndef CORMCP_CORMCP_H_
#define CORMCP_CORMCP_H_

//
// FILE            corMcp.h
//
// Copyright 2026 Seamware
// SPDX-License-Identifier: Apache-2.0
//
// corMcp - an MCP server for NGSI-LD brokers: the shared declarations
//
#include <stdbool.h>                             // bool

#include "corAlloc/CorAlloc.h"                   // CorAlloc
#include "corTree/CorNode.h"                     // CorNode
#include "corRest/CorRestVerb.h"                 // CorRestVerb



// -----------------------------------------------------------------------------
//
// CORMCP_VERSION -
//
#define CORMCP_VERSION "0.1.0"



// -----------------------------------------------------------------------------
//
// McpSession - what one MCP session is bound to: one broker, one tenant, one @context, one token
//
// The model never picks any of them - no tool takes a tenant or an @context.
//
typedef struct McpSession
{
  const char*  broker;                           // the broker's base URL: http://host:port (no /ngsi-ld/v1)
  const char*  tenant;                           // NGSILD-Tenant, NULL: the default tenant
  const char*  context;                          // the @context URL sent as Link, NULL: the core context
  const char*  token;                            // the bearer token sent as Authorization, NULL: none
  int          limitMax;                         // the largest 'limit' a tool call may ask for
} McpSession;

extern McpSession mcpSession;



// -----------------------------------------------------------------------------
//
// McpResponse - a broker's answer, as the tools see it
//
typedef struct McpResponse
{
  int          status;                           // the HTTP status, 0: the broker was not reached
  long long    count;                            // NGSILD-Results-Count, -1: not in the answer
  CorNode*     body;                             // the parsed body, NULL: none (or not JSON)
  char*        text;                             // the raw body (zero-terminated), NULL: none
  char         error[256];                       // why the broker was not reached (status 0)
} McpResponse;



// -----------------------------------------------------------------------------
//
// McpBackend - how a tool's NGSI-LD request reaches the broker
//
// The tools build requests, never DB calls: every backend runs the broker's own code path. One
// backend today: http (any NGSI-LD broker). cor:// and in-process come later.
//
typedef struct McpBackend
{
  const char* name;
  bool (*request)(CorAlloc* allocP, CorRestVerb verb, const char* path, const char* query, const char* body, McpResponse* respP);
} McpBackend;

extern McpBackend* mcpBackend;
extern McpBackend  mcpBackendHttp;



// -----------------------------------------------------------------------------
//
// McpStr - a growing string, taken from an allocator
//
typedef struct McpStr
{
  CorAlloc*  allocP;
  char*      buf;
  int        len;
  int        size;
} McpStr;

extern void  strInit(McpStr* sP, CorAlloc* allocP, int size);
extern void  strAdd(McpStr* sP, const char* s);
extern void  strAddN(McpStr* sP, const char* s, int n);
extern void  strAddUrlEncoded(McpStr* sP, const char* s, const char* keep);



// -----------------------------------------------------------------------------
//
// rpc.c
//
extern char* rpcHandle(CorAlloc* allocP, char* line);



// -----------------------------------------------------------------------------
//
// tools.c
//
extern CorNode* toolsList(CorAlloc* allocP);
extern CorNode* toolsCall(CorAlloc* allocP, const char* name, CorNode* argsP, bool* unknownP);
extern const char* toolsInstructions;



// -----------------------------------------------------------------------------
//
// shape.c
//
extern void      shapeCut(CorAlloc* allocP, CorNode* nodeP);
extern CorNode*  shapeResult(CorAlloc* allocP, CorNode* structuredP, bool isError);
extern CorNode*  shapeError(CorAlloc* allocP, const char* fmt, ...) __attribute__((format(printf, 2, 3)));
extern CorNode*  shapeBrokerError(CorAlloc* allocP, McpResponse* respP);
extern char*     shapeRender(CorAlloc* allocP, CorNode* nodeP);

#endif  // CORMCP_CORMCP_H_
