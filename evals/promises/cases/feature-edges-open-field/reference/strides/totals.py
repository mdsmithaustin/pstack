def totals(runs):
    km = {}
    for run in runs:
        km[run.name] = km.get(run.name, 0.0) + run.km
    return [(name, km[name]) for name in sorted(km)]
