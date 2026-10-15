//
// FILE            corMcp.c
//
// Copyright 2026 Seamware
// SPDX-License-Identifier: Apache-2.0
//
// corMcp - an MCP server for NGSI-LD brokers. Over stdio: one JSON-RPC message a line on stdin, the
// answers on stdout, the log on stderr - what an MCP host (c³, Claude Code, ...) starts.
//
//   corMcp --broker http://host:port [--tenant T] [--context URL] [--token-env VAR] [--limit-max N]
//
#include <stdio.h>                               // getline, printf, fprintf
#include <stdlib.h>                              // getenv, free
#include <string.h>                              // strlen, strncmp

#include "corAlloc/corAllocBufferInit.h"         // corAllocBufferInit
#include "corAlloc/corAllocBufferReset.h"        // corAllocBufferReset
#include "corArgs/corArgs.h"                     // corArgsInit, corArgsParse
#include "corArgs/CorArg.h"                      // CorArg

#include "corMcp.h"



// -----------------------------------------------------------------------------
//
// Globals
//
McpSession   mcpSession;
McpBackend*  mcpBackend = &mcpBackendHttp;

static char* brokerArg   = NULL;
static char* tenantArg   = NULL;
static char* contextArg  = NULL;
static char* tokenEnvArg = NULL;
static int   limitMaxArg = 100;



// -----------------------------------------------------------------------------
//
// options -
//
static CorArg options[] =
{
  { "--broker",    "-b",  CorArgString, &brokerArg,   CorArgReq, NULL,     NULL,  NULL,       "the broker's base URL: http://host:port" },
  { "--tenant",    "-t",  CorArgString, &tenantArg,   CorArgOpt, NULL,     NULL,  NULL,       "the tenant every request goes to (default: the broker's default tenant)" },
  { "--context",   "-ctx", CorArgString, &contextArg, CorArgOpt, NULL,     NULL,  NULL,       "the @context URL short names expand with (default: the core context)" },
  { "--token-env", "-te", CorArgString, &tokenEnvArg, CorArgOpt, NULL,     NULL,  NULL,       "the environment variable holding the bearer token sent to the broker" },
  { "--limit-max", "-lm", CorArgInt,    &limitMaxArg, CorArgOpt, _vp 100,  _vp 1, _vp 1000,   "the largest 'limit' a tool call may ask for" },
  CORARGS_END
};



// -----------------------------------------------------------------------------
//
// main -
//
int main(int argC, char* argV[])
{
  if (corArgsInit("corMcp", options, "CORMCP_") != CorArgsOk)
  {
    fprintf(stderr, "corMcp: corArgsInit failed\n");
    return 1;
  }

  if (corArgsParse(argC, argV) != CorArgsOk)
    return 1;

  if ((strncmp(brokerArg, "http://", 7) != 0) && (strncmp(brokerArg, "https://", 8) != 0))
  {
    fprintf(stderr, "corMcp: --broker %s - an http:// or https:// URL\n", brokerArg);
    return 1;
  }

  int len = strlen(brokerArg);                   // http://host:1026/ -> http://host:1026
  while ((len > 0) && (brokerArg[len - 1] == '/'))
    brokerArg[--len] = 0;

  mcpSession.broker   = brokerArg;
  mcpSession.tenant   = ((tenantArg  != NULL) && (tenantArg[0]  != 0)) ? tenantArg  : NULL;
  mcpSession.context  = ((contextArg != NULL) && (contextArg[0] != 0)) ? contextArg : NULL;
  mcpSession.token    = NULL;
  mcpSession.limitMax = limitMaxArg;

  if (tokenEnvArg != NULL)
  {
    mcpSession.token = getenv(tokenEnvArg);
    if ((mcpSession.token == NULL) || (mcpSession.token[0] == 0))
    {
      fprintf(stderr, "corMcp: --token-env %s - the variable is not set\n", tokenEnvArg);
      return 1;
    }
  }

  fprintf(stderr, "corMcp %s - broker %s, tenant %s, %s backend, stdio\n", CORMCP_VERSION, mcpSession.broker,
          (mcpSession.tenant != NULL) ? mcpSession.tenant : "(default)", mcpBackend->name);

  //
  // One message a line. Each one gets an allocator of its own, reset when its answer is out.
  //
  char*    line     = NULL;
  size_t   lineSize = 0;
  CorAlloc alloc;
  char     buf[64 * 1024];

  corAllocBufferInit(&alloc, buf, sizeof(buf), 1024 * 1024, NULL, "corMcp message");

  while (getline(&line, &lineSize, stdin) != -1)
  {
    int n = strlen(line);
    while ((n > 0) && ((line[n - 1] == '\n') || (line[n - 1] == '\r')))
      line[--n] = 0;

    if (n == 0)
      continue;

    char* out = rpcHandle(&alloc, line);
    if (out != NULL)
    {
      fputs(out, stdout);
      fputc('\n', stdout);
      fflush(stdout);
    }

    corAllocBufferReset(&alloc, true);
  }

  free(line);
  corAllocBufferReset(&alloc, false);
  return 0;
}
