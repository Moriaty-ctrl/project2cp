from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = (
        ('driver', 'Driver'),
        ('towing_service', 'Towing Service'),
        ('admin', 'Admin'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    fcm_token = models.CharField(max_length=255, blank=True, null=True)  # Store FCM token

class EmergencyRequest(models.Model):
    DRIVER = 'driver'
    SERVICE = 'service'
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)  # Driver making the request
    latitude = models.DecimalField(max_digits=9, decimal_places=6)  # Store lat
    longitude = models.DecimalField(max_digits=9, decimal_places=6)  # Store long
    vehicle_details = models.TextField()
    problem_type = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Request from {self.user.username} - {self.problem_type}"

