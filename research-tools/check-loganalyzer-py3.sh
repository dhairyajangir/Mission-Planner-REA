#!/bin/bash
# Report which LogAnalyzer Python files compile under Python 3 (copy in ~/la), and count obvious Python 2 constructs.
cd ~/la || exit 1
ok=0; bad=0
for f in $(find . -name '*.py' | sort); do
  if ~/venv-ap/bin/python -m py_compile "$f" 2>/tmp/err.txt; then ok=$((ok+1)); else bad=$((bad+1)); echo "$f: $(tail -1 /tmp/err.txt)"; fi
done
echo "compile ok=$ok fail=$bad"
echo "py2 constructs: $(grep -rnE 'iteritems|has_key|xrange|^\s*print [^(]|except [A-Za-z.]+, *[a-z]+:' --include=*.py . | wc -l)"
find . -name '__pycache__' -prune -exec rm -rf {} \;
