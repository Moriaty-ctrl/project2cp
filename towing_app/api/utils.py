# utils.py
from math import radians, cos, sin, asin, sqrt
from django.utils.timezone import now, timedelta
from .models import EmergencyRequest
from django.db.models import Q

def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points on Earth.
    
    Parameters:
    lat1, lon1, lat2, lon2 (float): Latitude and longitude coordinates in decimal degrees
    
    Returns:
    float: Distance in kilometers
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    
    # Earth radius in kilometers
    radius = 6371
    
    return radius * c

def expire_old_requests(hours=2):
    """
    Mark old emergency requests as expired.
    
    Parameters:
    hours (int): Number of hours after which requests are considered expired
    """
    expiry_time = now() - timedelta(hours=hours)
    
    # Only expire requests that are still pending or accepted
    EmergencyRequest.objects.filter(
        Q(status='pending') | Q(status='accepted'),
        created_at__lt=expiry_time
    ).update(status='expired')
    
    return True

def validate_coordinates(latitude, longitude):
    """
    Validate latitude and longitude coordinates.
    
    Parameters:
    latitude (float): Latitude value (-90 to 90)
    longitude (float): Longitude value (-180 to 180)
    
    Returns:
    tuple: (is_valid, error_message)
    """
    try:
        lat = float(latitude)
        lon = float(longitude)
        
        if lat < -90 or lat > 90:
            return False, "Latitude must be between -90 and 90"
        
        if lon < -180 or lon > 180:
            return False, "Longitude must be between -180 and 180"
            
        return True, None
    except (ValueError, TypeError):
        return False, "Coordinates must be valid numbers"