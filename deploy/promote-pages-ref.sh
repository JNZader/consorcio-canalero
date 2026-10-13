#!/usr/bin/env bash
# CI-05 / CI-07: move refs/heads/pages-production to PROMOTE_SHA.
#
# The caller must NOT check out PROMOTE_SHA. This script only talks to the
# GitHub API. It refuses force-updates: a diverged branch fails, and a SHA
# that is already behind pages-production is left in place (no rewind).
# PROMOTE_SHA must be main itself or an ancestor of main.
set -euo pipefail

: "${PROMOTE_SHA:?PROMOTE_SHA is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"

if ! [[ "${PROMOTE_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "PROMOTE_SHA is not a 40-character commit sha" >&2
  exit 1
fi

main_status="$(gh api --method GET "/repos/${GITHUB_REPOSITORY}/compare/main...${PROMOTE_SHA}" --jq '.status')"
case "${main_status}" in
  identical|behind) ;;
  *)
    echo "refusing to promote ${PROMOTE_SHA}: not contained in main (status=${main_status})" >&2
    exit 1
    ;;
esac

target="heads/pages-production"
if ! current="$(gh api --method GET "/repos/${GITHUB_REPOSITORY}/git/ref/${target}" --jq '.object.sha')"; then
  gh api --method POST "/repos/${GITHUB_REPOSITORY}/git/refs" \
    -f ref="refs/${target}" \
    -f sha="${PROMOTE_SHA}" >/dev/null
  echo "created ${target} at ${PROMOTE_SHA}"
  exit 0
fi

if [[ "${current}" == "${PROMOTE_SHA}" ]]; then
  echo "already at ${PROMOTE_SHA}"
  exit 0
fi

status="$(gh api --method GET "/repos/${GITHUB_REPOSITORY}/compare/${current}...${PROMOTE_SHA}" --jq '.status')"
case "${status}" in
  ahead|identical)
    gh api --method PATCH "/repos/${GITHUB_REPOSITORY}/git/refs/${target}" \
      -f sha="${PROMOTE_SHA}" \
      -F force=false >/dev/null
    echo "fast-forwarded ${target} ${current} -> ${PROMOTE_SHA}"
    ;;
  behind)
    echo "${target} is already ahead of ${PROMOTE_SHA}; not rewinding"
    ;;
  *)
    echo "refusing to promote: ${target} and ${PROMOTE_SHA} have diverged (status=${status})" >&2
    exit 1
    ;;
esac
