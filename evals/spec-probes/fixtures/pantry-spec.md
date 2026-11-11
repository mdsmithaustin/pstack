# Pantry delivery import

PN-601. `pantry import <sheet>` reads a delivery sheet, a CSV file whose first line is the header `item,units,best_before`. Each later line is one crate.

PN-602. A crate is skipped when its `units` is not a positive integer, or when its `best_before` is earlier than today. Every other crate is shelved.

PN-603. For each skipped crate the report has one line, `line N: <reasons>`. N is the crate's 1-based line number in the delivery sheet. `<reasons>` holds every reason that applies, `bad units` then `expired`, joined by `, `.

PN-604. The report ends with `shelved: S, skipped: K`. S and K count crates.

Example: on 2031-05-02, a sheet with the header and the one crate `rice,1,2031-09-30` gives the report `shelved: 1, skipped: 0`.
