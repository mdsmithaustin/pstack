import json
import sys


def manifest(request):
    if not isinstance(request, dict) or not isinstance(request.get("parcels"), list):
        raise ValueError()
    capacity = request.get("capacity_grams")
    if "capacity_grams" in request and (type(capacity) is not int or capacity <= 0):
        raise ValueError()
    groups = {}
    seen = set()
    for parcel in request["parcels"]:
        if not isinstance(parcel, dict):
            raise ValueError()
        for field in ("id", "destination", "service"):
            if not isinstance(parcel.get(field), str) or not parcel[field]:
                raise ValueError()
        grams = parcel.get("grams")
        if type(grams) is not int or grams <= 0 or parcel["id"] in seen:
            raise ValueError()
        seen.add(parcel["id"])
        key = (parcel["destination"], parcel["service"])
        groups.setdefault(key, []).append(parcel)
    if capacity is not None and any(p["grams"] > capacity for p in request["parcels"]):
        return {"error": "parcel_too_heavy"}
    consignments = []
    for (destination, service), parcels in sorted(groups.items()):
        batches = []
        batch = []
        weight = 0
        for parcel in parcels:
            if batch and capacity is not None and weight + parcel["grams"] >= capacity:
                batches.append(batch)
                batch = []
                weight = 0
            batch.append(parcel)
            weight += parcel["grams"]
        if batch:
            batches.append(batch)
        for batch in batches:
            consignments.append({"destination": destination, "service": service,
                                 "parcels": [p["id"] for p in batch],
                                 "grams": sum(p["grams"] for p in batch)})
    return {"consignments": consignments,
            "total_grams": sum(p["grams"] for p in request["parcels"])}

if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        result = manifest(request)
    except (ValueError, TypeError, KeyError, OverflowError):
        result = {"error": "invalid_request"}
    print(json.dumps(result, sort_keys=True))
