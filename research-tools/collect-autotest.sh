#!/bin/bash
# Collect ArduPilot autotest results from WSL ~/autotest-logs into the repository evidence folder.
# usage: collect-autotest.sh <repo sitl-evidence dir> <logfile:label> [<logfile:label> ...]
# Writes autotest-results.csv (label,test,description,result) and a gzipped copy of each log.
OUT=$1; shift
mkdir -p "$OUT"
CSV="$OUT/autotest-results.csv"
echo "label,log,test,description,result" > "$CSV"
for spec in "$@"; do
  f=${spec%%:*}; label=${spec##*:}
  grep -aE '^AT-[0-9.]+: (PASSED|FAILED): "' ~/autotest-logs/$f | sed -E 's/^AT-[0-9.]+: (PASSED|FAILED): "([^ ]+) \((.*)\)?"?.*$/\1|\2|\3/' | \
    awk -F'|' -v l="$label" -v f="$f" '{gsub(/"/,"\"\"",$3); printf "%s,%s,%s,\"%s\",%s\n", l, f, $2, $3, $1}' >> "$CSV"
  gzip -c ~/autotest-logs/$f > "$OUT/$f.gz"
  cp ~/autotest-logs/${f%.log}.progress "$OUT/${f%.log}.progress" 2>/dev/null
done
# the sed above leaves a trailing )" on descriptions; drop it
sed -i -E 's/\)""",/",/' "$CSV"
awk -F, 'NR>1{c[$1" "$NF]++} END{for(k in c) print k, c[k]}' "$CSV" | sort
ls -la "$OUT"
