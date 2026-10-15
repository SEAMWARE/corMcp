//
// FILE            shape.c
//
// Copyright 2026 Seamware
// SPDX-License-Identifier: Apache-2.0
//
// What a tool call returns: the result as structuredContent and the same JSON, compact, as text; long
// strings and big arrays cut with a marker; errors as text the model can act on
//
#include <stdarg.h>                              // va_list
#include <stdio.h>                               // snprintf, vsnprintf
#include <string.h>                              // strlen

#include "corAlloc/corAlloc.h"                   // corAlloc
#include "corAlloc/corAllocStrdup.h"             // corAllocStrdup
#include "corJson/corJsonRender.h"               // corJsonFastRender
#include "corJson/corJsonRenderSize.h"           // corJsonFastRenderSize
#include "corTree/corTreeBuilder.h"              // corTreeObject, corTreeString, ...
#include "corTree/corTreeLookup.h"               // corTreeLookup

#include "corMcp.h"



// -----------------------------------------------------------------------------
//
// The cuts - a string longer than SHAPE_STRING_MAX, an array longer than SHAPE_ARRAY_MAX (a GeoProperty's
// polygon, a long list in a value)
//
#define SHAPE_STRING_MAX  1000
#define SHAPE_ARRAY_MAX   100



// -----------------------------------------------------------------------------
//
// shapeCut - in place
//
void shapeCut(CorAlloc* allocP, CorNode* nodeP)
{
  if (nodeP->type == CorString)
  {
    int len = strlen(nodeP->value.s);

    if (len > SHAPE_STRING_MAX)
    {
      char* s = corAlloc(allocP, SHAPE_STRING_MAX + 64);
      snprintf(s, SHAPE_STRING_MAX + 64, "%.*s…[+%d characters cut]", SHAPE_STRING_MAX, nodeP->value.s, len - SHAPE_STRING_MAX);
      nodeP->value.s = s;
    }
    return;
  }

  if ((nodeP->type != CorObject) && (nodeP->type != CorArray))
    return;

  int       ix   = 0;
  CorNode*  prev = NULL;

  for (CorNode* childP = nodeP->value.head; childP != NULL; childP = childP->next)
  {
    if ((nodeP->type == CorArray) && (ix == SHAPE_ARRAY_MAX))
    {
      int more = 0;
      for (CorNode* restP = childP; restP != NULL; restP = restP->next)
        ++more;

      char marker[64];
      snprintf(marker, sizeof(marker), "…[+%d items cut]", more);

      CorNode* markerP = corTreeString(allocP, NULL, marker);
      prev->next       = markerP;
      nodeP->value.tail = markerP;
      return;
    }

    shapeCut(allocP, childP);
    prev = childP;
    ++ix;
  }
}



// -----------------------------------------------------------------------------
//
// shapeRender - compact JSON
//
char* shapeRender(CorAlloc* allocP, CorNode* nodeP)
{
  char* name = nodeP->name;                     // the value alone, not the member
  nodeP->name = NULL;

  int   size = corJsonFastRenderSize(nodeP) + 1;
  char* out  = corAlloc(allocP, size);

  corJsonFastRender(nodeP, out);
  nodeP->name = name;
  return out;
}



// -----------------------------------------------------------------------------
//
// shapeResult - { content: [{ type: text, text }], structuredContent, isError }
//
CorNode* shapeResult(CorAlloc* allocP, CorNode* structuredP, bool isError)
{
  CorNode* resultP  = corTreeObject(allocP, NULL);
  CorNode* contentP = corTreeArray(allocP, "content");
  CorNode* textP    = corTreeObject(allocP, NULL);

  corTreeChildAdd(textP, corTreeString(allocP, "type", "text"));
  corTreeChildAdd(textP, corTreeString(allocP, "text", shapeRender(allocP, structuredP)));
  corTreeChildAdd(contentP, textP);
  corTreeChildAdd(resultP, contentP);

  structuredP->name = (char*) "structuredContent";
  corTreeChildAdd(resultP, structuredP);

  if (isError)
    corTreeChildAdd(resultP, corTreeBoolean(allocP, "isError", true));

  return resultP;
}



// -----------------------------------------------------------------------------
//
// shapeError - a tool error: { error: <text> }, isError
//
CorNode* shapeError(CorAlloc* allocP, const char* fmt, ...)
{
  char    text[1024];
  va_list ap;

  va_start(ap, fmt);
  vsnprintf(text, sizeof(text), fmt, ap);
  va_end(ap);

  CorNode* errP = corTreeObject(allocP, NULL);
  corTreeChildAdd(errP, corTreeString(allocP, "error", text));
  return shapeResult(allocP, errP, true);
}



// -----------------------------------------------------------------------------
//
// shapeBrokerError - the broker's answer was not a success: its ProblemDetails, title and detail, with the status
//
CorNode* shapeBrokerError(CorAlloc* allocP, McpResponse* respP)
{
  if (respP->status == 0)
    return shapeError(allocP, "the broker at %s did not answer: %s", mcpSession.broker, respP->error);

  CorNode* titleP  = (respP->body != NULL) ? corTreeLookup(respP->body, "title")  : NULL;
  CorNode* detailP = (respP->body != NULL) ? corTreeLookup(respP->body, "detail") : NULL;
  CorNode* typeP   = (respP->body != NULL) ? corTreeLookup(respP->body, "type")   : NULL;

  CorNode* errP = corTreeObject(allocP, NULL);
  corTreeChildAdd(errP, corTreeInteger(allocP, "status", respP->status));

  if ((typeP != NULL) && (typeP->type == CorString))
    corTreeChildAdd(errP, corTreeString(allocP, "type", typeP->value.s));
  if ((titleP != NULL) && (titleP->type == CorString))
    corTreeChildAdd(errP, corTreeString(allocP, "title", titleP->value.s));
  if ((detailP != NULL) && (detailP->type == CorString))
    corTreeChildAdd(errP, corTreeString(allocP, "detail", detailP->value.s));

  if ((titleP == NULL) && (detailP == NULL) && (respP->text != NULL))
  {
    CorNode* textP = corTreeString(allocP, "body", respP->text);
    shapeCut(allocP, textP);
    corTreeChildAdd(errP, textP);
  }

  return shapeResult(allocP, errP, true);
}
