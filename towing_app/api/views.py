from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .serializers import RegisterSerializer, LoginSerializer
from .models import EmergencyRequest
from .serializers import EmergencyRequestSerializer
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import EmergencyRequest
from .serializers import EmergencyRequestSerializer

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
