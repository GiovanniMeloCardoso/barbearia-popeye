from django.db import models
from datetime import datetime, timedelta, date, time

class Barbeiro(models.Model):
    nome = models.CharField(max_length=120)
    cargo = models.CharField(max_length=100, default='Barbeiro Profissional')
    foto = models.ImageField(upload_to='barbeiros/', null=True, blank=True)
    telefone = models.CharField(max_length=20, null=True, blank=True)
    horario_inicio = models.TimeField(default=time(9, 0), verbose_name="Horário de Início")
    horario_fim = models.TimeField(default=time(20, 0), verbose_name="Horário de Término")
    intervalo_inicio = models.TimeField(null=True, blank=True, verbose_name="Início do Intervalo/Almoço")
    intervalo_fim = models.TimeField(null=True, blank=True, verbose_name="Fim do Intervalo/Almoço")
    dias_trabalho = models.CharField(max_length=50, default="0,1,2,3,4,5", verbose_name="Dias de Trabalho (0=Seg..5=Sáb, 6=Dom)")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Barbeiro'
        verbose_name_plural = 'Barbeiros'
        ordering = ['id']

    def __str__(self):
        return f"{self.nome} ({self.cargo})"

    @property
    def foto_url(self):
        if self.foto:
            try:
                return self.foto.url
            except (ValueError, Exception):
                return '/static/img/henrique.jpg'
        return '/static/img/henrique.jpg'

    def trabalha_no_dia(self, data_obj):
        """Retorna True se o barbeiro atende no dia da semana fornecido."""
        if not self.dias_trabalho:
            return data_obj.weekday() != 6  # Padrão: Segunda a Sábado
        dias = [int(d.strip()) for d in self.dias_trabalho.split(',') if d.strip().isdigit()]
        return data_obj.weekday() in dias

    def esta_no_horario_trabalho(self, hora_inicio, duracao_minutos):
        """Verifica se o horário e duração cabem no expediente do barbeiro sem bater no intervalo."""
        h_ini = self.horario_inicio or time(9, 0)
        h_fim = self.horario_fim or time(20, 0)
        
        dummy_date = date.today()
        atend_inicio = datetime.combine(dummy_date, hora_inicio)
        atend_fim = atend_inicio + timedelta(minutes=duracao_minutos)
        
        limite_inicio = datetime.combine(dummy_date, h_ini)
        limite_fim = datetime.combine(dummy_date, h_fim)
        
        if atend_inicio < limite_inicio or atend_fim > limite_fim:
            return False
            
        if self.intervalo_inicio and self.intervalo_fim:
            almoco_inicio = datetime.combine(dummy_date, self.intervalo_inicio)
            almoco_fim = datetime.combine(dummy_date, self.intervalo_fim)
            if max(atend_inicio, almoco_inicio) < min(atend_fim, almoco_fim):
                return False
                
        return True


class Servico(models.Model):
    nome = models.CharField(max_length=100)
    preco = models.DecimalField(max_digits=6, decimal_places=2)
    duracao_minutos = models.IntegerField(default=30, verbose_name="Duração (minutos)")
    ordem = models.PositiveIntegerField(default=10, verbose_name="Ordem de Exibição")

    class Meta:
        verbose_name = 'Serviço'
        verbose_name_plural = 'Serviços'
        ordering = ['ordem', 'id']

    def __str__(self):
        return f"{self.nome} - R$ {self.preco} ({self.duracao_minutos} min)"


class Agendamento(models.Model):
    nome_cliente = models.CharField(max_length=150)
    telefone = models.CharField(max_length=20)
    servicos = models.ManyToManyField(Servico)
    barbeiro = models.ForeignKey(Barbeiro, on_delete=models.SET_NULL, null=True, blank=True, related_name='agendamentos')
    data = models.DateField()
    hora = models.TimeField()
    duracao_minutos = models.IntegerField(default=30)
    token = models.CharField(max_length=100, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Agendamento'
        verbose_name_plural = 'Agendamentos'
        ordering = ['-data', '-hora']

    def __str__(self):
        barbeiro_nome = self.barbeiro.nome if self.barbeiro else "Sem preferência"
        return f"{self.nome_cliente} - {self.data.strftime('%d/%m/%Y')} às {self.hora.strftime('%H:%M')} ({barbeiro_nome})"

    def total(self):
        return sum(s.preco for s in self.servicos.all())

    @property
    def hora_fim(self):
        dt = datetime.combine(self.data, self.hora) + timedelta(minutes=self.duracao_minutos)
        return dt.time()