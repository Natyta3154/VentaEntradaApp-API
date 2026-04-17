from django.db import models
from django.contrib.auth.models import User
import uuid
from cloudinary.models import CloudinaryField


#--- MODELO DE DJ ---
class Dj(models.Model):
    nombre = models.CharField(max_length=100)
    biografia = models.TextField(blank=True)
    estilo_musical = models.CharField(max_length=50, default="Salsa")
    foto = models.ImageField(upload_to='djs/', null=True, blank=True)

    def __str__(self):
        return self.nombre


#--- MODELO DE EVENTO ---
class Evento(models.Model):
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    fecha = models.DateTimeField()
    ciudad = models.CharField(max_length=100)
    lugar = models.CharField(max_length=200)
    tipo_ritmo = models.CharField(max_length=50, default="Salsa")
    
    # Por retro-compatibilidad dejamos el precio_entrada base, aunque ahora hay TipoTicket
    precio_entrada = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) 
    
    es_destacado = models.BooleanField(default=False)
    imagen_portada = models.ImageField(upload_to='eventos/')
    artistas = models.ManyToManyField(Dj, related_name='eventos')
    
    # MEJORA: Aforo máximo para controlar la sobreventa
    capacidad_maxima = models.PositiveIntegerField(default=100, help_text="Aforo total permitido")

    def __str__(self):
        return self.titulo


#--- MODELO DE TIPO DE TICKET ---
class TipoTicket(models.Model):
    """MEJORA: Maneja diferentes fases/categorías de entradas (VIP, General)"""
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name='tipos_tickets')
    nombre = models.CharField(max_length=100, help_text="Ej: General, VIP, Fase 1")
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    stock_disponible = models.PositiveIntegerField(default=50)
    orden = models.PositiveIntegerField(default=1, help_text="Prioridad de venta (1 es primero)")

    class Meta:
        ordering = ['orden']

    def __str__(self):
        return f"{self.nombre} - {self.evento.titulo} (${self.precio})"


#--- MODELO DE ORDEN ---
class Orden(models.Model):
    """MEJORA: Representa el carrito o proceso de compra agrupando múltiples tickets."""
    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('aprobada', 'Aprobada'),
        ('rechazada', 'Rechazada'),
    ]
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ordenes')
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    metodo_pago = models.CharField(max_length=50, default="MercadoPago")
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Orden #{self.id} - {self.usuario.username} - {self.estado}"


#--- MODELO DE GALERIA ---
class GaleriaMedia(models.Model):
    CATEGORIAS = [
        ('evento', 'Fotos de Eventos'),
        ('promo', 'Promocionales'),
        ('dj', 'Artistas'),
    ]
    titulo = models.CharField(max_length=100, blank=True, verbose_name="Título o Descripción")
    archivo = CloudinaryField('archivo', resource_type="auto", folder="galeria_app/")
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default='evento')
    es_video = models.BooleanField(default=False, help_text="Marcar si el archivo subido es un video")
    fecha_subida = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Galería de Fotos y Videos"
        verbose_name_plural = "Galería de Fotos y Videos"

    def __str__(self):
        return f"{self.titulo or 'Sin título'} [{self.categoria}] ({self.id})"


#--- MODELO DE TICKET ---
class Ticket(models.Model):
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE)
    
    # Relaciones Opcionales, por ahora, para que el código anterior no rompa
    orden = models.ForeignKey(Orden, on_delete=models.CASCADE, null=True, blank=True, related_name="tickets")
    tipo_ticket = models.ForeignKey(TipoTicket, on_delete=models.SET_NULL, null=True, blank=True)
    
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    codigo_seguridad = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    # MEJORA: Precio históricamente pagado
    precio_pagado = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    pagado = models.BooleanField(default=False)
    usado = models.BooleanField(default=False)
    
    # MEJORA: Tracker de creación
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [
            ("can_validate_tickets", "Puede validar tickets en la puerta"),
        ]

    def save(self, *args, **kwargs):
        # MEJORA: Eliminamos todo el código que generaba la imagen local QR o la enviaba a Cloudinary.
        # Ahora la base de datos es mucho más eficiente. El código UUID es el único identificador necesario.
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Ticket {self.id} - {self.evento.titulo}"
