#!/bin/zsh
# One line of memory state: free %, swap used, wired and compressed pages, what LM Studio holds.
free=$(memory_pressure -Q 2>/dev/null | awk -F': ' '/free percentage/ {print $2}')
swap=$(sysctl -n vm.swapusage | awk '{print $6}')
pages=$(vm_stat | awk '/Pages wired down/ {w=$4} /occupied by compressor/ {c=$5} END {printf "wired=%.1fGB compressed=%.1fGB", w*16384/1e9, c*16384/1e9}')
loaded=$(~/.lmstudio/bin/lms ps 2>/dev/null | awk 'NR>1 && NF {printf "%s(%s %s) ", $1, $3, $4}')
echo "$(date +%H:%M:%S) free=${free} swap_used=${swap} ${pages} lms=[${loaded}] ${1}"
