#!/bin/sh
# Run as root in the ephemeral Linux task container. The task's packaging owns
# pixi context, pinned dependencies, source extraction and private input copies.
set -u
umask 077
TASK_STAGE=/tests/.runtime-result
TASK_PYTHON=${TASK_PYTHON:-/usr/local/bin/python}
"$TASK_PYTHON" -I -B /tests/runtime/publish.py "$TASK_STAGE" --prepare || exit 1
# BEGIN runtime-v1.1 state hardening. Root only, after publish --prepare has
# quiesced both worker UIDs and before any worker exists. Shared scratch
# directories start empty and root-only; workers keep HOME/TMPDIR in their own
# per-invocation writable dir. /tmp keeps its contents (the verifier mkdtemp runs
# there as root) but loses world write. /app (the submitted tree, mode 0777 under
# Harbor) becomes root-owned and not writable by group or others. verify.py
# records the observed result and also sweeps per invocation.
# review r01: any hardening failure is a verifier problem, never a model result.
# verify.py is then not run; publish.py turns exit code 86 into a verifier_invalid
# receipt (reason verifier_crashed_or_missing_receipt, verifier_exit_code 86) and
# the published verify.log names the step that failed.
TASK_HARDENING_RC=86
TASK_HARDENING_FAILED=0
task_hardening_failed() {
  echo "runtime-v1.1 hardening failed: $1" >&2
  echo "runtime-v1.1 hardening failed: $1 (verifier_exit_code $TASK_HARDENING_RC)" >>"$TASK_STAGE/verify.log"
  TASK_HARDENING_FAILED=1
}
for TASK_STATE_DIR in /var/tmp /dev/shm /dev/mqueue /run/lock; do
  if [ -d "$TASK_STATE_DIR" ] && [ ! -L "$TASK_STATE_DIR" ]; then
    find "$TASK_STATE_DIR" -xdev -mindepth 1 -delete \
      || task_hardening_failed "could not empty $TASK_STATE_DIR"
    { chown root:root "$TASK_STATE_DIR" && chmod 0755 "$TASK_STATE_DIR"; } \
      || task_hardening_failed "could not restrict $TASK_STATE_DIR"
  fi
done
{ chown root:root /tmp && chmod 0755 /tmp; } \
  || task_hardening_failed "could not restrict /tmp"
if [ -d /app ] && [ ! -L /app ]; then
  { chown -R -h root:root /app && chmod -R go-w /app; } \
    || task_hardening_failed "could not restrict /app"
fi
if [ "$TASK_HARDENING_FAILED" -ne 0 ]; then
  "$TASK_PYTHON" -I -B /tests/runtime/publish.py "$TASK_STAGE" --rc "$TASK_HARDENING_RC"
  exit $?
fi
# END runtime-v1.1 state hardening
# BEGIN runtime-v1.1 CPU pin for parallel official Harbor regrades (coordinator 06:15).
# `harbor jobs regrade ... --ve AQ_PIN_CPU=<k>` runs verify.py under taskset so every timed worker pins to CPU k
# (verify.py pins workers to the lowest CPU it is allowed). Unset or non-numeric: unchanged behavior (lowest CPU).
# Baseline and candidate roles of one verification always share the same CPU, so paired ratios stay like-for-like.
TASK_PIN_PREFIX=""
case "${AQ_PIN_CPU:-}" in
  ''|*[!0-9]*) ;;
  *) if command -v taskset >/dev/null 2>&1; then TASK_PIN_PREFIX="taskset -c $AQ_PIN_CPU"; fi ;;
esac
# END runtime-v1.1 CPU pin
set +e
$TASK_PIN_PREFIX "$TASK_PYTHON" -I -B /tests/runtime/verify.py \
  --task /tests/task --baseline /tests/pristine --candidate /app \
  --tools /tests/tools --native-upstream /tests/native-upstream \
  --policy /tests/policy.json --output "$TASK_STAGE" --python "$TASK_PYTHON" \
  >"$TASK_STAGE/verify.log" 2>&1
TASK_VERIFY_RC=$?
"$TASK_PYTHON" -I -B /tests/runtime/publish.py "$TASK_STAGE" --rc "$TASK_VERIFY_RC"
TASK_PUBLISH_RC=$?
exit "$TASK_PUBLISH_RC"
