
#Autenticador de Cookies con este código para que Django aprenda a leer la cookie que tú mismo creaste en el login:

from rest_framework.authentication import TokenAuthentication

class CookieTokenAuthentication(TokenAuthentication):
    def authenticate(self, request):
        # Buscamos el token en las cookies en lugar de los headers
        token = request.COOKIES.get('auth_token')
        
        if not token:
            return None
            
        return self.authenticate_credentials(token)