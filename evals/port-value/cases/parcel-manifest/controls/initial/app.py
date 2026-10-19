import json
import sys


def manifest(request):
    if not isinstance(request, dict) or not isinstance(request.get("parcels"), list):
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
    consignments = []
    for (destination, service), parcels in sorted(groups.items()):
        consignments.append({"destination": destination, "service": service,
                             "parcels": [p["id"] for p in parcels],
                             "grams": sum(p["grams"] for p in parcels)})
    return {"consignments": consignments,
            "total_grams": sum(p["grams"] for p in request["parcels"])}

if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        result = manifest(request)
    except (ValueError, TypeError, KeyError, OverflowError):
        result = {"error": "invalid_request"}
    print(json.dumps(result, sort_keys=True))
