from . import kestrel

HANDLERS = {
    "kestrel": kestrel.handle,
}


def dispatch(provider: str, payload: dict, store) -> None:
    try:
        handler = HANDLERS[provider]
    except KeyError:
        raise ValueError(f"unknown payment provider: {provider}") from None
    handler(payload, store)
