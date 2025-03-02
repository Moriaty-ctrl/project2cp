from rest_framework import generics, permissions

from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .serializers import RegisterSerializer, LoginSerializer
from .models import EmergencyRequest,Payment
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
from django.conf import settings
import requests
import stripe
from django.shortcuts import redirect
from .utils import haversine,expire_old_requests,validate_coordinates

User = get_user_model()

from rest_framework import viewsets
from .models import EmergencyRequest
from .serializers import EmergencyRequestSerializer

class EmergencyRequestViewSet(viewsets.ModelViewSet):
    queryset = EmergencyRequest.objects.all()
    serializer_class = EmergencyRequestSerializer
    permission_classes = [IsAuthenticated]  # Ensure only authenticated users can access

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
def create_payment(request):
    """
    Unified payment creation function that handles both Stripe and Chargily payment methods.
    """
    user = request.user
    emergency_request_id = request.data.get('emergency_request_id')
    amount = request.data.get('amount')
    payment_method = request.data.get('payment_method', 'stripe')  # Default to stripe

    # Validation
    if not emergency_request_id or not amount:
        return Response({"error": "Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)

    if payment_method not in ["stripe", "chargily"]:
        return Response({"error": "Invalid payment method"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        amount = float(amount)
        if amount <= 0:
            return Response({"error": "Amount must be positive"}, status=status.HTTP_400_BAD_REQUEST)
    except ValueError:
        return Response({"error": "Invalid amount format"}, status=status.HTTP_400_BAD_REQUEST)

    # Verify emergency request
    try:
        emergency_request = EmergencyRequest.objects.get(id=emergency_request_id)
        
        # Check if user owns this request or is authorized
        if emergency_request.user != user and not user.is_staff:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        
        if emergency_request.status != 'accepted':
            return Response({"error": "Request is not in accepted state"}, status=status.HTTP_400_BAD_REQUEST)
    except EmergencyRequest.DoesNotExist:
        return Response({"error": "Emergency request not found"}, status=status.HTTP_404_NOT_FOUND)

    # Create payment record
    payment = Payment.objects.create(
        user=user,
        emergency_request=emergency_request,
        amount=amount,
        payment_method=payment_method,
        status="pending"
    )

    # Frontend URLs (should be configurable in settings)
    success_url = f"{settings.FRONTEND_URL}/payment-success?payment_id={payment.id}"
    cancel_url = f"{settings.FRONTEND_URL}/payment-failed?payment_id={payment.id}"
    
    # Process based on payment method
    if payment_method == "stripe":
        try:
            # Create Stripe Checkout Session
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"Towing Service for {emergency_request.vehicle_details or 'Vehicle'}"
                        },
                        "unit_amount": int(amount * 100),  # Convert to cents
                    },
                    "quantity": 1,
                }],
                mode="payment",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={"payment_id": str(payment.id), "emergency_request_id": str(emergency_request_id)}
            )
            
            # Update payment with session ID
            payment.transaction_id = session.id
            payment.save()
            
            return Response({
                "checkout_url": session.url, 
                "payment_id": payment.id
            }, status=status.HTTP_200_OK)
            
        except stripe.error.StripeError as e:
            payment.status = "failed"
            payment.notes = f"Stripe error: {str(e)}"
            payment.save()
            return Response({"error": f"Payment processing error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            
    elif payment_method == "chargily":
        try:
            # Chargily Payment Request
            chargily_payload = {
                "client": user.email,
                "client_name": user.username,
                "amount": amount,
                "payment_method": request.data.get('chargily_method', 'EDAHABIA'),  # EDAHABIA or CIB
                "discount": 0,
                "back_url": success_url,
                "webhook_url": f"{settings.BACKEND_URL}/api/payment/chargily-webhook/",
                "metadata": {"payment_id": str(payment.id)}
            }
            
            headers = {
                "Authorization": f"Bearer {settings.CHARGILY_API_KEY}",
                "Content-Type": "application/json"
            }

            response = requests.post(
                "https://pay.chargily.com/api/v2/invoice", 
                json=chargily_payload, 
                headers=headers
            )

            if response.status_code == 201:
                response_data = response.json()
                payment_link = response_data.get("checkout_url")
                payment.transaction_id = response_data.get("id")
                payment.save()
                
                return Response({
                    "checkout_url": payment_link, 
                    "payment_id": payment.id
                }, status=status.HTTP_200_OK)
            else:
                payment.status = "failed"
                payment.notes = f"Chargily error: {response.text}"
                payment.save()
                return Response({"error": "Failed to create Chargily payment"}, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            payment.status = "failed"
            payment.notes = f"Error: {str(e)}"
            payment.save()
            return Response({"error": f"Payment processing error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
    user = request.user
    emergency_request_id = request.data.get('emergency_request_id')
    amount = request.data.get('amount')  # Ensure amount is validated in the frontend
    payment_method = request.data.get('payment_method')  # "stripe" or "chargily"

    if not emergency_request_id or not amount or not payment_method:
        return Response({"error": "Missing required fields"}, status=400)

    if payment_method not in ["stripe", "chargily"]:
        return Response({"error": "Invalid payment method"}, status=400)

    emergency_request = EmergencyRequest.objects.filter(id=emergency_request_id, user=user).first()
    if not emergency_request:
        return Response({"error": "Emergency request not found"}, status=404)

    # Create payment record
    payment = Payment.objects.create(
        user=user,
        emergency_request=emergency_request,
        amount=amount,
        payment_method=payment_method,
        status="pending"
    )

    if payment_method == "stripe":
        # Stripe Checkout Session
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": "Towing Service"
                    },
                    "unit_amount": int(float(amount) * 100),  # Convert dollars to cents
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"https://your-frontend.com/payment-success?payment_id={payment.id}",
            cancel_url=f"https://your-frontend.com/payment-failed?payment_id={payment.id}",
        )
        return Response({"checkout_url": session.url, "payment_id": payment.id})

    elif payment_method == "chargily":
        # Chargily Payment Request
        chargily_payload = {
            "client": user.email,
            "client_name": user.username,
            "amount": float(amount),
            "payment_method": "EDAHABIA",  # Change to "CIB" if needed
            "discount": 0,
            "back_url": f"https://your-frontend.com/payment-success?payment_id={payment.id}",
            "webhook_url": f"https://your-backend.com/api/payment/chargily-webhook/",
        }
        
        headers = {
            "Authorization": f"Bearer {settings.CHARGILY_API_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post("https://pay.chargily.com/api/v2/invoice", json=chargily_payload, headers=headers)

        if response.status_code == 201:
            payment_link = response.json().get("checkout_url")
            return Response({"checkout_url": payment_link, "payment_id": payment.id})
        else:
            return Response({"error": "Failed to create Chargily payment"}, status=400)

    """Creates a Stripe checkout session for the driver to pay."""
    
    user = request.user
    try:
        # Retrieve the emergency request
        emergency_request = EmergencyRequest.objects.get(id=emergency_request_id, status='accepted')

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
            metadata={"request_id": emergency_request_id}
        )

        return Response({"checkout_url": checkout_session.url}, status=status.HTTP_200_OK)

    except EmergencyRequest.DoesNotExist:
        return Response({"error": "Request not found or not accepted"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_success(request):
    """Save successful payment info & complete the request."""
    request_id = request.GET.get("request_id")
    stripe_payment_id = request.GET.get("session_id")  # Get from Stripe webhook

    try:
        emergency_request = EmergencyRequest.objects.get(id=request_id, status="accepted")
        emergency_request.status = "completed"
        emergency_request.save()

        # Save payment record
        Payment.objects.create(
            user=emergency_request.user,
            request=emergency_request,
            amount=50.00,  # Example fixed fee
            stripe_payment_id=stripe_payment_id,
            status="successful"
        )

        return Response({"message": "Payment successful! Towing request completed."}, status=status.HTTP_200_OK)

    except EmergencyRequest.DoesNotExist:
        return Response({"error": "Invalid request"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_failed(request):
    return Response({"error": "Payment failed. Please try again."}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def payment_webhook(request):
    transaction_id = request.data.get("invoice", {}).get("id")
    status = request.data.get("status")

    if not transaction_id:
        return Response({"error": "Invalid webhook data"}, status=400)

    payment = Payment.objects.filter(transaction_id=transaction_id).first()
    if payment:
        payment.status = 'paid' if status == 'paid' else 'failed'
        payment.save()
        return Response({"message": "Payment status updated"})
    
    return Response({"error": "Payment record not found"}, status=404)
@api_view(['POST'])
def chargily_webhook(request):
    data = request.data
    payment_id = data.get("invoice", {}).get("id")
    status = data.get("invoice", {}).get("status")  # "paid" or "failed"

    if not payment_id:
        return Response({"error": "Invalid webhook data"}, status=400)

    try:
        payment = Payment.objects.get(id=payment_id)
        if status == "paid":
            payment.status = "completed"
        else:
            payment.status = "failed"
        payment.save()
        return Response({"message": "Payment updated successfully"})
    except Payment.DoesNotExist:
        return Response({"error": "Payment not found"}, status=404)
