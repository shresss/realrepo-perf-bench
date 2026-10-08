#!/usr/bin/env bash
# Harbor verifier entry point (hardened 2026-09-30; template for every task).
# 1. Treat Harbor's /logs/verifier bind mount as untrusted while submitted code runs.
# 2. Stage logs/reward in a root-only image-layer directory, then quiesce every task
#    identity, scrub the publication mount, and copy final artifacts out afterward.
# 3. Run Python in isolated mode (-I: no PYTHON* env, no user site) and guarantee a
#    typed fallback even if it crashes.
private_logs=/tests/.runtime-verifier
mkdir -p /logs/verifier
find /logs/verifier -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null
rm -rf "$private_logs"
mkdir -p "$private_logs"
chown root:root "$private_logs"
chmod 0700 "$private_logs"
cd /app || true
python3 -I /tests/verify.py > "$private_logs/verify.log" 2>&1
rc=$?
if [ ! -s "$private_logs/reward.txt" ]; then
  # A shell fallback cannot prove whether the crash happened before or after
  # candidate action began.  Classify conservatively as lost integrity rather
  # than inventing a pre-start infrastructure cause or a model failure.
  printf '{"reason": "verifier_crashed", "validity": "indeterminate_integrity", "causal_validity": "indeterminate_integrity", "score_eligible": false, "model_reward": null, "transport_reward": 0, "denominator_policy": "exclude from primary estimate and regrade the same artifact", "reward": 0, "rc": %s}\n' "$rc" > "$private_logs/metrics.json"
  echo 0 > "$private_logs/reward.txt"
  echo '{"reward": 0}' > "$private_logs/reward.json"
fi
python3 -I /tests/quiesce_uids.py 10001 10002 10003
quiesce_rc=$?
if [ "$quiesce_rc" -ne 0 ]; then
  printf '{"reason": "verifier_epilogue_nonquiescent", "validity": "indeterminate_integrity", "causal_validity": "indeterminate_integrity", "score_eligible": false, "model_reward": null, "transport_reward": 0, "denominator_policy": "exclude from primary estimate and regrade the same artifact", "reward": 0, "rc": %s}\n' "$quiesce_rc" > "$private_logs/metrics.json"
  echo 0 > "$private_logs/reward.txt"
  echo '{"reward": 0}' > "$private_logs/reward.json"
fi
find /logs/verifier -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null
cp "$private_logs/verify.log" /logs/verifier/verify.log
cp "$private_logs/metrics.json" /logs/verifier/metrics.json
cp "$private_logs/reward.txt" /logs/verifier/reward.txt
cp "$private_logs/reward.json" /logs/verifier/reward.json
tail -n 40 "$private_logs/verify.log"
