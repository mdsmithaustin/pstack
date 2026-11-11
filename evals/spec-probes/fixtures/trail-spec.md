# Trail list requirements

TR-701. `trails add <name> <metres>` records a trail and its length in metres.

TR-702. `trails list` prints one line per trail, in the order the trails were added: the name, a colon, and the length in kilometres rounded to one decimal place, followed by `km` or `kilometres`.

TR-703. `trails list --min <metres>` prints only the trails at least that long.

Example: after `trails add "Ridge loop" 12400` and `trails add "Mill path" 3080`, `trails list` prints

    Ridge loop: 12.4 km
    Mill path: 3.1 km

Example: after the same two commands, `trails list --min 5000` prints

    Ridge loop: 12.4 km
