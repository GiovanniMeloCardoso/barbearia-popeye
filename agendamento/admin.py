from django.contrib import admin
from django.utils.html import format_html
from .models import Servico, Agendamento, Barbeiro

@admin.register(Barbeiro)
class BarbeiroAdmin(admin.ModelAdmin):
    list_display = ('foto_preview', 'nome', 'cargo', 'telefone', 'horario_inicio', 'horario_fim', 'ativo', 'criado_em')
    list_filter = ('ativo',)
    search_fields = ('nome', 'cargo', 'telefone')
    ordering = ('id',)

    def foto_preview(self, obj):
        url = obj.foto_url
        if url:
            return format_html('<img src="{}" style="width: 40px; height: 40px; border-radius: 50%; object-fit: cover;" onerror="this.style.display=\'none\';" />', url)
        return format_html('<div style="width: 40px; height: 40px; border-radius: 50%; background: #d4af37; color: #000; display: flex; align-items: center; justify-content: center; font-weight: bold;">{}</div>', obj.nome[0] if obj.nome else '?')
    foto_preview.short_description = 'Foto'

@admin.register(Servico)
class ServicoAdmin(admin.ModelAdmin):
    list_display = ('ordem', 'nome', 'preco', 'duracao_minutos')
    list_display_links = ('nome',)
    list_editable = ('ordem',)
    search_fields = ('nome',)
    ordering = ('ordem', 'id')

@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ('nome_cliente', 'telefone', 'barbeiro', 'data', 'hora', 'duracao_minutos', 'total_display')
    list_filter = ('data', 'barbeiro')
    search_fields = ('nome_cliente', 'telefone')

    def total_display(self, obj):
        return f"R$ {obj.total():.2f}"
    total_display.short_description = 'Total'

admin.site.site_header = "Barbearia Popeye Admin"
admin.site.site_title = "Barbearia Popeye"
admin.site.index_title = "Painel Administrativo"