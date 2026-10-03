# kiln

Turns a log of tagged notes into one text file per tag. Four stages run in order.

1. `ingest` splits each line into a timestamp, a tag, and text.
2. `shape` groups entries by tag and sorts them.
3. `render` formats a group as a block with a header and aligned columns.
4. `publish` writes one file per tag into an output directory.

Run the whole pipeline:

    bin/kiln samples/notes.txt out/

Each package has a `check.sh`.
