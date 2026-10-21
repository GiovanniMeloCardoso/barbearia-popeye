from django.core.management.base import BaseCommand
from agendamento.models import Servico, Barbeiro
from datetime import time

class Command(BaseCommand):
    help = 'Popula os serviços e barbeiro padrão na Barbearia Popeye'

    def handle(self, *args, **options):
        servicos_dados = [
            {'nome': 'Corte', 'preco': 40.00, 'duracao_minutos': 45},
            {'nome': 'Barba', 'preco': 35.00, 'duracao_minutos': 30},
            {'nome': 'Corte e Barba', 'preco': 75.00, 'duracao_minutos': 60},
            {'nome': 'Sobrancelhas', 'preco': 10.00, 'duracao_minutos': 5},
            {'nome': 'Corte Máq. 1 Pente', 'preco': 25.00, 'duracao_minutos': 30},
            {'nome': 'Pigmentação Barba', 'preco': 30.00, 'duracao_minutos': 30},
            {'nome': 'Selagem', 'preco': 50.00, 'duracao_minutos': 50},
            {'nome': 'Higienização Nariz', 'preco': 20.00, 'duracao_minutos': 15},
            {'nome': 'Alisamento FIO a FIO', 'preco': 35.00, 'duracao_minutos': 45},
            {'nome': 'Acabamento', 'preco': 15.00, 'duracao_minutos': 20},
            {'nome': 'Barba Máquina', 'preco': 25.00, 'duracao_minutos': 30},
        ]

        for dados in servicos_dados:
            servico, created = Servico.objects.update_or_create(
                nome=dados['nome'],
                defaults={
                    'preco': dados['preco'],
                    'duracao_minutos': dados['duracao_minutos'],
                }
            )
            status = 'Criado' if created else 'Atualizado'
            self.stdout.write(self.style.SUCCESS(f'{status} serviço: {servico.nome} (R$ {servico.preco}, {servico.duracao_minutos} min)'))

        # Garantir barbeiro Henrique padrão
        henrique, created = Barbeiro.objects.get_or_create(
            nome='Henrique',
            defaults={
                'cargo': 'Barbeiro Chefe',
                'telefone': '34 99139-5770',
                'horario_inicio': time(9, 0),
                'horario_fim': time(20, 0),
                'dias_trabalho': '0,1,2,3,4,5',
                'ativo': True
            }
        )
        if not created:
            if not henrique.telefone:
                henrique.telefone = '34 99139-5770'
            if not henrique.cargo:
                henrique.cargo = 'Barbeiro Chefe'
            henrique.ativo = True
            henrique.save()
        
        self.stdout.write(self.style.SUCCESS(f'Barbeiro padrão pronto: {henrique.nome}'))
