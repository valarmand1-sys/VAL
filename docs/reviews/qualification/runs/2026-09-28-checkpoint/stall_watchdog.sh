#!/bin/zsh
# Watches a bench run's service log; when a resume is not followed by a turn timeline
# within 45 s, asks the scratch service for every thread's stack (SIGUSR1, faulthandler)
# once per stall. 28 September 2026 — the C1a stall.
LOG=$1
typeset -A dumped
while true; do
  last=$(grep "voice resume:" $LOG 2>/dev/null | tail -1)
  if [[ -n $last ]]; then
    at=${last%% *}; at=${at%.*}
    now=$(date +%s)
    after=$(awk -v t="$at" '$1 > t' $LOG | grep -c "voice turn timeline")
    if (( now - at > 45 && after == 0 )) && [[ -z ${dumped[$at]} ]]; then
      pid=$(pgrep -f "serve_experiment.py" | xargs -I{} sh -c "ps -o pid=,comm= -p {}" | grep -i python | awk "{print \$1}" | head -1)
      [[ -n $pid ]] && kill -USR1 $pid && echo "stall after resume at $at: stacks requested from $pid"
      dumped[$at]=1
    fi
  fi
  sleep 5
done
