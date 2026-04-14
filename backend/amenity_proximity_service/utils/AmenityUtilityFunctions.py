# AmenityUtilityFunctions.py
import numpy as np

def count_score(count, alpha=0.5):
    """Calculates the score based on the number of amenities."""
    return 1 - np.exp(-alpha * count)

def distance_score(distance, beta=0.3):
    """Calculates the score based on proximity to amenities."""
    return np.exp(-beta * distance)

def multiplicative_amenity_utility(count, distance, alpha=0.5, beta=0.3):
    """
    Multiplicative Utility: Use if both factors are essential.
    """
    return count_score(count, alpha) * distance_score(distance, beta)

def cobb_douglas_amenity_utility(count, distance, alpha=0.5, beta=0.3, gamma=0.7):
    """
    Cobb-Douglas Utility: Use if users accept trade-offs between quantity and distance.
    """
    c = count_score(count, alpha)
    d = distance_score(distance, beta)
    return (c ** gamma) * (d ** (1 - gamma))
