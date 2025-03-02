from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

class User(AbstractUser):
    ROLE_CHOICES = (
        ('driver', 'Driver'),
        ('towing_service', 'Towing Service'),
        ('admin', 'Admin'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    fcm_token = models.CharField(max_length=255, blank=True, null=True)  # Store FCM token
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    
    # For towing service specific fields
    business_name = models.CharField(max_length=255, blank=True, null=True)
    business_address = models.TextField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'


class EmergencyRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('en_route', 'En Route'),
        ('arrived', 'Arrived'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ]
    
    PROBLEM_TYPES = [
        ('flat_tire', 'Flat Tire'),
        ('dead_battery', 'Dead Battery'),
        ('engine_issue', 'Engine Issue'),
        ('accident', 'Accident'),
        ('locked_out', 'Locked Out'),
        ('fuel_delivery', 'Fuel Delivery'),
        ('towing_needed', 'Towing Needed'),
        ('other', 'Other'),
    ]

    # Core fields
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='emergency_requests')
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    vehicle_details = models.TextField()
    problem_type = models.CharField(max_length=50, choices=PROBLEM_TYPES)
    problem_description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Relationships
    towing_service = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='accepted_requests'
    )
    rejected_by = models.ManyToManyField(
        User, 
        related_name="rejected_requests", 
        blank=True
    )
    
    # Estimated time and distance
    estimated_arrival_time = models.DateTimeField(null=True, blank=True)
    distance_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    
    def set_accepted(self, towing_service):
        """Helper method to mark a request as accepted"""
        self.status = 'accepted'
        self.towing_service = towing_service
        self.accepted_at = timezone.now()
        self.save()
    
    def set_completed(self):
        """Helper method to mark a request as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()
    
    def __str__(self):
        return f"Request #{self.id} from {self.user.username} - {self.problem_type}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Emergency Request'
        verbose_name_plural = 'Emergency Requests'


class Payment(models.Model):
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_METHODS = [
        ('stripe', 'Stripe'),
        ('chargily', 'Chargily'),
    ]
    
    # Core fields
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    emergency_request = models.ForeignKey(
        EmergencyRequest, 
        on_delete=models.CASCADE,
        related_name='payments'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    
    # Transaction details
    transaction_id = models.CharField(max_length=255, unique=True, blank=True, null=True)
    receipt_url = models.URLField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def mark_as_completed(self, transaction_id=None, receipt_url=None):
        """Helper method to mark payment as completed"""
        self.status = 'completed'
        if transaction_id:
            self.transaction_id = transaction_id
        if receipt_url:
            self.receipt_url = receipt_url
        self.completed_at = timezone.now()
        self.save()
        
        # Also update the emergency request status if needed
        if self.emergency_request.status == 'accepted':
            self.emergency_request.set_completed()
    
    def __str__(self):
        return f"Payment #{self.id} - {self.get_status_display()} - ${self.amount}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'


class Rating(models.Model):
    """Model for storing user ratings and reviews after service completion"""
    emergency_request = models.OneToOneField(
        EmergencyRequest,
        on_delete=models.CASCADE,
        related_name='rating'
    )
    rating = models.PositiveSmallIntegerField(choices=[(i, i) for i in range(1, 6)])
    review = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Rating for Request #{self.emergency_request.id}: {self.rating}/5"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Rating'
        verbose_name_plural = 'Ratings'