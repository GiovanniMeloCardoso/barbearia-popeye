from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('horarios/', views.horarios_disponiveis, name='horarios_disponiveis'),
    path('painel/', views.painel_barbeiro, name='painel'),
    path('cancelar/<int:id>/', views.cancelar_agendamento, name='cancelar_agendamento'),
    path('cancelar-cliente/<str:token>/', views.cancelar_cliente, name='cancelar_cliente'),
]