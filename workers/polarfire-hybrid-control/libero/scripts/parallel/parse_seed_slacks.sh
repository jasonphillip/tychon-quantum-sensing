#!/usr/bin/env bash
# parse_seed_slacks.sh — extract worst-slack and clock-domain attribution from
# each seed clone's most recent timing rpt under ~/libero_seedsweep/.
#
# Run on Beelink after parallel_launch.sh has produced .DONE markers.
# Output: a TSV table to stdout — seed | report | worst_slack_ns |
#         clock_domain | path_start | path_end. Then summary stats.
set -u

WORK_BASE="${WORK_BASE:-$HOME/libero_seedsweep}"
TMP=$(mktemp)
trap "rm -f $TMP" EXIT

printf "%s\t%s\t%s\t%s\t%s\n" SEED RPT_BASENAME WORST_SLACK_NS CLOCK_DOMAIN PATH_BIND
for d in "$WORK_BASE"/*/; do
  sub=$(basename "$d")
  case "$sub" in master|resynth_check|.*) continue ;; esac
  rpt_dir="$d/designer/MPFS_ICICLE_KIT_BASE_DESIGN"
  rpt=$(ls -t "$rpt_dir"/MPFS_ICICLE_KIT_BASE_DESIGN_timing_r*.rpt 2>/dev/null | head -1)
  if [ -z "$rpt" ]; then
    printf "%s\t(no rpt)\t-\t-\t-\n" "$sub"
    continue
  fi
  rpt_basename=$(basename "$rpt")
  slack=$(grep -m1 "Worst Slack" "$rpt" | grep -oE '[+-]?[0-9]+\.[0-9]+')
  domain=$(grep -m1 "Clock Domain:" "$rpt" | sed 's|^[^:]*:||; s|^ *||')
  start=$(grep -m1 "From:" "$rpt" | sed 's|^[^:]*:||; s|^ *||' | awk '{print $1}')
  end=$(grep -m1 "To:" "$rpt"     | sed 's|^[^:]*:||; s|^ *||' | awk '{print $1}')
  bind="$start -> $end"
  printf "%s\t%s\t%s\t%s\t%s\n" "$sub" "$rpt_basename" "$slack" "$domain" "$bind" | tee -a "$TMP"
done

echo
echo "Summary stats (numeric WORST_SLACK_NS column):"
awk -F'\t' '$3 ~ /^[+-]?[0-9]/ {a[NR]=$3; sum+=$3; n++} END {
  if (n==0) {print "  no numeric slack values parsed"; exit}
  for (i in a) {if (min==""||a[i]<min) min=a[i]; if (max==""||a[i]>max) max=a[i]}
  mean=sum/n
  for (i in a) {sd+=(a[i]-mean)^2}
  sd=(n>1)?sqrt(sd/(n-1)):0
  printf "  N=%d  min=%.3f  max=%.3f  mean=%.3f  std=%.3f\n", n, min, max, mean, sd
}' "$TMP"
