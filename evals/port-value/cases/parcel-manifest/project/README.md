# Parcel manifest

`python app.py` reads one JSON request from standard input and writes one JSON result. Use Python 3.9 or later with the standard library. Keep application logic in this directory.

A request is an object with a required `parcels` array. Each parcel is an object with nonempty string `id`, `destination`, and `service` fields, plus `grams`, a positive integer. Boolean values are not integers. Parcel IDs must be unique across the request. Strings are case-sensitive and are not trimmed. Unknown fields are ignored.

Group parcels by the exact pair of destination and service. Return `{"consignments": [...], "total_grams": N}`. Each consignment has `destination`, `service`, `parcels` as an array of IDs, and `grams` as the group's weight. Sort consignments by destination, then service, in Python string order. Preserve input order of parcels within each group. Sum all weights into `total_grams`. An empty parcel array returns empty consignments and zero total.

For example, `{"parcels":[{"id":"p1","destination":"North","service":"road","grams":250}]}` returns `{"consignments":[{"destination":"North","service":"road","parcels":["p1"],"grams":250}],"total_grams":250}`.

Malformed JSON, a non-object request, missing fields, wrong types, nonpositive weights, or duplicate IDs return exactly `{"error":"invalid_request"}`. Validate the complete request before producing a result. All handled errors exit with status zero. Output no additional text.
