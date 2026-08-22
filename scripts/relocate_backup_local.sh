#!/bin/sh
set -eu

fail() { printf "REJECTED: %s\n" "$*" >&2; exit 1; }
mode=${1:-}
case "$mode" in admit|execute) ;; *) fail "mode must be admit or execute" ;; esac
for tool in awk cat cmp cp dd docker git kill mkdir mv od rm rmdir sha256sum sort sync xargs; do
  command -v "$tool" >/dev/null 2>&1 || fail "missing prerequisite: $tool"
done
for value in RELOCATE_SOURCE RELOCATE_DEST RELOCATE_CRON_FILE RELOCATE_CRON_OLD RELOCATE_CRON_NEW RELOCATE_GIT_RECEIPT RELOCATE_CONTAINER_RECEIPT RELOCATE_SHA256; do
  eval "present=\${$value:-}"
  [ -n "$present" ] || fail "missing setting: $value"
done
source=$RELOCATE_SOURCE
dest=$RELOCATE_DEST
cron=$RELOCATE_CRON_FILE
git_receipt=$RELOCATE_GIT_RECEIPT
container_receipt=$RELOCATE_CONTAINER_RECEIPT
expected_hash=$RELOCATE_SHA256
for path in "$source" "$dest" "$cron" "$git_receipt" "$container_receipt"; do
  case "$path" in /*) ;; *) fail "path is not absolute" ;; esac
done
parent=${dest%/*}
[ "$parent" != "$dest" ] && [ -d "$parent" ] || fail "destination parent is invalid"
[ -f "$cron" ] && [ -f "$git_receipt" ] && [ -f "$container_receipt" ] || fail "receipt input is missing"
[ "$RELOCATE_CRON_OLD" != "$RELOCATE_CRON_NEW" ] || fail "cron lines must differ"
[ "$source" != "$dest" ] || fail "source and destination overlap"
for path in "$cron" "$git_receipt" "$container_receipt"; do
  [ "$source" != "$path" ] && [ "$dest" != "$path" ] || fail "paths must be pairwise distinct"
done

last_byte() {
  od -An -tx1 "$1" | awk "{for (i=1;i<=NF;i++) byte=\$i} END {print byte}"
}
require_git_receipt() {
  [ -s "$git_receipt" ] && [ "$(last_byte "$git_receipt")" = 00 ] || fail "git receipt lacks terminal NUL"
  git status --porcelain -z | cmp -s "$git_receipt" - || fail "git receipt differs"
}
require_container_receipt() {
  [ -s "$container_receipt" ] || fail "container receipt is empty"
  docker ps -q --no-trunc | xargs -r docker inspect --format "{{.Id}}|{{.Config.Image}}|{{.State.StartedAt}}|{{.RestartCount}}|{{.Name}}" |
    awk -F '|' 'NF != 5 {bad=1; next} {n=$5; if (substr(n,1,1) != "/" ) n="/" n; print $1 "|" $2 "|" $3 "|" $4 "|" n} END {exit bad}' |
    LC_ALL=C sort | cmp -s "$container_receipt" - || fail "container receipt differs"
}
count_line() { awk -v line="$2" "\$0 == line {count++} END {print count+0}" "$1"; }
hash_of() { sha256sum "$1" | awk "NR == 1 {print \$1}"; }
state() {
  old_count=$(count_line "$cron" "$RELOCATE_CRON_OLD")
  new_count=$(count_line "$cron" "$RELOCATE_CRON_NEW")
  if [ -f "$source" ] && [ ! -e "$dest" ] && [ "$old_count" = 1 ] && [ "$new_count" = 0 ]; then
    printf ready
  elif [ ! -e "$source" ] && [ -f "$dest" ] && [ "$old_count" = 0 ] && [ "$new_count" = 1 ] && [ "$(hash_of "$dest")" = "$expected_hash" ]; then
    printf complete
  else
    printf partial
  fi
}

require_git_receipt
require_container_receipt
current=$(state)
[ "$current" != partial ] || fail "divergent relocation state"
if [ "$mode" = admit ]; then
  printf "ADMITTED:%s\n" "$current"
  exit 0
fi
if [ "$current" = complete ]; then
  printf "SUCCESS:NOOP\n"
  exit 0
fi

lock="$parent/.backup-relocator.lock"
owner_file="$lock/owner"
tmp="$parent/.backup-relocator.$$.tmp"
archive="$parent/.backup-relocator.$$.archive"
cron_tmp="$parent/.backup-relocator.$$.cron"
cron_saved="$parent/.backup-relocator.$$.saved"
locked=0
started=0
committed=0
dest_created=0
cron_changed=0
source_removed=0
acquire_lock() {
  if mkdir "$lock" 2>/dev/null; then :; else
    [ -f "$owner_file" ] || fail "relocation lock is held without provable owner"
    owner=""
    read -r owner < "$owner_file" || :
    case "$owner" in ""|*[!0-9]*) fail "relocation lock owner marker is unreadable" ;; esac
    [ ! -e "/proc/$owner" ] || fail "relocation lock is held by live process $owner"
    mv "$lock" "$lock.$$.stale" 2>/dev/null || fail "relocation lock is held"
    rm -f "$lock.$$.stale/owner"
    rmdir "$lock.$$.stale" || fail "stale relocation lock could not be released"
    mkdir "$lock" || fail "relocation lock is held"
  fi
  printf "%s\n" $$ > "$owner_file"
  locked=1
}
release_lock() {
  rm -f "$owner_file"
  rmdir "$lock" || :
  locked=0
}
rollback() {
  set +e
  [ "$source_removed" = 0 ] || cp -p "$archive" "$source"
  [ "$cron_changed" = 0 ] || cp -p "$cron_saved" "$cron"
  [ "$dest_created" = 0 ] || rm -f "$dest"
  rm -f "$tmp" "$cron_tmp" "$cron_saved" "$archive"
  [ "$locked" = 0 ] || release_lock
  printf "ROLLED_BACK\n" >&2
}
finish() {
  status=$?
  trap - 0
  trap "" HUP INT TERM
  if [ "$status" -ne 0 ] && [ "$started" = 1 ] && [ "$committed" = 0 ]; then rollback; fi
  rm -f "$tmp" "$cron_tmp" "$cron_saved" "$archive"
  [ "$locked" = 0 ] || release_lock
  exit "$status"
}
trap finish 0
trap "exit 1" HUP INT TERM
acquire_lock
require_git_receipt
require_container_receipt
current=$(state)
if [ "$current" = complete ]; then
  printf "SUCCESS:NOOP\n"
  exit 0
fi
[ "$current" = ready ] || fail "state changed before mutation"
fail_step=""
[ "${RELOCATE_TEST_HOOKS:-}" != 1 ] || fail_step=${RELOCATE_FAIL_STEP:-}
started=1
cp -p "$source" "$archive"
cp -p "$source" "$tmp"
dest_created=1
mv "$tmp" "$dest"
[ "$fail_step" != dest ] || exit 1
[ "$fail_step" != cron ] || exit 1
cp -p "$cron" "$cron_saved"
awk -v old="$RELOCATE_CRON_OLD" -v new="$RELOCATE_CRON_NEW" "\$0 == old {print new; next} {print}" "$cron" > "$cron_tmp"
cron_changed=1
cat "$cron_tmp" > "$cron"
[ "$(state)" = partial ] || fail "source must remain until final removal"
[ "$(count_line "$cron" "$RELOCATE_CRON_OLD")" = 0 ] && [ "$(count_line "$cron" "$RELOCATE_CRON_NEW")" = 1 ] || fail "cron replacement is not exact"
[ "$(hash_of "$dest")" = "$expected_hash" ] || fail "destination hash differs"
[ "$fail_step" != signal ] || kill -TERM $$
sync "$dest" "$cron" "$parent"
source_removed=1
rm "$source"
[ "$fail_step" != postrm ] || kill -TERM $$
rm "$archive"
committed=1
printf "SUCCESS:RELOCATED\n"
