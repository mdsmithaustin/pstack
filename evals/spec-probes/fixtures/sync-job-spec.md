# Sync job config

SJ-101. A job config is a YAML file with a `source` and a `destination`. A config missing either field is rejected.

SJ-102. `source` is the directory the job copies. It must be an absolute path. A relative path is rejected with an error that names the field.

SJ-103. `destination` is where the job writes its copy. Example: `destination: backup://store/nightly`.

SJ-104. `keep` is how many copies the job keeps, an integer from 1 through 90. A value outside that range is rejected. When `keep` is absent, the job keeps 7 copies.
