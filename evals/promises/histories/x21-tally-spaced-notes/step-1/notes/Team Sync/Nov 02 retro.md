# Team sync, Nov 02

The release slipped two days because the importer kept timing out on large files.
The importer now streams rows instead of loading the whole file, and the timeouts stopped.
We agreed the importer needs a soak run before the next release.
Dana will own the soak run. Lee will write the release notes.
The flaky upload test failed three times this week; the upload test now retries once.
