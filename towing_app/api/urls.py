# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import EmergencyRequestViewSet 
# Create a router for ViewSets
router = DefaultRouter()
router.register(r'emergency-requests', views.EmergencyRequestViewSet, basename='emergency-request')

urlpatterns = [
    # Authentication URLs - keep using class-based views
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    
    # Payment URLs - keep using function-based view for consolidated payment system
    path('payment/create/', views.create_payment, name='create-payment'),
    path('payment/success/', views.payment_success, name='payment-success'),
    path('payment/failed/', views.payment_failed, name='payment-failed'),
    path('payment/chargily-webhook/', views.chargily_webhook, name='chargily-webhook'),
    
    # Include ViewSet routes - this will handle CRUD operations for emergency requests
    path('', include(router.urls)),
    
    # Legacy URLs - these should eventually be removed in favor of the ViewSet routes
    # They're kept temporarily for backward compatibility
    path('nearby-requests/', views.nearby_requests, name='nearby_requests'),
    path('emergency-request/', views.create_emergency_request, name='create_emergency_request'),
    path('accept-request/<int:request_id>/', views.accept_request, name='accept_request'),
    path('reject-request/<int:request_id>/', views.reject_request, name='reject_request'),
]