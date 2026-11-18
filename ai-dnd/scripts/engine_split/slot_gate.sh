#!/bin/bash
# Guarded shards with the gate probe first (game.py split, Plan 2). From Git Bash:
#   slot_gate.sh FSLOT WT LABEL SHARDS TIMEOUT 'regex'
# Same staging and sync as AI-DND-TOOLS/slot.sh, same shards and summary as AI-DND-TOOLS/slot_par.sh, with one change:
# every shard's selector list starts with api.tests.gate_boot, so the label's tokens (fon, n4, n7) reach the guarded child
# before any test module loads. The launcher builds the child's environment from scratch: a flag set outside never arrives.
# Inside WSL this file runs itself from the synced slot copy: slot_gate.sh --shards ROOT PREFIX JOBS TIMEOUT REGEXFILE
# Exit: 0 only when every shard reported PASS and printed a summary (NO_SUMMARY counts as at least 1); otherwise the worst launcher code (1 FAIL, 2 BLOCKED, 3 TIMEOUT, 4 no modules); 2 before any sync for a label gate_boot refuses.
if [ "${1:-}" != --shards ]; then
  set -euo pipefail; unset MSYS_NO_PATHCONV
  N=$1; WT=$2; label=$3; jobs=$4; t=$5; rx=$6
  D=/c/Users/Kadir/Desktop/$WT; R=/root/aidnd-env-$N; S=/c/Users/Kadir/Desktop/AI-DND-TOOLS; M=/mnt/c/Users/Kadir/Desktop/AI-DND-TOOLS
  # gate_boot's own rule prints the tokens the label applies (TOKENS ...) and refuses a glued one, before any staging or sync
  MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 --cd "/mnt/c/Users/Kadir/Desktop/$WT/ai-dnd" -- "$R/proj/.venv/bin/python" -B -m api.tests.gate_boot --label "$label" < /dev/null || exit 2
  cd "$D"
  if [ -z "${NOSTAGE:-}" ]; then git add -A -- ai-dnd content lib artifacts .github start_local.ps1; T=$(git write-tree); else T=HEAD; fi
  git -c core.autocrlf=false -c core.eol=lf archive -o "$S/tree-$N.tar" "$T" ai-dnd content tools lib .github artifacts start_local.ps1
  export MSYS_NO_PATHCONV=1
  wsl.exe -d Ubuntu-24.04 -- bash "$M/slot_sync.sh" "$R" "$M/tree-$N.tar" | tail -1
  printf '%s' "$rx" > "$S/rx-$N.txt"
  exec wsl.exe -d Ubuntu-24.04 -- bash "$R/src/ai-dnd/scripts/engine_split/slot_gate.sh" --shards "$R" "$label" "$jobs" "$t" "$M/rx-$N.txt"
fi
R=$2; prefix=$3; jobs=$4; t=$5; rx=$(cat "$6")
cd "$R"
api=$(cd src/ai-dnd/api/tests && ls test_*.py | sed 's/\.py$//' | grep -E "$rx" | sed 's/^/api.tests./')
top=$(cd src/ai-dnd && ls test_*.py | sed 's/\.py$//' | grep -E "$rx")
mods=$(printf '%s\n%s\n' "$api" "$top" | sed '/^$/d')
[ -n "$mods" ] || { echo "modules=0"; exit 4; }
echo "modules=$(echo "$mods" | wc -l) api=$(echo "$api" | sed '/^$/d' | wc -l) top=$(echo "$top" | sed '/^$/d' | wc -l)"
rm -f "$R"/.shard-*
# a reused prefix must not leave old runs for the results glob to pick up
rm -rf "$R"/runs/*-"$prefix"-[0-9]*
i=0; for m in $mods; do echo "$m" >> "$R/.shard-$((i % jobs))"; i=$((i+1)); done
for j in $(seq 0 $((jobs-1))); do
  [ -s "$R/.shard-$j" ] || continue
  ( proj/.venv/bin/python linux_guarded_launcher.py "$prefix-$j" "$t" api.tests.gate_boot $(cat "$R/.shard-$j") >/dev/null; echo $? > "$R/.shard-$j.code" ) &
done
wait
worst=0
for j in $(seq 0 $((jobs-1))); do
  [ -s "$R/.shard-$j" ] || continue
  code=$(cat "$R/.shard-$j.code" 2>/dev/null || echo 2)
  echo "shard $j exit=$code"
  [ "$code" -gt "$worst" ] && worst=$code
done
rm -f "$R"/.shard-*
python3 - "$prefix" <<'PY'
import glob,re,sys
tot=skip=0;bad=set();missing=[]
for d in sorted(glob.glob(f'runs/*-{sys.argv[1]}-[0-9]*')):
    t=open(d+'/target.log',errors='ignore').read()
    m=re.search(r'Ran (\d+) tests? in',t)
    if m: tot+=int(m.group(1))
    else: missing.append(d)
    s=re.search(r'skipped=(\d+)',t); skip+=int(s.group(1)) if s else 0
    bad|=set(re.findall(r'^(?:FAIL|ERROR): \S+ \(([\w.]+)',t,re.M))
print('tests',tot,'skipped',skip,'failing_ids',len(bad))
for d in missing: print('NO_SUMMARY',d)
open(f'{sys.argv[1]}.bad','w').write('\n'.join(sorted(bad)))
for b in sorted(bad)[:30]: print(' ',b[:115])
sys.exit(1 if missing else 0)
PY
summ=$?
[ "$summ" -gt "$worst" ] && worst=$summ
echo "PAR_EXIT=$worst"
exit "$worst"
