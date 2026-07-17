#!/usr/bin/env bash
set -euo pipefail

environment_id="${1:?environment id is required}"
for attempt in {1..10}; do
  resources="$(aws resourcegroupstaggingapi get-resources \
    --tag-filters Key=Project,Values=Atlas Key=Environment,Values="$environment_id" \
    --query 'ResourceTagMappingList[].ResourceARN' --output json)"
  active="$(jq '[.[] | select(test(":kms:") | not)]' <<<"$resources")"
  if [[ "$(jq length <<<"$active")" == "0" ]]; then
    echo "No active Atlas-tagged resources remain for $environment_id"
    exit 0
  fi
  echo "Cleanup audit attempt $attempt still sees: $active"
  sleep 20
done
echo "Billable or active Atlas-tagged resources remain after teardown" >&2
exit 1
