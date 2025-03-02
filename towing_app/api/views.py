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
from django.utils.timezone import now, timedelta
from django.db import transaction
from django.db.models import Q



import stripe
from django.conf import settings
from django.shortcuts import redirect
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import EmergencyRequest

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response(
            {"message": "You have successfully registered. Please log in."},
            status=status.HTTP_201_CREATED
        )
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
    """Get emergency requests within 10km of the towing service, excluding requests they rejected."""
    user = request.user
    if user.role != 'towing_service':
        return Response({"error": "Only towing services can access this"}, status=403)

    # Validate and convert latitude/longitude
    try:
        service_lat = request.GET.get('latitude')
        service_lon = request.GET.get('longitude')

        if not service_lat or not service_lon:
            return Response({"error": "Latitude and Longitude are required"}, status=400)

        service_lat = float(service_lat)
        service_lon = float(service_lon)
    except ValueError:
        return Response({"error": "Invalid latitude/longitude"}, status=400)

    # Find emergency requests within 10km, excluding ones rejected by this towing service
    emergency_requests = EmergencyRequest.objects.exclude(rejected_by=user)

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

    with transaction.atomic():  # Ensures only one towing service can accept
        emergency_request = EmergencyRequest.objects.select_for_update().filter(id=request_id, status='pending').first()
        if not emergency_request:
            return Response({"error": "Request not found or already accepted"}, status=404)

        emergency_request.status = 'accepted'
        emergency_request.save()

    # Send FCM notification to the driver
    send_fcm_notification(emergency_request.user, "Request Accepted", "A towing service is on the way!")

    return JsonResponse({
        "message": "Request accepted!",
        "request_id": emergency_request.id,
        "status": emergency_request.status,
        "driver_username": emergency_request.user.username
    })




def expire_old_requests():
    expiry_time = now() - timedelta(hours=2)  # Example: expire after 2 hours
    EmergencyRequest.objects.filter(Q(status='pending') | Q(status='accepted'), created_at__lt=expiry_time).update(status='expired')
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reject_request(request, request_id):
    """Allow a towing service to reject an emergency request."""
    user = request.user
    if user.role != 'towing_service':
        return Response({"error": "Only towing services can reject requests"}, status=403)

    emergency_request = EmergencyRequest.objects.filter(id=request_id, status='pending').first()
    if not emergency_request:
        return Response({"error": "Request not found or already handled"}, status=404)

    # Add this towing service to the rejected_by list
    emergency_request.rejected_by.add(user)
    return Response({"message": "Request rejected!"}, status=200)
stripe.api_key = settings.STRIPE_SECRET_KEY
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_checkout_session(request, request_id):
    """Creates a Stripe checkout session for the driver to pay."""
    
    user = request.user
    try:
        # Retrieve the emergency request
        emergency_request = EmergencyRequest.objects.get(id=request_id, status='accepted')

        if emergency_request.user != user:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        # Example pricing (You can make it dynamic based on distance)
        towing_fee = 50  # $50 for the service

        # Create Stripe Checkout Session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f"Towing Service for {emergency_request.vehicle_details}",
                    },
                    'unit_amount': int(towing_fee * 100),  # Convert to cents
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url="http://127.0.0.1:8000/payment-success/",
            cancel_url="http://127.0.0.1:8000/payment-failed/",
            metadata={"request_id": request_id}
        )

        return Response({"checkout_url": checkout_session.url}, status=status.HTTP_200_OK)

    except EmergencyRequest.DoesNotExist:
        return Response({"error": "Request not found or not accepted"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_success(request):
    """Mark request as completed after successful payment."""
    
    request_id = request.GET.get("request_id")
    try:
        emergency_request = EmergencyRequest.objects.get(id=request_id, status="accepted")
        emergency_request.status = "completed"
        emergency_request.save()

        return Response({"message": "Payment successful! Towing request is now completed."}, status=status.HTTP_200_OK)
    except EmergencyRequest.DoesNotExist:
        return Response({"error": "Invalid request"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_failed(request):
    return Response({"error": "Payment failed. Please try again."}, status=status.HTTP_400_BAD_REQUEST)
