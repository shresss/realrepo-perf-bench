#!/usr/bin/env bash
# The slow job, as finance runs it. Fixture script: do not edit.
set -euo pipefail

cd "$(dirname "$0")/.."

run_dir="$(mktemp -d "${TMPDIR:-/tmp}/ledgerly-visible.XXXXXXXX")"
socket_path="$run_dir/database.sock"
ready_file="$run_dir/ready.json"
metrics_file="$run_dir/metrics.json"
service_log="$run_dir/service.log"
service_pid=""
if command -v python3 >/dev/null 2>&1; then
    python_bin="python3"
else
    python_bin="python"
fi

stop_service() {
    if [[ -z "$service_pid" ]]; then
        return
    fi
    if kill -0 "$service_pid" 2>/dev/null; then
        kill -TERM "$service_pid" 2>/dev/null || true
    fi
    if ! wait "$service_pid"; then
        echo "warning: visible database service exited abnormally" >&2
    fi
    service_pid=""
}

cleanup() {
    stop_service
    if [[ -n "$run_dir" && -d "$run_dir" ]]; then
        rm -rf -- "$run_dir"
    fi
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

"$python_bin" workloads/visible_sqlite_service.py \
    --db data/visible.db \
    --socket "$socket_path" \
    --ready-file "$ready_file" \
    --metrics-file "$metrics_file" \
    >"$service_log" 2>&1 &
service_pid=$!

for _ in {1..200}; do
    if [[ -S "$socket_path" && -s "$ready_file" ]]; then
        break
    fi
    if ! kill -0 "$service_pid" 2>/dev/null; then
        echo "visible database service failed during startup" >&2
        cat "$service_log" >&2 || true
        exit 1
    fi
    sleep 0.05
done

if [[ ! -S "$socket_path" || ! -s "$ready_file" ]]; then
    echo "visible database service did not become ready" >&2
    cat "$service_log" >&2 || true
    exit 1
fi

set +e
time "$python_bin" -m ledgerly.report \
    --db "metered+unix://$socket_path" \
    --month 2026-08 \
    --out out/statements.json
report_status=$?
set -e

stop_service
cat "$service_log" || true
if [[ ! -s "$metrics_file" ]]; then
    echo "warning: visible diagnostic metrics were not produced" >&2
fi

exit "$report_status"
