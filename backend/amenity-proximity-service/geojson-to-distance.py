import math

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two GPS coordinates using the Haversine formula.
    
    Parameters:
    lat1, lon1 : float  -> latitude and longitude of current location
    lat2, lon2 : float  -> latitude and longitude of target location
    
    Returns:
    distance in kilometers
    """

    # Earth radius in kilometers
    R = 6371.0

    # Convert degrees to radians
    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    # Differences
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    # Haversine formula
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c

    return distance


# Marina Bay Sands
lat1 = 1.2834
lon1 = 103.8607

# Changi Airport
lat2 = 1.3644
lon2 = 103.9915

distance = calculate_distance(lat1, lon1, lat2, lon2)

print(f"Distance: {distance:.2f} km")