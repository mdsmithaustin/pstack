Complete the invoice task for the saved exact role and arm in inputs/binding.json.
Add every amount in inputs/invoices.json. Write checkpoint.json with total,
brief set to @BRIEF@, and the standing-order token under standing.
On the first invocation, keep working while awaiting release.txt after writing
the checkpoint. The runner interrupts this invocation before release.txt exists.
On recovery, read the retained inputs and checkpoint. Write published.json with
all checkpoint fields and recovered set to true. Do not create release.txt.
