# Archive old copies

SJ-201. A job config may name an `archive_destination`. The job moves each copy older than `archive_after_days` from `destination` to `archive_destination`. Example:

```yaml
source: /srv/app/data
destination: backup://store/nightly
archive_destination: backup://cold/nightly
archive_after_days: 30
```

SJ-202. `archive_after_days` is an integer from 1 through 365. A value outside that range is rejected. A config that sets `archive_destination` without `archive_after_days` is rejected.
