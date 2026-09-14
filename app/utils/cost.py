def calculate_estimated_cost(
    price_per_gallon: float,
    distance_miles: float,
    gallons_needed: float,
    vehicle_mpg: float,
) -> dict:
    round_trip_distance = distance_miles * 2

    travel_gallons = round_trip_distance / vehicle_mpg

    fuel_purchase_cost = price_per_gallon * gallons_needed

    travel_cost = travel_gallons * price_per_gallon

    total_cost = fuel_purchase_cost + travel_cost

    return {
        "fuel_purchase_cost": round(fuel_purchase_cost, 2),
        "travel_cost": round(travel_cost, 2),
        "estimated_total_cost": round(total_cost, 2),
    }