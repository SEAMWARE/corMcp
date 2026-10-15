#!/bin/bash
#
# FILE            run.sh
#
# Copyright 2026 Seamware
# SPDX-License-Identifier: Apache-2.0
#
# corMcp's tests against a running NGSI-LD broker: BROKER_URL (default http://127.0.0.1:1026). The tests
# make entities of their own (a per-run type) and delete them at the end.
#
DIR=$(cd "$(dirname "$0")" && pwd)
exec python3 -I "$DIR/check.py" "$DIR/../corMcp" "${BROKER_URL:-http://127.0.0.1:1026}"
