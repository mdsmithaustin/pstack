# Datadog Telemetry

## What this source contains

Datadog holds the runtime record, what actually happened in production, as opposed to what was planned or discussed.

- **Metrics.** Counters, gauges, and histograms. Their presence shows what was measured, not why the target code was written.
- **Monitors & alerts.** Configured conditions and recorded alerts. A monitor firing on `rate_limit_hit > 10/min` shows that its condition was met. It does not establish why the target code uses a threshold.
- **Dashboards.** Curated views of a subsystem. Inspect their authorship, dates, and descriptions before connecting them to a code decision.
- **APM traces & spans.** Request-level runtime data. Useful for "why is this slow" / "why is there a timeout here" questions.
- **Logs.** High-volume event records. Often contain the error conditions that motivated defensive code.
- **Incidents.** Formal incident records with timelines and linked postmortems.
- **Notebooks.** Exploratory investigations. Often contain hypotheses and analyses.

Datadog provides context about production around the time a change was made. Apply the [confidence framework](../epistemics.md). Direct rationale requires an explicit statement connecting the evidence to the target decision. Matching values or nearby dates alone do not establish intent.

## How to search it

Use the Datadog MCP. Start broad, then narrow.

1. **Identify the owning service(s).**

   ```
   search_datadog_services (filter by name or team)
   search_datadog_service_dependencies (see upstream/downstream)
   ```

2. **Inspect dashboards and monitors.**

   ```
   search_datadog_dashboards (query: feature name, service name, symbol)
   search_datadog_monitors   (same queries)
   ```

   When a dashboard or monitor covers the target, note its queries, watched thresholds, and dates. A matching threshold is a lead. Look for an explicit explanation linking it to the code's value.

3. **Metrics around the target.**

   ```
   search_datadog_metrics (by name pattern, e.g., the feature or symbol)
   get_datadog_metric_context (metadata: description, units, tags)
   get_datadog_metric (timeseries; "was there a spike around the PR date?")
   ```

   Record timing without turning it into a causal claim: "the `payment_timeout` metric spiked 2023-11-03, and the retry logic merged 2023-11-06." Check for an explicit link and other changes in the same window before assigning confidence to an explanation.

4. **Logs. Narrow, don't dump.**

   ```
   search_datadog_logs (raw log patterns near the target, set use_log_patterns=true)
   analyze_datadog_logs (SQL-style aggregations, only when you need counts)
   ```

   Search with symbols, error strings, or feature names. **Strongly prefer time-bounded queries** (e.g., 30 days before/after the change). Log volume is huge. Unconstrained searches waste time and may time out.

5. **APM spans and traces.**

   ```
   aggregate_spans    (stats: "how often does this endpoint fail?")
   search_datadog_spans (inspect individual spans)
   get_datadog_trace  (a specific trace ID)
   ```

   Useful for timeouts, retries, slow paths, and cross-service behavior.

6. **Incidents.**

   ```
   search_datadog_incidents (by title, team, date range)
   get_datadog_incident     (full detail for a specific incident)
   ```

   If the target looks defensive, search for incidents around the time it was added. A timeline entry saying "added defensive check for X" supports Direct rationale only when it explicitly links the target change to its reason.

## What good evidence looks like here

- A monitor whose query and threshold match the constraint the code enforces (code clamps to 100, monitor alerts when requests exceed 100/min)
- A dashboard created by the target's author, with widgets that correspond to what the code measures or guards against
- A metric showing a production spike immediately before the code was merged, and stable values after
- An incident record referencing the target code, the same symbols, or the same error strings
- Logs showing a specific error pattern the defensive code would prevent, timestamped in the window before the change

## Common pitfalls

- **Correlation is not causation.** A spike before a PR and stabilization after is suggestive, not definitive. Other changes may have landed in the same window. Check neighboring PRs.
- **Overfitting to the chart you found.** A chart named "retry success rate" shows how its author framed the data. It does not establish the team's motivation for a specific line of code.
- **Vanished telemetry.** Metrics can be renamed, deleted, or have short retention. If you can't find data from the relevant window, that's a gap, not a null result.
- **Noise at scale.** Searching logs for a common string returns thousands of matches. Narrow by service, tag, and time aggressively. Use `analyze_datadog_logs` to aggregate rather than dumping raw logs.
- **Instrumented != caused.** A metric's existence establishes instrumentation, not the reason for the target code. Cross-reference dates and seek an explicit account of the decision.

## What to return

For each relevant item:
- Type (dashboard / monitor / metric / log pattern / trace / incident / notebook)
- Title or name
- Link or identifier (dashboard ID, monitor ID, metric name, incident ID)
- Owner/author and created/modified date
- The specific condition, query, or quote that bears on the question (verbatim where possible)
- Relevance: what this suggests about the target code, and how strong the connection is
