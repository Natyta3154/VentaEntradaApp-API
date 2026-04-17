from django.contrib import admin
from django.utils.html import format_html
from .models import Dj, Evento, TipoTicket, Orden, GaleriaMedia, Ticket

# 1. Administración de DJs
@admin.register(Dj)
class DjAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'estilo_musical', 'mostrar_foto')
    search_fields = ('nombre', 'estilo_musical')

    def mostrar_foto(self, obj):
        if obj.foto:
            return format_html('<img src="{}" style="width: 45px; height:45px; border-radius: 50%; object-fit: cover;" />', obj.foto.url)
        return "Sin foto"
    mostrar_foto.short_description = 'Avatar'


# 2. Administración de la Galería
@admin.register(GaleriaMedia)
class GaleriaMediaAdmin(admin.ModelAdmin):
    list_display = ('id', 'titulo', 'categoria', 'es_video', 'ver_miniatura', 'url_txt', 'fecha_subida')
    list_filter = ('categoria', 'es_video', 'fecha_subida')

    def ver_miniatura(self, obj):
        if obj.archivo:
            if obj.es_video:
                return "🎥 Video"
            return format_html('<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 5px;" />', obj.archivo.url)
        return "Sin archivo"
    ver_miniatura.short_description = 'Miniatura'

    def url_txt(self, obj):
        if obj.archivo:
            return format_html('<a href="{0}" target="_blank" style="font-family: monospace; font-size: 10px;">{0}</a>', obj.archivo.url)
        return "Sin URL"
    url_txt.short_description = 'URL de Cloudinary'


class TipoTicketInline(admin.TabularInline):
    model = TipoTicket
    extra = 1
    fields = ('nombre', 'precio', 'stock_disponible', 'orden')

# 3. Administración de Eventos
@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'ciudad', 'fecha', 'precio_entrada', 'capacidad_maxima', 'es_destacado', 'tickets_restantes')
    list_filter = ('ciudad', 'tipo_ritmo', 'es_destacado', 'fecha')
    search_fields = ('titulo', 'lugar')
    list_editable = ('es_destacado', 'precio_entrada', 'capacidad_maxima')
    filter_horizontal = ('artistas',) 
    inlines = [TipoTicketInline]

    def tickets_restantes(self, obj):
        from django.db.models import Sum
        total_stock = obj.tipos_tickets.aggregate(total=Sum('stock_disponible'))['total'] or 0
        return total_stock
    tickets_restantes.short_description = 'Stock Total Disponible'


@admin.register(TipoTicket)
class TipoTicketAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'evento', 'precio', 'stock_disponible')
    list_filter = ('evento',)
    search_fields = ('nombre', 'evento__titulo')
    list_editable = ('precio', 'stock_disponible')


@admin.register(Orden)
class OrdenAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'total', 'metodo_pago', 'estado', 'fecha_creacion')
    list_filter = ('estado', 'metodo_pago', 'fecha_creacion')
    search_fields = ('usuario__username', 'usuario__email', 'id')


# 4. Administración de Tickets
@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'evento', 'usuario', 'precio_pagado', 'pagado', 'usado', 'fecha_creacion', 'ver_qr_dinamico')
    list_filter = ('evento', 'pagado', 'usado')
    search_fields = ('usuario__username', 'codigo_seguridad')
    readonly_fields = ('codigo_seguridad', 'ver_qr_dinamico', 'fecha_creacion')

    def ver_qr_dinamico(self, obj):
        # Generamos el QR de forma dinámica usando la API pública sin ocupar espacio en DB ni Cloudinary.
        if obj.codigo_seguridad:
            url_qr = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={obj.codigo_seguridad}"
            return format_html(
                '<a href="{0}" target="_blank"><img src="{0}" style="width: 100px; height: 100px; border: 1px solid #ccc; padding: 2px;" alt="QR Code" /></a>',
                url_qr
            )
        return "Falta Código"
    ver_qr_dinamico.short_description = "QR Dinámico"