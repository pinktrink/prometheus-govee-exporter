#!/bin/bash

EXPORTER_ARGS=""

if test ! -z "$PORT"; then
    EXPORTER_ARGS="$EXPORTER_ARGS -p $PORT"
fi

if test ! -z "$POLL_INTERVAL"; then
    EXPORTER_ARGS="$EXPORTER_ARGS -i $POLL_INTERVAL"
fi

if test ! -z "$LOG_LEVEL"; then
    EXPORTER_ARGS="$EXPORTER_ARGS --log-level $LOG_LEVEL"
fi

/bin/sh -c "prometheus-govee-exporter $EXPORTER_ARGS $DEVICES"
