from django.contrib import admin
from django.urls import path, include  # <-- Precisamos importar o 'include'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('agendamento.urls')),  # <-- Esta linha faz a mágica!
]