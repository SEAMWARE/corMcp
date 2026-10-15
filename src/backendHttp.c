//
// FILE            backendHttp.c
//
// Copyright 2026 Seamware
// SPDX-License-Identifier: Apache-2.0
//
// The http backend - any NGSI-LD broker: one request per tool call, carrying the session's tenant,
// @context and token
//
#include <stdio.h>                               // snprintf
#include <stdlib.h>                              // atoll
#include <string.h>                              // strlen, memcpy
#include <strings.h>                             // strcasecmp

#include "corAlloc/corAlloc.h"                   // corAlloc
#include "corJson/CorJson.h"                     // CorJson
#include "corJson/corJsonCreate.h"               // corJsonCreate
#include "corJson/corJsonParse.h"                // corJsonParse
#include "corRest/corRestClient.h"               // corRestClientMulti*

#include "corMcp.h"



// -----------------------------------------------------------------------------
//
// HTTP_BROKER_MAX - the largest answer read from a broker; a tool's limit keeps answers far below it
//
#define HTTP_BROKER_MAX  (32 * 1024 * 1024)
#define HTTP_TIMEOUT_MS  30000



// -----------------------------------------------------------------------------
//
// httpRequest -
//
static bool httpRequest(CorAlloc* allocP, CorRestVerb verb, const char* path, const char* query, const char* body, McpResponse* respP)
{
  CorRestKeyValue  headers[6];
  int              headerCount = 0;
  McpStr           url;
  char             link[1024];
  char*            auth = NULL;

  respP->status   = 0;
  respP->count    = -1;
  respP->body     = NULL;
  respP->text     = NULL;
  respP->error[0] = 0;

  strInit(&url, allocP, 512);
  strAdd(&url, mcpSession.broker);
  strAdd(&url, "/ngsi-ld/v1");
  strAdd(&url, path);
  if ((query != NULL) && (query[0] != 0))
  {
    strAdd(&url, "?");
    strAdd(&url, query);
  }

  headers[headerCount].key   = (char*) "Accept";
  headers[headerCount].value = (char*) "application/json";
  ++headerCount;

  if (body != NULL)
  {
    headers[headerCount].key   = (char*) "Content-Type";
    headers[headerCount].value = (char*) "application/json";
    ++headerCount;
  }

  if (mcpSession.tenant != NULL)
  {
    headers[headerCount].key   = (char*) "NGSILD-Tenant";
    headers[headerCount].value = (char*) mcpSession.tenant;
    ++headerCount;
  }

  if (mcpSession.context != NULL)
  {
    snprintf(link, sizeof(link), "<%s>; rel=\"http://www.w3.org/ns/json-ld#context\"; type=\"application/ld+json\"", mcpSession.context);
    headers[headerCount].key   = (char*) "Link";
    headers[headerCount].value = link;
    ++headerCount;
  }

  if (mcpSession.token != NULL)
  {
    int alen = strlen(mcpSession.token) + 8;
    auth     = corAlloc(allocP, alen);
    snprintf(auth, alen, "Bearer %s", mcpSession.token);
    headers[headerCount].key   = (char*) "Authorization";
    headers[headerCount].value = auth;
    ++headerCount;
  }

  CorRestClientMulti* multiP = corRestClientMultiCreate(1);
  if (multiP == NULL)
  {
    snprintf(respP->error, sizeof(respP->error), "out of memory");
    return false;
  }

  corRestClientMultiMaxResponse(multiP, HTTP_BROKER_MAX);

  if (corRestClientMultiAdd(multiP, verb, url.buf, headers, headerCount, body, (body != NULL) ? strlen(body) : 0, NULL, NULL) < 0)
  {
    snprintf(respP->error, sizeof(respP->error), "the URL %s could not be used", url.buf);
    corRestClientMultiDestroy(multiP);
    return false;
  }

  corRestClientMultiPerform(multiP, HTTP_TIMEOUT_MS);

  CorRestClientResponse* rP = corRestClientMultiResponse(multiP, 0);

  if ((rP == NULL) || (rP->error != CORR_OK) || (rP->statusCode == 0))
  {
    snprintf(respP->error, sizeof(respP->error), "%s", ((rP != NULL) && (rP->errorDetail[0] != 0)) ? rP->errorDetail : "no answer");
    corRestClientMultiDestroy(multiP);
    return false;
  }

  respP->status = rP->statusCode;

  for (int ix = 0; ix < rP->headerCount; ix++)
  {
    if (strcasecmp(rP->headerV[ix].key, "NGSILD-Results-Count") == 0)
      respP->count = atoll(rP->headerV[ix].value);
  }

  if ((rP->body != NULL) && (rP->bodyLen > 0))
  {
    respP->text = corAlloc(allocP, rP->bodyLen + 1);
    memcpy(respP->text, rP->body, rP->bodyLen);
    respP->text[rP->bodyLen] = 0;

    // The parse works in place: a copy of its own, so the raw text stays readable
    char*   copy = corAlloc(allocP, rP->bodyLen + 1);
    CorJson json;

    memcpy(copy, respP->text, rP->bodyLen + 1);
    corJsonCreate(&json, allocP);
    respP->body = corJsonParse(&json, copy);
  }

  corRestClientMultiDestroy(multiP);
  return true;
}



// -----------------------------------------------------------------------------
//
// mcpBackendHttp -
//
McpBackend mcpBackendHttp = { "http", httpRequest };
