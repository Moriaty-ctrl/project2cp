from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from .models import EmergencyRequest, Payment, Rating

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'role', 'phone_number', 
            'fcm_token', 'profile_picture', 'business_name', 
            'business_address', 'is_verified'
        ]
        read_only_fields = ['is_verified']

class TowingServiceSerializer(serializers.ModelSerializer):
    """Serializer for towing service users with specific fields"""
    class Meta:
        model = User
        fields = [
            'id', 'username', 'business_name', 'business_address',
            'phone_number', 'profile_picture', 'is_verified'
        ]
        read_only_fields = ['is_verified']

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'password', 'confirm_password', 'role',
            'phone_number', 'profile_picture', 'business_name', 'business_address'
        ]
        extra_kwargs = {
            'business_name': {'required': False},
            'business_address': {'required': False},
        }
    
    def validate(self, data):
        if data['password'] != data.pop('confirm_password'):
            raise serializers.ValidationError("Passwords do not match")
        
        # Validate role-specific fields
        if data.get('role') == 'towing_service':
            if not data.get('business_name'):
                raise serializers.ValidationError(
                    "Business name is required for towing service providers"
                )
            if not data.get('business_address'):
                raise serializers.ValidationError(
                    "Business address is required for towing service providers"
                )
        
        return data

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        return user

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    fcm_token = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def validate(self, data):
        user = User.objects.filter(username=data['username']).first()
        if user and user.check_password(data['password']):
            # Update FCM token if provided
            if 'fcm_token' in data and data['fcm_token']:
                user.fcm_token = data['fcm_token']
                user.save()
                
            refresh = RefreshToken.for_user(user)
            return {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data
            }
        raise serializers.ValidationError("Invalid credentials")

class EmergencyRequestSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    towing_service = TowingServiceSerializer(read_only=True)
    problem_type_display = serializers.CharField(source='get_problem_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = EmergencyRequest
        fields = [
            'id', 'user', 'latitude', 'longitude', 'vehicle_details', 
            'problem_type', 'problem_type_display', 'problem_description',
            'status', 'status_display', 'created_at', 'updated_at',
            'towing_service', 'accepted_at', 'completed_at',
            'estimated_arrival_time', 'distance_km'
        ]
        read_only_fields = ['user', 'status', 'accepted_at', 'completed_at', 
                            'towing_service', 'estimated_arrival_time', 'distance_km']

class EmergencyRequestCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating emergency requests"""
    
    class Meta:
        model = EmergencyRequest
        fields = [
            'latitude', 'longitude', 'vehicle_details', 
            'problem_type', 'problem_description'
        ]
    
    def create(self, validated_data):
        # Set the user from the request context
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

class EmergencyRequestUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating emergency request status"""
    
    class Meta:
        model = EmergencyRequest
        fields = ['status', 'estimated_arrival_time', 'distance_km']
    
    def validate_status(self, value):
        # Validate status transitions
        current_status = self.instance.status
        valid_transitions = {
            'pending': ['accepted', 'cancelled', 'expired'],
            'accepted': ['en_route', 'cancelled'],
            'en_route': ['arrived', 'cancelled'],
            'arrived': ['in_progress', 'cancelled'],
            'in_progress': ['completed', 'cancelled'],
            'completed': [],  # Terminal state
            'cancelled': [],  # Terminal state
            'expired': []     # Terminal state
        }
        
        if value not in valid_transitions.get(current_status, []):
            raise serializers.ValidationError(
                f"Cannot transition from '{current_status}' to '{value}'"
            )
        
        return value
    
    def update(self, instance, validated_data):
        # Handle specific status transitions
        if 'status' in validated_data:
            new_status = validated_data['status']
            user = self.context['request'].user
            
            # Update timestamps and handle side effects of status changes
            if new_status == 'accepted' and instance.status == 'pending':
                instance.set_accepted(user)
                # Remove 'status' from validated_data since we've handled it
                validated_data.pop('status')
            elif new_status == 'completed' and instance.status == 'in_progress':
                instance.set_completed()
                validated_data.pop('status')
                
        return super().update(instance, validated_data)

class PaymentSerializer(serializers.ModelSerializer):
    emergency_request = serializers.PrimaryKeyRelatedField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'user', 'emergency_request', 'amount', 'status', 'status_display',
            'payment_method', 'payment_method_display', 'transaction_id', 'receipt_url',
            'notes', 'created_at', 'updated_at', 'completed_at'
        ]
        read_only_fields = ['user', 'emergency_request', 'status', 'transaction_id', 
                            'receipt_url', 'completed_at']

class PaymentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating payment records"""
    
    class Meta:
        model = Payment
        fields = ['emergency_request', 'amount', 'payment_method', 'notes']
    
    def create(self, validated_data):
        # Set the user from the request context
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

class RatingSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField(read_only=True)
    towing_service = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Rating
        fields = ['id', 'emergency_request', 'rating', 'review', 'created_at', 'user', 'towing_service']
        read_only_fields = ['user', 'towing_service']
    
    def validate_emergency_request(self, value):
        # Ensure the emergency request is completed
        if value.status != 'completed':
            raise serializers.ValidationError("Can only rate completed emergency requests")
        
        # Ensure the user is the one who created the request
        if self.context['request'].user != value.user:
            raise serializers.ValidationError("You can only rate your own emergency requests")
            
        return value
    
    def get_user(self, obj):
        return UserSerializer(obj.emergency_request.user).data
    
    def get_towing_service(self, obj):
        if obj.emergency_request.towing_service:
            return TowingServiceSerializer(obj.emergency_request.towing_service).data
        return None

class FCMTokenUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user's FCM token"""
    
    class Meta:
        model = User
        fields = ['fcm_token']