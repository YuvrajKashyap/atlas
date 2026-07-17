#!/usr/bin/env bash
set -euo pipefail

bucket="${1:?bucket name is required}"
while true; do
  payload="$(aws s3api list-object-versions --bucket "$bucket" --output json | jq '{Objects: ((.Versions // []) + (.DeleteMarkers // []) | map({Key, VersionId})), Quiet: true}')"
  count="$(jq '.Objects | length' <<<"$payload")"
  if [[ "$count" == "0" ]]; then break; fi
  aws s3api delete-objects --bucket "$bucket" --delete "$payload" >/dev/null
done
aws s3api delete-bucket --bucket "$bucket"
