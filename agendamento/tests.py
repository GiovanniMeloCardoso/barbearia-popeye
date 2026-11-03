from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo
from agendamento.models import Barbeiro, Servico, Agendamento, Cliente

SP_TZ = ZoneInfo('America/Sao_Paulo')

class SecurityAuditTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Cria barbeiro padrão de teste
        self.barbeiro = Barbeiro.objects.create(
            nome='Barbeiro Teste',
            cargo='Barbeiro Chefe',
            telefone='34991395770',
            horario_inicio=time(9, 0),
            horario_fim=time(20, 0),
            intervalo_inicio=time(12, 0),
            intervalo_fim=time(13, 0),
            dias_trabalho='0,1,2,3,4,5',
            ativo=True
        )

        # Cria serviços de teste
        self.servico_corte = Servico.objects.create(
            nome='Corte Masculino',
            preco=40.00,
            duracao_minutos=45
        )
        self.servico_barba = Servico.objects.create(
            nome='Barba Tradicional',
            preco=35.00,
            duracao_minutos=30
        )

        # Cria usuário autenticado para testes do painel
        self.user = User.objects.create_user(
            username='barbeiro_admin',
            password='SenhaSeguraForte123!'
        )

    def test_01_bloqueio_agendamento_data_passada(self):
        """Verifica que o backend rejeita agendamentos com data anterior a hoje."""
        ontem = (datetime.now(SP_TZ).date() - timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.post(
            reverse('index'),
            {
                'nome': 'Cliente Teste',
                'telefone': '34999998888',
                'servicos': [self.servico_corte.id],
                'data': ontem,
                'hora': '10:00',
                'barbeiro': self.barbeiro.id
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['sucesso'])
        self.assertIn('passaram', data['mensagem'].lower())
        self.assertEqual(Agendamento.objects.count(), 0)

    def test_02_bloqueio_agendamento_horario_passado_hoje(self):
        """
        VULNERABILIDADE RELATADA PELO IRMÃO:
        Mesmo sendo hoje, não pode permitir agendar um horário que já passou!
        """
        agora = datetime.now(SP_TZ)
        hoje_str = agora.date().strftime('%Y-%m-%d')
        
        # Escolhe um horário sabidamente anterior ao momento atual (ex: 1 hora atrás ou 08:00)
        hora_passada = (agora - timedelta(minutes=15)).strftime('%H:%M')
        
        response = self.client.post(
            reverse('index'),
            {
                'nome': 'Cliente Teste',
                'telefone': '34999998888',
                'servicos': [self.servico_corte.id],
                'data': hoje_str,
                'hora': hora_passada,
                'barbeiro': self.barbeiro.id
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['sucesso'])
        self.assertIn('passou', data['mensagem'].lower())
        self.assertEqual(Agendamento.objects.count(), 0)

    def test_03_bloqueio_agendamento_domingo(self):
        """Verifica que o backend rejeita agendamentos aos domingos (fechado)."""
        hoje = datetime.now(SP_TZ).date()
        dias_ate_domingo = (6 - hoje.weekday()) % 7
        if dias_ate_domingo == 0:
            dias_ate_domingo = 7
        proximo_domingo = (hoje + timedelta(days=dias_ate_domingo)).strftime('%Y-%m-%d')

        response = self.client.post(
            reverse('index'),
            {
                'nome': 'Cliente Teste',
                'telefone': '34999998888',
                'servicos': [self.servico_corte.id],
                'data': proximo_domingo,
                'hora': '14:00',
                'barbeiro': self.barbeiro.id
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['sucesso'])
        self.assertIn('domingo', data['mensagem'].lower())
        self.assertEqual(Agendamento.objects.count(), 0)

    def test_04_bloqueio_horario_fora_expediente(self):
        """Verifica que o backend impede agendamento fora do horário de trabalho do barbeiro (ex: 04:00 da manhã)."""
        # Acha um dia útil no futuro (segunda a sábado)
        data_futura = datetime.now(SP_TZ).date() + timedelta(days=2)
        while data_futura.weekday() == 6:
            data_futura += timedelta(days=1)
        data_str = data_futura.strftime('%Y-%m-%d')

        # Teste 1: Antes do início do expediente (04:00 AM)
        response_madrugada = self.client.post(
            reverse('index'),
            {
                'nome': 'Invasor Madrugada',
                'telefone': '34999998888',
                'servicos': [self.servico_corte.id],
                'data': data_str,
                'hora': '04:00',
                'barbeiro': self.barbeiro.id
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response_madrugada.status_code, 400)
        self.assertFalse(response_madrugada.json()['sucesso'])

        # Teste 2: Ultrapassando o fim do expediente (19:45 para corte de 45 min termina às 20:30, mas expediente fecha às 20:00)
        response_fim = self.client.post(
            reverse('index'),
            {
                'nome': 'Invasor Noite',
                'telefone': '34999998888',
                'servicos': [self.servico_corte.id],
                'data': data_str,
                'hora': '19:45',
                'barbeiro': self.barbeiro.id
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response_fim.status_code, 400)
        self.assertFalse(response_fim.json()['sucesso'])
        self.assertEqual(Agendamento.objects.count(), 0)

    def test_05_bloqueio_servicos_vazios_ou_inexistentes(self):
        """Impede que requisições forjadas com IDs inexistentes criem agendamentos fantasma."""
        data_futura = datetime.now(SP_TZ).date() + timedelta(days=2)
        while data_futura.weekday() == 6:
            data_futura += timedelta(days=1)

        # Sem serviços
        res_vazio = self.client.post(
            reverse('index'),
            {
                'nome': 'Cliente Fantasma',
                'telefone': '34999998888',
                'servicos': [],
                'data': data_futura.strftime('%Y-%m-%d'),
                'hora': '14:00',
                'barbeiro': self.barbeiro.id
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res_vazio.status_code, 400)

        # Com ID de serviço inexistente
        res_inexistente = self.client.post(
            reverse('index'),
            {
                'nome': 'Cliente Fantasma',
                'telefone': '34999998888',
                'servicos': [999999],
                'data': data_futura.strftime('%Y-%m-%d'),
                'hora': '14:00',
                'barbeiro': self.barbeiro.id
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res_inexistente.status_code, 400)
        self.assertEqual(Agendamento.objects.count(), 0)

    def test_06_bloqueio_colisao_concorrencia(self):
        """Verifica que o backend impede colisões de horário para o mesmo barbeiro."""
        data_futura = datetime.now(SP_TZ).date() + timedelta(days=3)
        while data_futura.weekday() == 6:
            data_futura += timedelta(days=1)
        data_str = data_futura.strftime('%Y-%m-%d')

        # 1. Primeiro agendamento legítimo: 14:00 (duração 45 min -> vai até 14:45)
        res1 = self.client.post(
            reverse('index'),
            {
                'nome': 'Cliente Legítimo',
                'telefone': '34999998888',
                'servicos': [self.servico_corte.id],
                'data': data_str,
                'hora': '14:00',
                'barbeiro': self.barbeiro.id
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(res1.json()['sucesso'])
        self.assertEqual(Agendamento.objects.count(), 1)

        # 2. Segundo agendamento tentando o mesmo barbeiro às 14:15 (sobreposição/conflito)
        res2 = self.client.post(
            reverse('index'),
            {
                'nome': 'Cliente Conflitante',
                'telefone': '34988887777',
                'servicos': [self.servico_corte.id],
                'data': data_str,
                'hora': '14:15',
                'barbeiro': self.barbeiro.id
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res2.status_code, 400)
        self.assertFalse(res2.json()['sucesso'])
        self.assertIn('outro agendamento', res2.json()['mensagem'].lower())
        # Confirma que o segundo não foi salvo
        self.assertEqual(Agendamento.objects.count(), 1)

    def test_07_geracao_servidor_token_seguro(self):
        """
        Garante que o backend NÃO confia no token enviado pelo cliente,
        gerando um token criptográfico robusto e retornando o link correto.
        """
        data_futura = datetime.now(SP_TZ).date() + timedelta(days=4)
        while data_futura.weekday() == 6:
            data_futura += timedelta(days=1)

        token_forjado = 'meu-token-forjado-123'
        response = self.client.post(
            reverse('index'),
            {
                'nome': 'Cliente Token',
                'telefone': '34999998888',
                'servicos': [self.servico_corte.id],
                'data': data_futura.strftime('%Y-%m-%d'),
                'hora': '15:00',
                'barbeiro': self.barbeiro.id,
                'token': token_forjado
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['sucesso'])
        
        # Token gravado no banco NÃO pode ser o token forjado do cliente
        ag = Agendamento.objects.get(nome_cliente='Cliente Token')
        self.assertNotEqual(ag.token, token_forjado)
        self.assertGreaterEqual(len(ag.token), 32)
        self.assertIn(ag.token, data['link_cancelamento'])

    def test_08_protecao_csrf_e_post_exclusao_barbeiro(self):
        """
        Garante que a rota de exclusão de barbeiro:
        - Bloqueia usuários anônimos (302 login).
        - Rejeita requisições GET com 405 Method Not Allowed (impossibilitando ataques de CSRF via link/imagem).
        - Exige método POST autenticado.
        """
        # 1. Usuário anônimo tenta GET
        res_anon = self.client.get(reverse('excluir_barbeiro', args=[self.barbeiro.id]))
        self.assertEqual(res_anon.status_code, 302)
        self.assertIn('login', res_anon.url)

        # 2. Usuário autenticado tenta GET (DEVE SER REJEITADO COM 405)
        self.client.force_login(self.user)
        res_get = self.client.get(reverse('excluir_barbeiro', args=[self.barbeiro.id]))
        self.assertEqual(res_get.status_code, 405)
        self.assertTrue(Barbeiro.objects.filter(id=self.barbeiro.id).exists())

        # 3. Usuário autenticado via POST legítimo
        res_post = self.client.post(reverse('excluir_barbeiro', args=[self.barbeiro.id]))
        self.assertEqual(res_post.status_code, 302)
        self.assertFalse(Barbeiro.objects.filter(id=self.barbeiro.id).exists())

    def test_09_protecao_csrf_e_post_cancelar_agendamento(self):
        """
        Garante que o cancelamento de agendamento no painel pelo barbeiro:
        - Rejeita GET com 405 Method Not Allowed.
        - Exige autenticação e método POST.
        """
        ag = Agendamento.objects.create(
            nome_cliente='Teste Cancelar',
            telefone='34999998888',
            barbeiro=self.barbeiro,
            data=datetime.now(SP_TZ).date() + timedelta(days=2),
            hora=time(10, 0),
            duracao_minutos=45,
            token='seguro1234567890123456'
        )

        # Usuário autenticado tenta cancelar via GET (proibido)
        self.client.force_login(self.user)
        res_get = self.client.get(reverse('cancelar_agendamento', args=[ag.id]))
        self.assertEqual(res_get.status_code, 405)
        self.assertTrue(Agendamento.objects.filter(id=ag.id).exists())

        # Usuário autenticado via POST (permitido)
        res_post = self.client.post(reverse('cancelar_agendamento', args=[ag.id]))
        self.assertEqual(res_post.status_code, 302)
        self.assertFalse(Agendamento.objects.filter(id=ag.id).exists())

    def test_10_cancelamento_cliente_seguro(self):
        """
        Garante que o link de cancelamento público do cliente:
        - Rejeita tokens curtos, nulos ou forjados.
        - Não apaga o agendamento em requisições GET (ex: crawler do WhatsApp).
        - Só confirma a exclusão no POST.
        """
        ag = Agendamento.objects.create(
            nome_cliente='Cliente Cancelador',
            telefone='34999998888',
            barbeiro=self.barbeiro,
            data=datetime.now(SP_TZ).date() + timedelta(days=2),
            hora=time(11, 0),
            duracao_minutos=45,
            token='token_super_secreto_e_longo_12345'
        )

        # 1. Tentativa de cancelar com token inválido
        res_invalido = self.client.get(reverse('cancelar_cliente', args=['curto']))
        self.assertEqual(res_invalido.status_code, 302)

        # 2. Requisição GET com token legítimo (apenas exibe página de confirmação, NÃO apaga)
        res_get = self.client.get(reverse('cancelar_cliente', args=[ag.token]))
        self.assertEqual(res_get.status_code, 200)
        self.assertTrue(Agendamento.objects.filter(id=ag.id).exists())

        # 3. Requisição POST de confirmação com token legítimo (apaga)
        res_post = self.client.post(reverse('cancelar_cliente', args=[ag.token]))
        self.assertEqual(res_post.status_code, 302)
        self.assertFalse(Agendamento.objects.filter(id=ag.id).exists())


class SiteFullFeaturesTestCase(TestCase):
    """
    Testa rigorosamente TODAS as funcionalidades do site para garantir
    que nada quebrou após as alterações de segurança.
    """
    def setUp(self):
        self.client = Client()

        # Barbeiro titular
        self.barbeiro = Barbeiro.objects.create(
            nome='Henrique Barbeiro',
            cargo='Barbeiro Chefe',
            telefone='34991395770',
            horario_inicio=time(9, 0),
            horario_fim=time(20, 0),
            intervalo_inicio=time(12, 0),
            intervalo_fim=time(13, 0),
            dias_trabalho='0,1,2,3,4,5',
            ativo=True
        )

        # Serviços do salão
        self.servico_corte = Servico.objects.create(
            nome='Corte de Cabelo',
            preco=40.00,
            duracao_minutos=45
        )
        self.servico_barba = Servico.objects.create(
            nome='Barba Alinhada',
            preco=35.00,
            duracao_minutos=30
        )
        self.servico_sobrancelha = Servico.objects.create(
            nome='Sobrancelhas',
            preco=10.00,
            duracao_minutos=5
        )

        # Superusuário para acesso ao painel e admin
        self.admin_user = User.objects.create_superuser(
            username='admin_popeye',
            password='SenhaMasterForte123!',
            email='admin@popeye.com'
        )

    def test_01_pagina_inicial_carrega_com_sucesso(self):
        """Verifica se a página inicial (GET /) carrega com HTTP 200 e exibe serviços e barbeiros."""
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Barbearia Popeye')
        self.assertContains(response, self.barbeiro.nome)
        self.assertContains(response, self.servico_corte.nome)
        self.assertContains(response, self.servico_barba.nome)
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_02_endpoint_horarios_disponiveis_funciona(self):
        """Verifica se a busca de horários disponíveis (/horarios/) gera a grade corretamente."""
        # Escolhe uma data útil futura (terça ou quarta)
        data_futura = datetime.now(SP_TZ).date() + timedelta(days=2)
        while data_futura.weekday() == 6:
            data_futura += timedelta(days=1)
        data_str = data_futura.strftime('%Y-%m-%d')

        # 1. Busca horários para o barbeiro específico e serviço de corte
        response = self.client.get(reverse('horarios_disponiveis'), {
            'data': data_str,
            'barbeiro_id': self.barbeiro.id,
            'servicos[]': [self.servico_corte.id]
        })
        self.assertEqual(response.status_code, 200)
        horarios = response.json()
        self.assertIsInstance(horarios, list)
        self.assertGreater(len(horarios), 0)

        # O primeiro horário deve ser o início do expediente (09:00)
        self.assertIn('09:00', horarios)
        self.assertIn('09:15', horarios)

        # O horário das 12:00 e 12:30 (intervalo de almoço) NÃO deve estar disponível
        self.assertNotIn('12:00', horarios)
        self.assertNotIn('12:30', horarios)

        # O horário limite de 19:30 não deve caber um corte de 45 min se fecha às 20:00
        self.assertNotIn('19:30', horarios)

    def test_03_fluxo_agendamento_completo_com_sucesso(self):
        """Testa o fluxo completo de um cliente realizando agendamento legítimo."""
        data_futura = datetime.now(SP_TZ).date() + timedelta(days=3)
        while data_futura.weekday() == 6:
            data_futura += timedelta(days=1)
        data_str = data_futura.strftime('%Y-%m-%d')

        payload = {
            'nome': 'João Silva',
            'telefone': '(34) 99123-4567',
            'servicos': [self.servico_corte.id, self.servico_barba.id],
            'data': data_str,
            'hora': '10:00',
            'barbeiro': self.barbeiro.id
        }

        response = self.client.post(
            reverse('index'),
            payload,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['sucesso'])
        self.assertEqual(data['barbeiro_nome'], self.barbeiro.nome)
        # Corte + Barba = 60 minutos (regra especial de combo)
        self.assertEqual(data['duracao'], 60)
        self.assertTrue(data['link_cancelamento'].startswith('http'))

        # Confirma que o agendamento foi salvo no banco de dados com todos os dados
        ag = Agendamento.objects.filter(nome_cliente='João Silva').first()
        self.assertIsNotNone(ag)
        self.assertEqual(ag.telefone, '34991234567')
        self.assertEqual(ag.barbeiro, self.barbeiro)
        self.assertEqual(ag.hora, time(10, 0))
        self.assertEqual(ag.duracao_minutos, 60)
        self.assertEqual(ag.servicos.count(), 2)

    def test_04_fluxo_cancelamento_cliente_completo(self):
        """Testa a tela de confirmação e a ação de cancelamento do próprio cliente."""
        data_futura = datetime.now(SP_TZ).date() + timedelta(days=2)
        while data_futura.weekday() == 6:
            data_futura += timedelta(days=1)

        ag = Agendamento.objects.create(
            nome_cliente='Carlos Cliente',
            telefone='34988776655',
            barbeiro=self.barbeiro,
            data=data_futura,
            hora=time(14, 0),
            duracao_minutos=45,
            token='token_cliente_teste_123456789'
        )
        ag.servicos.add(self.servico_corte)

        # 1. Cliente acessa link de cancelamento recebido no WhatsApp (GET)
        url_cancelar = reverse('cancelar_cliente', args=[ag.token])
        res_view = self.client.get(url_cancelar)
        self.assertEqual(res_view.status_code, 200)
        self.assertContains(res_view, 'Carlos Cliente')
        self.assertContains(res_view, 'Sim, Confirmar Cancelamento')
        self.assertTrue(Agendamento.objects.filter(id=ag.id).exists())

        # 2. Cliente clica em confirmar (POST)
        res_confirm = self.client.post(url_cancelar)
        self.assertEqual(res_confirm.status_code, 302)
        self.assertRedirects(res_confirm, reverse('index'))
        self.assertFalse(Agendamento.objects.filter(id=ag.id).exists())

    def test_05_painel_barbeiro_completo_e_crud(self):
        """
        Testa todas as funcionalidades do Painel do Barbeiro (/painel/):
        - Acesso restrito a usuários logados.
        - Exibição de agendamentos e faturamento.
        - Adicionar novo barbeiro.
        - Editar barbeiro existente.
        - Cancelar agendamento via painel.
        - Excluir barbeiro via painel.
        """
        # 1. Não autenticado -> redireciona para login
        res_bloqueado = self.client.get(reverse('painel'))
        self.assertEqual(res_bloqueado.status_code, 302)

        # 2. Autentica o barbeiro admin
        self.client.force_login(self.admin_user)
        res_painel = self.client.get(reverse('painel'))
        self.assertEqual(res_painel.status_code, 200)
        self.assertContains(res_painel, self.barbeiro.nome)
        self.assertContains(res_painel, 'Painel do Barbeiro')

        # 3. Criar novo barbeiro via formulário do painel
        res_add = self.client.post(reverse('adicionar_barbeiro'), {
            'nome': 'Novo Barbeiro Júnior',
            'cargo': 'Barbeiro Assistente',
            'telefone': '34999991111',
            'horario_inicio': '10:00',
            'horario_fim': '19:00',
            'intervalo_inicio': '13:00',
            'intervalo_fim': '14:00'
        })
        self.assertEqual(res_add.status_code, 302)
        novo_barbeiro = Barbeiro.objects.filter(nome='Novo Barbeiro Júnior').first()
        self.assertIsNotNone(novo_barbeiro)
        self.assertEqual(novo_barbeiro.horario_inicio, time(10, 0))

        # 4. Editar barbeiro via modal do painel
        res_edit = self.client.post(reverse('editar_barbeiro', args=[novo_barbeiro.id]), {
            'nome': 'Barbeiro Júnior Promovido',
            'cargo': 'Barbeiro Especialista',
            'telefone': '34999992222',
            'horario_inicio': '09:00',
            'horario_fim': '18:00',
            'intervalo_inicio': '12:00',
            'intervalo_fim': '13:00',
            'ativo': 'on'
        })
        self.assertEqual(res_edit.status_code, 302)
        novo_barbeiro.refresh_from_db()
        self.assertEqual(novo_barbeiro.nome, 'Barbeiro Júnior Promovido')
        self.assertEqual(novo_barbeiro.cargo, 'Barbeiro Especialista')

        # 5. Criar agendamento e cancelar via botão do painel
        ag = Agendamento.objects.create(
            nome_cliente='Cliente Painel',
            telefone='34988887777',
            barbeiro=novo_barbeiro,
            data=datetime.now(SP_TZ).date() + timedelta(days=2),
            hora=time(11, 0),
            duracao_minutos=45,
            token='token_painel_123456789'
        )
        res_cancela_ag = self.client.post(reverse('cancelar_agendamento', args=[ag.id]))
        self.assertEqual(res_cancela_ag.status_code, 302)
        self.assertFalse(Agendamento.objects.filter(id=ag.id).exists())

        # 6. Excluir barbeiro via botão do painel
        res_del_barb = self.client.post(reverse('excluir_barbeiro', args=[novo_barbeiro.id]))
        self.assertEqual(res_del_barb.status_code, 302)
        self.assertFalse(Barbeiro.objects.filter(id=novo_barbeiro.id).exists())

    def test_06_django_admin_gerenciamento_completo(self):
        """Verifica se o Django Admin (/admin/) continua 100% acessível e funcional."""
        self.client.force_login(self.admin_user)

        # Página principal do admin
        res_admin = self.client.get('/admin/')
        self.assertEqual(res_admin.status_code, 200)

        # Lista de Barbeiros no admin
        res_barbeiros = self.client.get('/admin/agendamento/barbeiro/')
        self.assertEqual(res_barbeiros.status_code, 200)
        self.assertContains(res_barbeiros, self.barbeiro.nome)

        # Lista de Serviços no admin
        res_servicos = self.client.get('/admin/agendamento/servico/')
        self.assertEqual(res_servicos.status_code, 200)
        self.assertContains(res_servicos, self.servico_corte.nome)

        # Lista de Agendamentos no admin
        res_agendamentos = self.client.get('/admin/agendamento/agendamento/')
        self.assertEqual(res_agendamentos.status_code, 200)

        # Lista de Clientes no admin
        res_clientes = self.client.get('/admin/agendamento/cliente/')
        self.assertEqual(res_clientes.status_code, 200)


class ClienteManagementTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='barbeiro_gestor',
            password='SenhaSegura123!'
        )
        self.barbeiro = Barbeiro.objects.create(
            nome='Henrique Teste',
            cargo='Barbeiro Chefe',
            telefone='(34) 99999-1111',
            horario_inicio=time(9, 0),
            horario_fim=time(20, 0),
            intervalo_inicio=time(12, 0),
            intervalo_fim=time(13, 0),
            dias_trabalho='0,1,2,3,4,5',
            ativo=True
        )
        self.servico = Servico.objects.create(
            nome='Corte Tradicional',
            preco=45.00,
            duracao_minutos=45
        )
        self.amanha = (datetime.now(SP_TZ).date() + timedelta(days=2))
        while self.amanha.weekday() == 6:  # Pula domingo
            self.amanha += timedelta(days=1)
        self.amanha_str = self.amanha.strftime('%Y-%m-%d')

    def test_01_bloqueio_usuario_deslogado(self):
        """Endpoints de gestão manual exigem autenticação do barbeiro."""
        res_cad = self.client.post(reverse('cadastrar_cliente_manual'), {'nome': 'Fulano'})
        self.assertEqual(res_cad.status_code, 302)
        self.assertIn('/login/', res_cad.url)

        res_ag = self.client.post(reverse('agendar_cliente_manual'), {'cliente_id': 1})
        self.assertEqual(res_ag.status_code, 302)
        self.assertIn('/login/', res_ag.url)

    def test_02_cadastrar_cliente_manual_sucesso(self):
        """Barbeiro cadastra novo cliente com serviço opcional e cria agendamento."""
        self.client.force_login(self.user)
        res = self.client.post(
            reverse('cadastrar_cliente_manual'),
            {
                'nome': 'Marcos Vinicius',
                'telefone': '(34) 99888-7777',
                'data': self.amanha_str,
                'hora': '10:00',
                'servico': self.servico.id,
                'barbeiro': self.barbeiro.id
            }
        )
        self.assertEqual(res.status_code, 302)
        
        # Verifica se o cliente foi salvo no banco de dados
        cliente = Cliente.objects.filter(nome='Marcos Vinicius').first()
        self.assertIsNotNone(cliente)
        self.assertEqual(cliente.telefone, '(34) 99888-7777')

        # Verifica se o agendamento foi criado no banco
        ag = Agendamento.objects.filter(cliente=cliente, data=self.amanha, hora=time(10, 0)).first()
        self.assertIsNotNone(ag)
        self.assertEqual(ag.barbeiro, self.barbeiro)
        self.assertEqual(ag.duracao_minutos, 45)
        self.assertIn(self.servico, ag.servicos.all())

    def test_03_cadastrar_cliente_manual_sem_servico_opcional(self):
        """Barbeiro cadastra novo cliente sem selecionar serviço (serviço opcional)."""
        self.client.force_login(self.user)
        res = self.client.post(
            reverse('cadastrar_cliente_manual'),
            {
                'nome': 'João Sem Servico',
                'telefone': '34991112222',
                'data': self.amanha_str,
                'hora': '14:00',
                'servico': '',
                'barbeiro': self.barbeiro.id
            }
        )
        self.assertEqual(res.status_code, 302)
        cliente = Cliente.objects.filter(nome='João Sem Servico').first()
        self.assertIsNotNone(cliente)
        ag = Agendamento.objects.filter(cliente=cliente, data=self.amanha, hora=time(14, 0)).first()
        self.assertIsNotNone(ag)
        self.assertEqual(ag.duracao_minutos, 30)
        self.assertEqual(ag.servicos.count(), 0)

    def test_04_bloqueio_conflito_horario_novo_cliente(self):
        """Impede colisão de horário no cadastro de cliente manual."""
        self.client.force_login(self.user)
        # Cria primeiro agendamento às 10:00
        self.client.post(
            reverse('cadastrar_cliente_manual'),
            {
                'nome': 'Cliente 1',
                'telefone': '(34) 99111-0001',
                'data': self.amanha_str,
                'hora': '10:00',
                'servico': self.servico.id,
                'barbeiro': self.barbeiro.id
            }
        )
        # Tenta cadastrar segundo agendamento no mesmo horário para o mesmo barbeiro
        res2 = self.client.post(
            reverse('cadastrar_cliente_manual'),
            {
                'nome': 'Cliente 2',
                'telefone': '(34) 99111-0002',
                'data': self.amanha_str,
                'hora': '10:00',
                'servico': self.servico.id,
                'barbeiro': self.barbeiro.id
            }
        )
        self.assertEqual(res2.status_code, 302)
        # Segundo agendamento não deve ser criado
        self.assertFalse(Agendamento.objects.filter(nome_cliente='Cliente 2').exists())

    def test_05_agendar_cliente_existente_sucesso(self):
        """Barbeiro seleciona cliente já cadastrado e agenda horário."""
        self.client.force_login(self.user)
        cliente = Cliente.objects.create(
            nome='Lucas Oliveira',
            telefone='(34) 99777-6666'
        )
        res = self.client.post(
            reverse('agendar_cliente_manual'),
            {
                'cliente_id': cliente.id,
                'data': self.amanha_str,
                'hora': '16:00',
                'servico': self.servico.id,
                'barbeiro': self.barbeiro.id
            }
        )
        self.assertEqual(res.status_code, 302)
        ag = Agendamento.objects.filter(cliente=cliente, data=self.amanha, hora=time(16, 0)).first()
        self.assertIsNotNone(ag)
        self.assertEqual(ag.nome_cliente, 'Lucas Oliveira')
        self.assertEqual(ag.barbeiro, self.barbeiro)

    def test_06_painel_renderiza_botoes_e_clientes(self):
        """Verifica se o painel carrega com os novos botões e lista de clientes."""
        self.client.force_login(self.user)
        Cliente.objects.create(nome='Cliente Teste Visual', telefone='(34) 99000-0000')
        res = self.client.get(reverse('painel'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Cadastrar Novo Cliente')
        self.assertContains(res, 'Agendar Horário')
        self.assertContains(res, 'Cliente Teste Visual')
        # Verifica que o botão flutuante gcal-fab foi removido
        self.assertNotContains(res, 'class="gcal-fab"')


