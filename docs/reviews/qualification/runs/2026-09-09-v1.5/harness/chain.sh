#!/bin/zsh
cd /private/tmp/claude-501/-Users-josepharmand-Projects-val/6dad0650-9c42-4a9a-80d9-cb88832215bf/scratchpad/classifier
for e in high medium low; do
  echo "=== $e start $(date)" >> packet_v15/chain.log
  uv run --quiet --project /Users/josepharmand/Projects/val python run_packet_v15.py $e packet_v15/run_$e.json > packet_v15/run_$e.log 2>&1
  echo "=== $e exit $? $(date)" >> packet_v15/chain.log
done
echo ALLDONE >> packet_v15/chain.log
