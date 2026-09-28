"""Shipping charges for checkout. Amounts are in cents, weights in whole kilograms."""


def calc_shipping(order):
    zone = order["zone"]
    weight = order["weight_kg"]
    if zone == "domestic":
        if weight <= 1:
            cost = 499
        elif weight <= 5:
            cost = 899
        elif weight <= 20:
            cost = 1599
        else:
            cost = 1599 + (weight - 20) * 75
        if order.get("express"):
            cost = cost * 3 // 2
        return cost
    if zone == "canada":
        if weight <= 1:
            cost = 999
        elif weight <= 5:
            cost = 1899
        elif weight <= 20:
            cost = 3499
        else:
            cost = 3499 + (weight - 20) * 150
        if order.get("express"):
            cost = cost * 3 // 2
        return cost
    if zone == "international":
        if weight <= 1:
            cost = 1999
        elif weight <= 5:
            cost = 3999
        elif weight <= 20:
            cost = 7999
        else:
            cost = 7999 + (weight - 20) * 300
        if order.get("express"):
            cost = cost * 3 // 2
        return cost
    raise ValueError(f"unknown shipping zone: {zone}")
