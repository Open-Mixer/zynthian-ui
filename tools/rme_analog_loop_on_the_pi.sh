#!/bin/bash
# The RME analog loop proof on the Pi, at each rate asked for, by hand. Run as root on the Pi, under the Pi lock
# (/root/pi-busy names the holder: this script refuses to run without it, and never frees it). At the rate the
# Zynthian runs, the proof runs as the Pi is. At another rate the Zynthian is stopped, a JACK server with the Pi's own
# options but that rate is started, the Zynthian started on it (its chains come back from last_state), the proof runs,
# and the Pi is put back as found: the jack2 unit, the zynthian unit, their state. Whatever happens, the restore runs.
#
#   tools/rme_analog_loop_on_the_pi.sh <holder-word> [rate ...]       # rates default to 48000 96000
#   tools/rme_analog_loop_on_the_pi.sh C2 48000 -- --back system:capture_3,system:capture_4 --xlr-in 3,4   # the red
#
# Arguments after -- go to tools/rme_analog_loop_proof.py. Results in /root/rme-loop/loop-<rate>.{out,md,json}.
#
# Copyright (C) 2026 Pau Aliagas <linuxnow@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

set -u
HOLDER=${1:?the word that names the lock holder in /root/pi-busy}
shift
RATES=()
while [ $# -gt 0 ] && [ "$1" != "--" ]; do RATES+=("$1"); shift; done
[ $# -gt 0 ] && shift
[ ${#RATES[@]} -eq 0 ] && RATES=(48000 96000)
D=/root/rme-loop
HERE=$(cd "$(dirname "$0")" && pwd)
TOOL=$HERE/rme_analog_loop_proof.py
PY=/zynthian/venv/bin/python3
[ -x $PY ] || PY=python3

[ -e /root/pi-busy ] || { echo "REFUSED: the Pi lock /root/pi-busy is not held; take it first, naming yourself"; exit 75; }
grep -q -- "$HOLDER" /root/pi-busy || { echo "BUSY: $(cat /root/pi-busy)"; exit 75; }
mkdir -p $D
# shellcheck disable=SC1091
. /zynthian/config/zynthian_envars.sh
WAS_ZYN=$(systemctl is-active zynthian)
WAS_JACK=$(systemctl is-active jack2)
RATE_WAS=$(jack_samplerate 2>/dev/null || echo none)
echo "AS FOUND: zynthian=$WAS_ZYN jack2=$WAS_JACK rate=$RATE_WAS options=[$JACKD_OPTIONS] lock=$(cat /root/pi-busy)"
MY_JACKD=""

chain_up() {  # the Zynthian's strip and MAIN are in the graph, up to $1 seconds
    local t=0
    while [ $t -lt "$1" ]; do
        jack_lsp 2>/dev/null | grep -q '^zynmixer_chan:input_00a$' && jack_lsp 2>/dev/null | grep -q '^zynmixer_bus:output_00a$' && return 0
        sleep 2; t=$((t + 2))
    done
    return 1
}

restore() {  # only what this script changed: at the Pi's own rate nothing was touched, nothing is restarted
    [ -n "$MY_JACKD" ] || { echo "LEFT AS FOUND rate=$(jack_samplerate 2>/dev/null || echo none) zynthian=$(systemctl is-active zynthian) jack2=$(systemctl is-active jack2) lock=$([ -e /root/pi-busy ] && echo held || echo free)"; return; }
    echo "RESTORING"
    systemctl stop zynthian
    kill "$MY_JACKD" 2>/dev/null; sleep 2
    [ "$WAS_JACK" = active ] && systemctl start jack2 && sleep 3
    [ "$WAS_ZYN" = active ] && systemctl start zynthian && chain_up 120 && sleep 5
    echo "RESTORED rate=$(jack_samplerate 2>/dev/null || echo none) zynthian=$(systemctl is-active zynthian) jack2=$(systemctl is-active jack2) lock=$([ -e /root/pi-busy ] && echo held || echo free)"
}
trap restore EXIT

RC=0
for rate in "${RATES[@]}"; do
    desc="the Pi's jack2 unit: $JACKD_OPTIONS"
    if [ "$(jack_samplerate 2>/dev/null)" != "$rate" ]; then
        opts=${JACKD_OPTIONS//-r $RATE_WAS/-r $rate}
        [ "$opts" = "$JACKD_OPTIONS" ] && opts="$JACKD_OPTIONS -r $rate"
        desc="jackd $opts (the Pi's options at $rate Hz, started by this script)"
        echo "SWITCHING to $rate Hz: stopping zynthian and jack2, starting jackd $opts"
        systemctl stop zynthian; systemctl stop jack2
        if [ -n "$MY_JACKD" ]; then kill "$MY_JACKD" 2>/dev/null; fi
        sleep 3  # the USB device is released a moment after jackd exits: started at once, the next jackd fails to open
        # the jack2 unit's own environment (JACK_NO_AUDIO_RESERVATION, the bus): without it jackd fails to open
        # shellcheck disable=SC2046,SC2086
        env $(systemctl show -p Environment --value jack2) nohup jackd $opts > $D/jackd-$rate.log 2>&1 &
        MY_JACKD=$!
        sleep 8  # no client knocks while the server opens: asked at once, jackd 1.9.22 fails to open
        t=8; while [ $t -lt 45 ] && [ "$(jack_samplerate 2>/dev/null)" != "$rate" ]; do sleep 1; t=$((t + 1)); done
        if [ "$(jack_samplerate 2>/dev/null)" != "$rate" ]; then
            echo "REFUSED rme-analog-loop: no JACK server at $rate Hz after 45 s ($D/jackd-$rate.log): $(tail -3 $D/jackd-$rate.log | tr '\n' ' ')"
            RC=1; continue
        fi
        systemctl start zynthian
        if ! chain_up 150; then
            echo "REFUSED rme-analog-loop: the Zynthian did not bring chain strip 00 and MAIN up at $rate Hz within 150 s"
            RC=1; continue
        fi
        sleep 10
    fi
    echo "RUN at $rate Hz: $(date -u +%FT%TZ)"
    $PY "$TOOL" --rate "$rate" --chain-strip 0 --jack-desc "$desc" --json $D/loop-$rate.json --report $D/loop-$rate.md \
        --capture-dir $D "$@" 2>&1 | tee $D/loop-$rate.out
    rc=${PIPESTATUS[0]}
    echo "RC at $rate Hz: $rc"
    [ "$rc" -ne 0 ] && RC=1
done
exit $RC
