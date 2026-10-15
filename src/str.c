//
// FILE            str.c
//
// Copyright 2026 Seamware
// SPDX-License-Identifier: Apache-2.0
//
// A growing string, taken from an allocator - for URLs and query strings
//
#include <string.h>                              // strlen, memcpy, strchr

#include "corAlloc/corAlloc.h"                   // corAlloc

#include "corMcp.h"



// -----------------------------------------------------------------------------
//
// strInit -
//
void strInit(McpStr* sP, CorAlloc* allocP, int size)
{
  sP->allocP = allocP;
  sP->size   = size;
  sP->len    = 0;
  sP->buf    = corAlloc(allocP, size);
  sP->buf[0] = 0;
}



// -----------------------------------------------------------------------------
//
// strAddN - the allocator does not free: a grown string leaves its old buffer behind until the call ends
//
void strAddN(McpStr* sP, const char* s, int n)
{
  if (sP->len + n + 1 > sP->size)
  {
    int   size = (sP->len + n + 1) * 2;
    char* buf  = corAlloc(sP->allocP, size);

    memcpy(buf, sP->buf, sP->len + 1);
    sP->buf  = buf;
    sP->size = size;
  }

  memcpy(&sP->buf[sP->len], s, n);
  sP->len += n;
  sP->buf[sP->len] = 0;
}



// -----------------------------------------------------------------------------
//
// strAdd -
//
void strAdd(McpStr* sP, const char* s)
{
  strAddN(sP, s, strlen(s));
}



// -----------------------------------------------------------------------------
//
// strAddUrlEncoded - RFC 3986 percent-encoding: the unreserved characters as they are, and the ones in
// 'keep' (a list parameter's separators), everything else %XX
//
void strAddUrlEncoded(McpStr* sP, const char* s, const char* keep)
{
  static const char hex[] = "0123456789ABCDEF";

  for (const unsigned char* cP = (const unsigned char*) s; *cP != 0; ++cP)
  {
    unsigned char c = *cP;

    if (((c >= 'a') && (c <= 'z')) || ((c >= 'A') && (c <= 'Z')) || ((c >= '0') && (c <= '9')) ||
        (c == '-') || (c == '.') || (c == '_') || (c == '~') || ((keep != NULL) && (strchr(keep, c) != NULL)))
    {
      char ch = (char) c;
      strAddN(sP, &ch, 1);
    }
    else
    {
      char pct[3] = { '%', hex[c >> 4], hex[c & 0xF] };
      strAddN(sP, pct, 3);
    }
  }
}
