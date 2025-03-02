
from .views import RegisterView, LoginView, LogoutView,nearby_requests,accept_request
from django.urls import path
from .views import create_emergency_request



urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('nearby-requests/', nearby_requests, name='nearby_requests'),
    path('emergency-request/', create_emergency_request, name='create_emergency_request'),
    path('accept-request/<int:request_id>/', accept_request, name='accept_request'),

]

