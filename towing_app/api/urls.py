
from .views import RegisterView, LoginView, LogoutView, nearby_requests,accept_request,reject_request,create_checkout_session, payment_success, payment_failed
from django.urls import path
from .views import create_emergency_request



urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('nearby-requests/', nearby_requests, name='nearby_requests'),
    path('emergency-request/', create_emergency_request, name='create_emergency_request'),
    path('accept-request/<int:request_id>/', accept_request, name='accept_request'),
    path('reject-request/<int:request_id>/', reject_request, name='reject_request'),
    path('api/pay/<int:request_id>/', create_checkout_session, name='create_checkout_session'),
    path('payment-success/', payment_success, name='payment_success'),
    path('payment-cancel/', payment_failed, name='payment_cancel'),
]

