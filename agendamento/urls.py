from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('horarios/', views.horarios_disponiveis, name='horarios_disponiveis'),
    path('painel/', views.painel_barbeiro, name='painel'),
    path('painel/barbeiro/adicionar/', views.adicionar_barbeiro, name='adicionar_barbeiro'),
    path('painel/barbeiro/editar/<int:id>/', views.editar_barbeiro, name='editar_barbeiro'),
    path('painel/barbeiro/excluir/<int:id>/', views.excluir_barbeiro, name='excluir_barbeiro'),
    path('painel/cliente/cadastrar/', views.cadastrar_cliente_manual, name='cadastrar_cliente_manual'),
    path('painel/cliente/agendar/', views.agendar_cliente_manual, name='agendar_cliente_manual'),
    path('cancelar/<int:id>/', views.cancelar_agendamento, name='cancelar_agendamento'),
    path('cancelar-cliente/<str:token>/', views.cancelar_cliente, name='cancelar_cliente'),
]