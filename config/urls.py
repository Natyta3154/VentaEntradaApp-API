"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken import views as auth_views
from eventos.views import ComprarTicketView, CustomLoginView, EventoViewSet, DjViewSet, GaleriaMediaViewSet, LogoutView, RegistroView, PerfilUsuarioView, ValidarTicketView, MercadoPagoWebhookView

router = DefaultRouter()
router.register(r'eventos', EventoViewSet, basename='evento')
router.register(r'djs', DjViewSet)
router.register(r'galeria', GaleriaMediaViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Todo lo que es API va aquí:
    path('api/', include(router.urls)),
    path('api/registro/', RegistroView.as_view(), name='registro'),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('api/perfil/', PerfilUsuarioView.as_view(), name='perfil'),
    path('api/logout/', LogoutView.as_view(), name='logout'),

    # info del usuario
    path('api/user-info/', PerfilUsuarioView.as_view(), name='user-info'),

    # Endpoint para comprar tickets
    path('api/comprar-ticket/', ComprarTicketView.as_view(), name='comprar-ticket'),
    # Webhook MercadoPago
    path('api/mercadopago-webhook/', MercadoPagoWebhookView.as_view(), name='mercadopago-webhook'),
    # Endpoint para validar el ticket
    path('api/validar-ticket/', ValidarTicketView.as_view(), name='validar-ticket'),
]