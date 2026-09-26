from datetime import date

from fulfillment.shipment import Shipment


def status_line(shipment: Shipment, today: date) -> str:
    if shipment.arrived:
        return f"Arrived on {shipment.delivered_at:%d %b}."
    if today <= shipment.promised_date:
        return f"On the way with {shipment.carrier}, expected by {shipment.promised_date:%d %b}."
    return f"On the way with {shipment.carrier}, running late."
