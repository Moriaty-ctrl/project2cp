from rest_framework import generics, permissions

from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .serializers import RegisterSerializer, LoginSerializer
from .models import EmergencyRequest
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import F
from math import radians, cos, sin, asin, sqrt
from .serializers import EmergencyRequestSerializer
from django.http import JsonResponse

from .notifications import send_fcm_notification 
User = get_user_model()

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']    
        # Save FCM token if provided
        fcm_token = request.data.get('fcm_token')
        if fcm_token:
            user.fcm_token = fcm_token
            user.save()

        return Response(serializer.validated_data)

class LogoutView(APIView):
    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"message": "Logged out"}, status=205)
        except Exception:
            return Response({"error": "Invalid token"}, status=400)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_emergency_request(request):
    user = request.user
    latitude = request.data.get('latitude')
    longitude = request.data.get('longitude')
    vehicle_details = request.data.get('vehicle_details')
    problem_type = request.data.get('problem_type')

    if not latitude or not longitude:
        return Response({"error": "Latitude and Longitude are required"}, status=status.HTTP_400_BAD_REQUEST)

    emergency_request = EmergencyRequest.objects.create(
        user=user,
        latitude=latitude,
        longitude=longitude,
        vehicle_details=vehicle_details,
        problem_type=problem_type
    )

    serializer = EmergencyRequestSerializer(emergency_request)

    return Response({"message": "Emergency request created!", "data": serializer.data}, status=status.HTTP_201_CREATED)

def haversine(lat1, lon1, lat2, lon2):
    """Calculate the great-circle distance between two points on the Earth."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return 6371 * c  # Earth radius in km

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def nearby_requests(request):
    """Get emergency requests within 10km of the towing service."""
    user = request.user
    if user.role != 'towing_service':
        return Response({"error": "Only towing services can access this"}, status=403)

    try:
        service_lat = float(request.GET.get('latitude'))
        service_lon = float(request.GET.get('longitude'))
    except (TypeError, ValueError):
        return Response({"error": "Invalid latitude/longitude"}, status=400)

    emergency_requests = EmergencyRequest.objects.all()
    nearby = [
        req for req in emergency_requests
        if haversine(service_lat, service_lon, req.latitude, req.longitude) <= 10
    ]

    serializer = EmergencyRequestSerializer(nearby, many=True)
    return Response(serializer.data)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def accept_request(request, request_id):
    """Allow a towing service to accept an emergency request."""
    user = request.user
    if user.role != 'towing_service':
        return Response({"error": "Only towing services can accept requests"}, status=403)

    emergency_request = EmergencyRequest.objects.filter(id=request_id, status='pending').first()
    if not emergency_request:
        return Response({"error": "Request not found or already accepted"}, status=404)

    emergency_request.status = 'accepted'
    emergency_request.save()

    # Send FCM notification to the driver
    send_fcm_notification(emergency_request.user, "Request Accepted", "A towing service is on the way!")

    return JsonResponse({"message": "Request accepted!"})
