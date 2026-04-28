import os
from django.http import JsonResponse
from django.shortcuts import render
from rest_framework import viewsets, filters, generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
# Importamos tu autenticador personalizado
from .authentication import CookieTokenAuthentication 
from rest_framework.authtoken.models import Token as TokenDRF 
from rest_framework.authtoken.serializers import AuthTokenSerializer
from django.utils.html import strip_tags
from django.core.mail import EmailMultiAlternatives, get_connection
from django.contrib.auth import logout as django_logout
import mercadopago
from config import settings 

from .models import Evento, Orden, TipoTicket, Dj, GaleriaMedia, Ticket
from .serializers import (
    EventoSerializer, DjSerializer, GaleriaSerializer, 
    UserSerializer, TicketSerializer, RegistroSerializer
)

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction, models
from django.db.models import F

# --- VISTAS DE AUTENTICACIÓN ---

@method_decorator(csrf_exempt, name='dispatch')
class CustomLoginView(APIView):
    authentication_classes = [] # No requiere auth previa
    permission_classes = []
    
    def post(self, request):
        # El AuthTokenSerializer espera 'username' y 'password' en el JSON
        serializer = AuthTokenSerializer(data=request.data, context={'request': request})
        
        # Validamos manualmente para capturar el error y enviar un mensaje amigable
        if not serializer.is_valid():
            return Response({
                "mensaje": "Usuario o contraseña incorrectos. Por favor, verifica tus datos."
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Si es válido, extraemos al usuario
        user = serializer.validated_data['user']
        
        # Obtenemos o creamos el token para este usuario
        token, _ = TokenDRF.objects.get_or_create(user=user)
        
        # Preparamos la respuesta con los datos que necesita React (Usando el Serializer para consistencia)
        user_serializer = UserSerializer(user)
        
        response = Response({
            "usuario": user_serializer.data,
            "token": token.key,
            "mensaje": "¡Bienvenido a la rumba!"
        }, status=status.HTTP_200_OK)

        # Seteamos la cookie segura con el token (Forzamos seguridad para producción)
        response.set_cookie(
            key='auth_token', 
            value=token.key, 
            httponly=True,
            samesite='None',
            secure=True,
            max_age=60*60*24*7 # 7 días de duración
        )
        
        return response

class LogoutView(APIView):
    def post(self, request):
        django_logout(request)
        response = Response({"message": "Sesión cerrada correctamente"}, status=status.HTTP_200_OK)
        response.delete_cookie('auth_token')
        return response

# --- VISTAS DEL PERFIL Y TICKETS (PROTEGIDAS) ---


class PerfilUsuarioView(APIView):
    authentication_classes = [CookieTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Obtener datos del usuario y sus tickets"""
        user_serializer = UserSerializer(request.user)
        tickets = Ticket.objects.filter(usuario=request.user)
        return Response({
            "usuario": user_serializer.data,
            "mis_tickets": TicketSerializer(tickets, many=True).data
        })

    def patch(self, request):
        """Actualizar datos personales (Nombre, Apellido, Email)"""
        user = request.user
        data = request.data

        # Actualizamos los campos si vienen en la petición
        user.first_name = data.get('first_name', user.first_name)
        user.last_name = data.get('last_name', user.last_name)
        user.email = data.get('email', user.email)

        try:
            user.save()
            # Devolvemos los datos actualizados para que React los vea de inmediato
            return Response({
                "mensaje": "Perfil actualizado correctamente",
                "usuario": UserSerializer(user).data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "mensaje": "Error al actualizar el perfil",
                "error": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        




class ComprarTicketView(APIView):
    authentication_classes = [CookieTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        evento_id = request.data.get('evento_id')
        tipo_ticket_id = request.data.get('tipo_ticket_id') # RECIBIMOS EL ID ESPECIFICO
        user = request.user
        
        try:
            evento = Evento.objects.get(id=evento_id)
            
            # 1. BUSCAMOS EL TIPO DE TICKET SOLICITADO
            if tipo_ticket_id:
                try:
                    tipo_ticket = TipoTicket.objects.get(id=tipo_ticket_id, evento=evento)
                except TipoTicket.DoesNotExist:
                    return Response({"mensaje": "El tipo de ticket seleccionado no es válido."}, status=400)
            else:
                # Fallback por si acaso: buscamos el primero disponible por orden
                tipo_ticket = evento.tipos_tickets.filter(stock_disponible__gt=0).first()

            if not tipo_ticket:
                return Response({
                    "mensaje": "Lo sentimos, no hay tickets disponibles para este evento."
                }, status=status.HTTP_400_BAD_REQUEST)

            # 2. VALIDAMOS STOCK ANTES DE HACER NADA
            if tipo_ticket.stock_disponible <= 0:
                return Response({
                    "mensaje": f"Lo sentimos, las entradas tipo '{tipo_ticket.nombre}' se han agotado."
                }, status=status.HTTP_400_BAD_REQUEST)

            # Usamos el precio y nombre del ticket seleccionado
            precio_final = tipo_ticket.precio
            nombre_ticket = f"{evento.titulo} - {tipo_ticket.nombre}"

            token = getattr(settings, 'MP_ACCESS_TOKEN', None)
            if not token:
                return Response({"error": "Configuración de token en el servidor incorrecta"}, status=500)

            # --- CREACIÓN PREVIA DEL TICKET (Estado: Pendiente) ---
            # Lo creamos aquí para tener un ID único que enviar a MercadoPago
            ticket = Ticket.objects.create(
                evento=evento,
                tipo_ticket=tipo_ticket,
                usuario=user,
                precio_pagado=precio_final, 
                pagado=False # Pendiente de confirmación por Webhook
            )

            sdk = mercadopago.SDK(token)

            preference_data = {
                "items": [
                    {
                        "id": str(tipo_ticket.id),
                        "title": nombre_ticket,
                        "quantity": 1,
                        "unit_price": float(precio_final),
                        "currency_id": "ARS"
                    }
                ],
                "back_urls": {
                    "success": "http://localhost:5173/pago-exitoso",
                    "failure": "http://localhost:5173/tickets",
                    "pending": "http://localhost:5173/pago-pendiente"
                },
                "notification_url": "https://tu-dominio-o-ngrok.com/api/mercadopago-webhook/", # WEBHOOK
                "external_reference": str(ticket.id), # REFERENCIA AL ID DEL TICKET
                "binary_mode": True
            }

            result = sdk.preference().create(preference_data)
            
            if result["status"] in [200, 201]:
                # ENVIAMOS EMAIL DE "PROCESANDO" (Opcional, podrías enviarlo solo al confirmar)

                # En el nuevo flujo, el mail de éxito y el QR se envían en el WEBHOOK
                # cuando el estado pasa a 'approved'.

                return Response({
                    "init_point": result["response"]["init_point"],
                    "tipo_ticket_nombre": tipo_ticket.nombre
                }, status=200)
            else:
                return Response(result["response"], status=400)

        except Evento.DoesNotExist:
            return Response({"error": "Evento no encontrado"}, status=404)
        except Exception as e:
            print(f"ERROR EXCEPCION: {str(e)}")
            return Response({"error": str(e)}, status=400)


def enviar_email_ticket(ticket):
    """Función auxiliar para enviar el QR una vez confirmado el pago"""
    try:
        user = ticket.usuario
        evento = ticket.evento
        tipo_ticket = ticket.tipo_ticket
        nombre_ticket = f"{evento.titulo} - {tipo_ticket.nombre}"
        precio_final = ticket.precio_pagado

        subject = f'🎟️ Tu entrada para {nombre_ticket}'
        from_email = settings.DEFAULT_FROM_EMAIL
        to = user.email 
        
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={ticket.codigo_seguridad}"

        html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif;">
                    <h2>¡Hola {user.first_name or user.username}!</h2>
                    <p>¡Pago Confirmado! Tu entrada para <b>{evento.titulo}</b> ({tipo_ticket.nombre}) ya está lista.</p>
                    <p>Precio abonado: <b>${precio_final}</b></p>
                    <p>Código de Seguridad: <b>{ticket.codigo_seguridad}</b></p>
                    <div style="text-align: center;">
                        <img src="{qr_url}" alt="QR Code" style="width:200px; border: 1px solid #ddd;">
                    </div>
                </body>
            </html>
        """
        text_content = strip_tags(html_content)

        import ssl
        context = ssl._create_unverified_context()

        connection = get_connection(
            backend=settings.EMAIL_BACKEND, 
            ssl_context=context 
        )

        msg = EmailMultiAlternatives(subject, text_content, from_email, [to], connection=connection)
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        print(f"✅ ÉXITO: Mail enviado a {to} para {tipo_ticket.nombre}")
        return True
    except Exception as e:
        print(f"❌ ERROR AL ENVIAR MAIL: {str(e)}")
        return False


@method_decorator(csrf_exempt, name='dispatch')
class MercadoPagoWebhookView(APIView):
    """
    Recibe las notificaciones de Mercado Pago (IPN / Webhooks)
    """
    authentication_classes = [] # Sin auth para MP
    permission_classes = []

    def post(self, request):
        # Obtenemos el ID de la notificación
        # MP envía ?topic=payment&id=12345 o un JSON en el body
        payment_id = request.query_params.get('data.id') or request.data.get('data', {}).get('id')
        topic = request.query_params.get('type') or request.data.get('type')

        if topic == 'payment' and payment_id:
            token = getattr(settings, 'MP_ACCESS_TOKEN', None)
            sdk = mercadopago.SDK(token)
            
            # Consultamos el estado real del pago en MP
            payment_info = sdk.payment().get(payment_id)
            
            if payment_info["status"] == 200:
                payment_data = payment_info["response"]
                status_mp = payment_data.get("status")
                ticket_id = payment_data.get("external_reference")

                if status_mp == "approved" and ticket_id:
                    try:
                        with transaction.atomic():
                            # Buscamos el ticket (bloqueando la fila para evitar duplicidad)
                            ticket = Ticket.objects.select_for_update().get(id=ticket_id)
                            
                            if not ticket.pagado:
                                # ⚠️ AQUÍ SE DESCUENTA EL STOCK REAL
                                tipo = ticket.tipo_ticket
                                if tipo.stock_disponible > 0:
                                    tipo.stock_disponible = F('stock_disponible') - 1
                                    tipo.save()
                                    
                                    ticket.pagado = True
                                    ticket.save()
                                    
                                    # Enviamos el mail con el QR
                                    enviar_email_ticket(ticket)
                                    print(f"💰 PAGO APROBADO: Ticket {ticket.id} procesado.")
                                else:
                                    print(f"🚫 ERROR: No hay stock para el ticket {ticket.id} (pago aprobado)")
                            else:
                                print(f"ℹ️ Ticket {ticket.id} ya estaba marcado como pagado.")

                    except Ticket.DoesNotExist:
                        print(f"❌ ERROR: Ticket ID {ticket_id} no encontrado en la DB.")
                    except Exception as e:
                        print(f"❌ ERROR WEBHOOK: {str(e)}")

        return Response(status=200)



class ValidarTicketView(APIView):
    # Usamos CookieTokenAuthentication para que el personal logueado en la web pueda usarlo
    authentication_classes = [CookieTokenAuthentication]
    permission_classes = [IsAuthenticated] 

    def post(self, request):
        # SEGURIDAD: Solo Staff o Usuarios con permiso específico (Porteros)
        if not (request.user.is_staff or request.user.has_perm('eventos.can_validate_tickets')):
            return Response({"status": "rojo", "mensaje": "NO TIENES PERMISO PARA VALIDAR ACCESOS"}, status=status.HTTP_403_FORBIDDEN)

        codigo = request.data.get('codigo_seguridad')
        if not codigo:
            return Response({"status": "rojo", "mensaje": "FALTA CÓDIGO"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Buscamos el ticket y traemos datos relacionados para el portero
            ticket = Ticket.objects.select_related('usuario', 'tipo_ticket', 'evento').get(codigo_seguridad=codigo)
            
            # Datos para mostrar en el scanner:
            datos_ticket = {
                "usuario": f"{ticket.usuario.first_name} {ticket.usuario.last_name}".strip() or ticket.usuario.username,
                "email": ticket.usuario.email,
                "tipo": ticket.tipo_ticket.nombre,
                "evento": ticket.evento.titulo,
            }

            if ticket.usado:
                return Response({
                    "status": "rojo", 
                    "mensaje": "TICKET YA USADO",
                    "detalles": datos_ticket
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Marcamos como usado
            ticket.usado = True
            ticket.save()
            
            return Response({
                "status": "verde", 
                "mensaje": "ACCESO PERMITIDO",
                "detalles": datos_ticket
            }, status=status.HTTP_200_OK)

        except Ticket.DoesNotExist:
            return Response({"status": "rojo", "mensaje": "TICKET NO VÁLIDO"}, status=status.HTTP_404_NOT_FOUND)

from django.utils import timezone

# --- VISTAS PÚBLICAS ---

class EventoViewSet(viewsets.ModelViewSet):
    serializer_class = EventoSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['ciudad', 'titulo', 'tipo_ritmo']

    def get_queryset(self):
        """Filtramos para que solo salgan eventos de hoy en adelante"""
        return Evento.objects.filter(fecha__gte=timezone.now()).order_by('fecha')

class DjViewSet(viewsets.ModelViewSet):
    queryset = Dj.objects.all()
    serializer_class = DjSerializer

class GaleriaMediaViewSet(viewsets.ModelViewSet):
    queryset = GaleriaMedia.objects.all().order_by('-fecha_subida')
    serializer_class = GaleriaSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

@method_decorator(csrf_exempt, name='dispatch')
class RegistroView(APIView):
    authentication_classes = []
    permission_classes = []
    
    def post(self, request):
        serializer = RegistroSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            TokenDRF.objects.get_or_create(user=user)
            return Response({"mensaje": "Usuario creado con éxito"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    





#-- VISTA PARA CREAR PREFERENCIA DE PAGO EN MERCADO PAGO ---
def crear_preferencia(request, evento_id):
    # Configura el SDK con tu Token de las variables de entorno
    sdk = mercadopago.SDK(os.getenv("MP_ACCESS_TOKEN"))

    try:
        evento = Evento.objects.get(id=evento_id)
        
        # Estructura de la preferencia
        preference_data = {
            "items": [
                {
                    "id": str(evento.id),
                    "title": evento.titulo,
                    "quantity": 1,
                    "unit_price": float(evento.precio_entrada), # Precio real de tu DB
                    "currency_id": "ARS"
                }
            ],
            "back_urls": {
                "success": "http://localhost:3000/pago-exitoso",
                "failure": "http://localhost:3000/tickets",
                "pending": "http://localhost:3000/pago-pendiente"
            },
            "auto_return": "approved",
            # Esto es vital para saber quién compró después
            "external_reference": f"user_{request.user.id}_event_{evento.id}" 
        }

        result = sdk.preference().create(preference_data)
        
        # Devolvemos el init_point (la URL donde el usuario pagará)
        return JsonResponse({
            "preference_id": result["response"]["id"],
            "init_point": result["response"]["init_point"]
        })

    except Evento.DoesNotExist:
        return JsonResponse({"error": "Evento no encontrado"}, status=404)


def home(request):
    return JsonResponse({
        "status": "ok",
        "message": "Bienvenido a API salsa funcionando correctamente",
        "endpoints": {
            "eventos": "/api/eventos/",
            "djs": "/api/djs/",
            "galeria": "/api/galeria/",
            "registro": "/api/registro/",
            "login": "/login/",
            "perfil": "/api/perfil/",
            "logout": "/api/logout/",
            "user-info": "/api/user-info/",
        }
    })