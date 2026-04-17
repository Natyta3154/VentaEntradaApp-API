from rest_framework import serializers
from .models import Dj, Evento, TipoTicket, Orden, GaleriaMedia, Ticket
from django.contrib.auth.models import User



#--- SERIALIZADOR DE DJ ---
class DjSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dj
        fields = '__all__'




#--- SERIALIZADOR DE GALERIA ---
class GaleriaSerializer(serializers.ModelSerializer):
    archivo_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = GaleriaMedia
        fields = ['id', 'titulo', 'archivo_url', 'thumbnail_url', 'es_video', 'categoria', 'fecha_subida']

    def get_archivo_url(self, obj):
        if obj.archivo:
            return obj.archivo.url
        return None

    def get_thumbnail_url(self, obj):
        if obj.archivo:
            # Optimizamos para dispositivos móviles: 400px es suficiente para galerías
            # Cloudinary permite transformar la URL directamente
            if obj.es_video:
                # Si es video, Cloudinary genera el frame .jpg automáticamente si cambiamos la extensión
                # y aplicamos transformaciones (w_400 = 400px de ancho)
                return obj.archivo.url.replace(".mp4", ".jpg").replace(".mov", ".jpg").replace("/video/upload/", "/video/upload/w_400,c_limit/")
            
            # Para imágenes, redimensionamos con c_scale
            return obj.archivo.url.replace("/image/upload/", "/image/upload/w_400,c_scale/")
        return None



#--- SERIALIZADOR DE TIPO DE TICKET ---
class TipoTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoTicket
        fields = ['id', 'nombre', 'precio', 'stock_disponible', 'orden']



#--- SERIALIZADOR DE EVENTO ---
class EventoSerializer(serializers.ModelSerializer):
    artistas = DjSerializer(many=True, read_only=True)
    tipos_tickets = TipoTicketSerializer(many=True, read_only=True)
    
    class Meta:
        model = Evento
        fields = [
            'id', 'titulo', 'descripcion', 'fecha', 
            'ciudad', 'lugar', 'tipo_ritmo', 'precio_entrada',
            'capacidad_maxima', 'imagen_portada', 'artistas', 
            'es_destacado', 'tipos_tickets'
        ]



#--- SERIALIZADOR DE TICKET ---
class TicketSerializer(serializers.ModelSerializer):
    evento_titulo = serializers.ReadOnlyField(source='evento.titulo')
    evento_fecha = serializers.ReadOnlyField(source='evento.fecha')

    class Meta:
        model = Ticket
        fields = ['id', 'evento', 'evento_titulo', 'evento_fecha', 'codigo_seguridad', 'pagado', 'usado', 'precio_pagado', 'fecha_creacion']



#--- SERIALIZADORES DE USUARIO ---
class UserSerializer(serializers.ModelSerializer):
    """Este serializador sirve para mostrar los datos del usuario logueado"""
    nombre_completo = serializers.SerializerMethodField()
    puedo_escanear = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'nombre_completo', 'is_staff', 'is_superuser', 'puedo_escanear')

    def get_puedo_escanear(self, obj):
        # Es staff o tiene el permiso específico que creamos
        return obj.is_staff or obj.has_perm('eventos.can_validate_tickets')

    def get_nombre_completo(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username



#--- SERIALIZADOR DE REGISTRO ---
class RegistroSerializer(serializers.ModelSerializer):
    # La contraseña debe ser escrita pero nunca leída por el frontend
    password = serializers.CharField(write_only=True, min_length=8) # Bajé a 8 para ser más estándar, pero mantén 10 si prefieres
    
    # Validamos que el email sea obligatorio y único
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'first_name', 'last_name')

    def validate_email(self, value):
        """
        Verifica que el email no exista ya en la base de datos para evitar duplicados.
        """
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Este correo electrónico ya está registrado.")
        return value

    def validate_username(self, value):
        """
        Verifica que el nombre de usuario no esté tomado.
        """
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Este nombre de usuario ya existe.")
        return value

    def create(self, validated_data):
        # create_user se encarga de encriptar la contraseña automáticamente
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )
        return user