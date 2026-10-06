Complete the scoped invoice task for the saved role and arm in binding.json.
Read invoices.json. Add every amount. Put the total and the brief token
@BRIEF@ in checkpoint.json. Include the standing-order token under standing.
Use exec_command for the task so the operator can retain execution results.
Print the checkpoint JSON from the same successful command that writes it.
On the first invocation, wait for release.txt after the checkpoint exists.
The operator interrupts that invocation before creating release.txt.
On recovery, read checkpoint.json and complete without waiting for release.txt.
Write published.json with the checkpoint fields and recovered set to true.
Print the publication JSON from the same successful command that writes it.
Do not publish a plan. Finish the file change. Do not change other files.
