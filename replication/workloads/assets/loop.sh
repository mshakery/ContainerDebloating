#!/bin/sh
set -eu

N="$1"

iter_payload() {
    printf 'greenlab-iter-%s\n' "$1"
}

COLD_HASH=$(iter_payload 1 | sha256sum | awk '{print $1}')
printf 'COLD %s\n' "$COLD_HASH"

i=1
TMP=/tmp/greenlab-loop.$$
: > "$TMP"
while [ "$i" -le "$N" ]; do
    iter_payload "$i" >> "$TMP"
    i=$((i + 1))
done
STEADY_HASH=$(sha256sum < "$TMP" | awk '{print $1}')
rm -f "$TMP"
printf 'STEADY %s\n' "$STEADY_HASH"
