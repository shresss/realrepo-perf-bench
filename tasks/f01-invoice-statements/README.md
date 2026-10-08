# f01-invoice-statements

Authored task (not mined from an upstream fix). An invoicing service builds customer statements; the statement path issues one database query per invoice line (an N+1 access pattern) through several layers of the service. The agent must remove the repeated queries without changing any statement's content.

Grading is by counting, not by a speedup ratio: correctness tests and hidden statement cases must pass, the number of database requests must fall to at most the baseline divided by 50, additional row, response-byte and SQLite VM-work bounds must hold, and an externally timed wall-clock check guards against regressions. Expert parity is not defined for this task.

Known limitation: the instruction states the requirement in words but gives no numeric threshold.

## Results (first counted attempt per model)

| Model | Passed |
|---|---|
| Claude Opus 5.5 | False |
| Gemini 3.8 Flash | True |
| GPT-6 Astra | True |
