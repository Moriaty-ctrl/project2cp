from django.contrib import admin
from django.urls import path ,include
from api.views import RegisterView, LoginView, LogoutView
urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
]
from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
