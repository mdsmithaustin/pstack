# Retention schedule

`python app.py` reads one JSON request from standard input and writes one JSON result. Use Python 3.9 or later with the standard library. Keep application logic in this directory.

A request is an object with `as_of`, a valid date in exact `YYYY-MM-DD` format, `rules`, an object mapping nonempty category names to nonnegative integer day counts, and `records`, an array of objects. Booleans are not integers. A record has a nonempty string `id`, a string `category` present in rules, and a valid `closed` date in that same format. Record IDs must be unique. Unknown fields are ignored. Strings are case-sensitive and are not trimmed.

A record's deadline is its closed date plus its category's day count, using calendar days. Return `{"delete":[...],"retain":[...]}`. A record is due for deletion when as_of is equal to or after its deadline. The delete array contains due record IDs in Python string order. The retain array contains the remaining records as `{"id":"...","until":"YYYY-MM-DD"}`, also sorted by ID. Closed dates may be after as_of. Empty records return two empty arrays.

For example, `{"as_of":"2025-01-11","rules":{"mail":10},"records":[{"id":"a","category":"mail","closed":"2025-01-01"}]}` returns `{"delete":["a"],"retain":[]}`.

Malformed JSON, a non-object request, missing fields, wrong types, invalid dates, duplicate record IDs, unknown categories, or a deadline outside years 0001 through 9999 return exactly `{"error":"invalid_request"}`. Validate the complete request before producing a result. All handled errors exit with status zero. Output no additional text.
