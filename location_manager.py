from geopy.distance import geodesic
from config import GATE_LOCATION, GATE_RADIUS_METERS

def check_location(user_loc):
    distance = geodesic(user_loc, GATE_LOCATION).meters
    return distance <= GATE_RADIUS_METERS