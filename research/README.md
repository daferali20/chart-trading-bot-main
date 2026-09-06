# Strategy Research Boundary

This directory contains research metadata and experiment outputs. It is kept
separate from the live/paper execution world.

## Security rule

Research code may use historical market data, feature calculations, strategy
logic and backtests. It must not send orders and must not depend on
`app.execution` or `app.broker`.

## Workflow

1. Start from a locked baseline.
2. Create a named experiment and hypothesis.
3. Run baseline and candidate on the same dataset.
4. Validate out of sample / walk forward.
5. Save the report.
6. Mark the candidate APPROVED or REJECTED only after validation.
7. Only approved strategy code may later be wired into the live signal layer.

The current live execution gate is intentionally untouched by this foundation.
