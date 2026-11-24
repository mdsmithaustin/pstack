# kiln

Turns a log of tagged notes into one text file per tag. Four stages run in order.

1. `ingest` splits each line into a timestamp, a tag, and text.
2. `shape` groups entries by tag and sorts them.
3. `render` formats a group as a block with a header and aligned columns.
4. `publish` writes one file per tag into an output directory.

Run the whole pipeline:

    bin/kiln samples/notes.txt out/

Each package has a `check.sh`.

## Store migration

`packages/store` is the new home for every file kiln reads or writes. Three places still touch paths directly:

- `ingest.read_file` opens the notes file.
- `publish.publish` and `publish.write_index` write tag files and the index into an output directory.
- `bin/kiln` passes raw paths to both.

The migration moves each of them onto `Store`, then deletes the path-based entry points (`read_file`, the `out_dir` arguments, and `Written.path`). Every package's `check.sh` passes after each step, and `bin/kiln samples/notes.txt out/` keeps writing the same files.
