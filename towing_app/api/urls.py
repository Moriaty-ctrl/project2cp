
from .views import RegisterView, LoginView, LogoutView
from django.urls import path
from .views import create_emergency_request



urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('emergency-request/', create_emergency_request, name='create_emergency_request'),
]

