from django.db import models

class Servico(models.Model):
    nome = models.CharField(max_length=100)
    preco = models.DecimalField(max_digits=6, decimal_places=2)

    def __str__(self):
        return f"{self.nome} - R$ {self.preco}"

class Agendamento(models.Model):
    nome_cliente = models.CharField(max_length=150)
    telefone = models.CharField(max_length=20)
    servicos = models.ManyToManyField(Servico)
    data = models.DateField()
    hora = models.TimeField()
    token = models.CharField(max_length=100, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nome_cliente} - {self.data.strftime('%d/%m/%Y')} às {self.hora.strftime('%H:%M')}"

    def total(self):
        return sum(s.preco for s in self.servicos.all())