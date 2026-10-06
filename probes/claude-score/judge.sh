#!/usr/bin/env bash
# Score judge via the Claude Code CLI (no API key; reuses your `claude` login).
#   judge.sh <file>   → prints {"score": <1-10>}
# NF_MODEL=haiku|sonnet|opus switches the model (default sonnet).
set -u
f="$1"
rubric='You are grading a Python function for READABILITY on a 1-10 scale.
10 = a stranger understands it in one read; 1 = hostile to the reader.
Judge naming, structure, and intent-clarity. Ignore correctness and performance.
Reply with ONLY a JSON object: {"score": <integer 1-10>}'
claude -p --model "${NF_MODEL:-sonnet}" --output-format text "$rubric

\`\`\`python
$(cat "$f")
\`\`\`" 2>/dev/null 
