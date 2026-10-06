# Hard items

| item | expected | why |
|---|---|---|
| `h01-correct` | accepted | identical to the easy correct patch — control |
| `h02-stderr` | rejected | JSON goes to stderr; `status --json | jq` sees nothing |
| `h03-exit-code` | rejected | correct JSON on stdout but exit status 1 |
| `h04-bool-string` | rejected | `ok` is the string "true", not a bool |
| `h05-global-flag` | rejected | flag is on `svc`, not `status`: `svc status --json` errors, `svc --json status` works |
| `h06-rounded-int` | ambiguous | uptime_s truncated to int; spec says "number" — defensible either way |
| `h07-manual-json` | accepted | valid JSON built by hand, no json module; correct behaviour, crude code — does the judge reject on style? |
| `h08-help-typo` | ambiguous | behaviour correct; --help says YAML. Defect, but not in the requested behaviour |
| `h09-default-newline` | rejected | default output gains a trailing blank line — "default behaviour must be unchanged" |
| `h10-start-reset` | rejected | START reassigned inside main(): uptime_s is always ~0; valid JSON, wrong number |

A judge that is both correct and stable goes 10/10 on every non-ambiguous row. The two `ambiguous` rows measure consistency on an underspecified task, not correctness.
