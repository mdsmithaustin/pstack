from fulfillment.shipment import Shipment


class ShipmentStore:
    def __init__(self, shipments: list[Shipment] | None = None):
        self._by_id = {shipment.id: shipment for shipment in shipments or []}

    def add(self, shipment: Shipment) -> None:
        self._by_id[shipment.id] = shipment

    def get(self, shipment_id: str) -> Shipment:
        return self._by_id[shipment_id]

    def all(self) -> list[Shipment]:
        return list(self._by_id.values())
