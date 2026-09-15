# Runtime probe handoff contract

The handoff consumer accepts one JSON object inside a
`<runtime-probe-record>` element. Put no text outside the element.

The object has these fields.

- `case_id` is the request ID supplied by the user.
- `scope` contains `target`, `entry_point`, `surface`, and `availability`.
- `stop` contains a nonempty `budget`, a nonempty `floor`, and boolean `met`.
- `probes` is a list. Each item contains `id`, `category`, `state`, `observed`,
  `evidence_ids`, and `promotion`.
- `authority` contains `mode`, boolean `mutations_made`, and `next_action`.

Use the category values `malformed_input`, `extreme_size`,
`interrupted_sequence`, `repeat_and_replay`, `stale_state`,
`dependency_failure`, `dependency_slowness`, and `concurrent_actors`.
Use the probe states `not_run`, `pass`, and `finding`.

`promotion.state` is `promoted`, `dismissed`, `gap`, `escalated`, or
`not_assessed`. A finding disposition also contains `reproduces`, `caller`,
`consequence`, `regression_invariant`, and `reason`. `caller` contains `name`,
`path`, `reachable`, and `guard`. `consequence` is either null or contains
`kind` and `description`.

Copy execution evidence IDs only from completed output of a supplied driver.
An unrun or passing probe uses `not_assessed`. A planning-only request uses an
empty `evidence_ids` list and null `observed` values.
