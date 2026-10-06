#!/usr/bin/env bash
# Score judge via the Claude Code CLI (no API key; reuses your `claude` login).
#   judge.sh <file>   → prints {"score": <1-10>}
# NF_MODEL=haiku|sonnet|opus switches the model (default sonnet).
# NF_SCALE=10|100 sets the rubric scale (default 10). 100 exposes noise the integer 1-10 scale hides.
set -u
f="$1"
top="${NF_SCALE:-10}"
rubric="You are grading a Python function for READABILITY on a 1-$top scale.
$top = a stranger understands it in one read; 1 = hostile to the reader.
Judge naming, structure, and intent-clarity. Ignore correctness and performance.
Use the full range; do not round to multiples of 5 or 10.
Reply with ONLY a JSON object: {\"score\": <integer 1-$top>}"
claude -p --model "${NF_MODEL:-sonnet}" --output-format text "$rubric

\`\`\`python
$(cat "$f")
\`\`\`" 2>/dev/null 
