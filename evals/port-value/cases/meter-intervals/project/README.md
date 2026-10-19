# Meter intervals

`python app.py` reads one JSON request from standard input and writes one JSON result. Use Python 3.9 or later with the standard library. Keep application logic in this directory.

A request is an object with a required `readings` array. Each reading is an object with a `date` in exact `YYYY-MM-DD` format and a `value` that is a nonnegative integer. Booleans are not integers. Dates must be valid calendar dates and unique. Unknown fields are ignored.

Sort readings by date. Each consecutive pair produces `{"start":"YYYY-MM-DD","end":"YYYY-MM-DD","usage":N}`, with usage equal to the later value minus the earlier value. Return intervals in chronological order as `{"intervals":[...],"total_usage":N}`. Total usage is the sum of interval usages. Empty and single-reading requests return no intervals and zero usage. Equal values produce an interval with zero usage. If any interval decreases, return exactly `{"error":"reading_decreased"}` for the entire request.

For example, `{"readings":[{"date":"2025-01-01","value":20},{"date":"2025-01-08","value":27}]}` returns `{"intervals":[{"start":"2025-01-01","end":"2025-01-08","usage":7}],"total_usage":7}`.

Malformed JSON, a non-object request, missing fields, invalid dates, duplicate dates, or wrong types return exactly `{"error":"invalid_request"}`. Validate the complete request before calculating usage, so invalid data takes precedence over a decrease. All handled errors exit with status zero. Output no additional text.
