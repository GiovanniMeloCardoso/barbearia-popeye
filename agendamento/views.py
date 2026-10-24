from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseNotAllowed
from django.urls import reverse
from django.db import transaction
from django.views.decorators.http import require_POST
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo
from django.contrib.auth.decorators import login_required
import secrets
import re
import json
from .models import Servico, Agendamento, Barbeiro

# Fuso horário oficial do negócio (São Paulo / Brasília)
SP_TZ = ZoneInfo('America/Sao_Paulo')

def calcular_duracao_servicos(servicos_objs):
    """
    Calcula a duração total em minutos com base nas regras do barbeiro:
    - CORTE: 45 minutos
    - BARBA: 30 minutos
    - CORTE E BARBA: 60 minutos (1 hora)
    - SOBRANCELHAS: 5 minutos
    - Demais serviços adicionais somam seu respectivo tempo
    """
    if not servicos_objs:
        return 45

    nomes = [s.nome.lower() for s in servicos_objs]
    tem_corte = any('corte' in n for n in nomes)
    tem_barba = any('barba' in n for n in nomes)
    tem_combo_corte_barba = any(('corte' in n and 'barba' in n) for n in nomes)

    if (tem_corte and tem_barba) or tem_combo_corte_barba:
        duracao = 60  # Regra especial: Corte e Barba = 1 hora
        outros = [s for s in servicos_objs if not ('corte' in s.nome.lower() or 'barba' in s.nome.lower())]
        duracao += sum(s.duracao_minutos for s in outros)
        return duracao
    elif tem_corte:
        duracao = 45  # Regra especial: Corte = 45 min
        outros = [s for s in servicos_objs if not 'corte' in s.nome.lower()]
        duracao += sum(s.duracao_minutos for s in outros)
        return duracao
    elif tem_barba:
        duracao = 30  # Regra especial: Barba = 30 min
        outros = [s for s in servicos_objs if not 'barba' in s.nome.lower()]
        duracao += sum(s.duracao_minutos for s in outros)
        return duracao
    else:
        duracao = sum(s.duracao_minutos for s in servicos_objs)
        return max(duracao, 5)

def verificar_conflito(data_obj, hora_inicio, duracao_minutos, barbeiro):
    """
    Verifica se o barbeiro tem colisão com algum agendamento existente
    ou se o horário está fora do expediente/intervalo de trabalho específico do barbeiro.
    """
    if not barbeiro:
        return True

    # 1. Checa se o barbeiro trabalha no dia da semana fornecido
    if hasattr(barbeiro, 'trabalha_no_dia') and not barbeiro.trabalha_no_dia(data_obj):
        return True

    # 2. Checa se o horário de atendimento cabe no expediente do barbeiro (e fora do intervalo)
    if hasattr(barbeiro, 'esta_no_horario_trabalho') and not barbeiro.esta_no_horario_trabalho(hora_inicio, duracao_minutos):
        return True

    # 3. Checa colisão com agendamentos existentes na agenda específica deste barbeiro
    inicio_dt = datetime.combine(data_obj, hora_inicio)
    fim_dt = inicio_dt + timedelta(minutes=duracao_minutos)

    agendamentos = Agendamento.objects.filter(data=data_obj, barbeiro=barbeiro)
    for ag in agendamentos:
        ag_inicio = datetime.combine(ag.data, ag.hora)
        ag_fim = ag_inicio + timedelta(minutes=ag.duracao_minutos)
        if max(inicio_dt, ag_inicio) < min(fim_dt, ag_fim):
            return True
    return False

def index(request):
    servicos = Servico.objects.all().order_by('ordem', 'id')
    barbeiros = Barbeiro.objects.filter(ativo=True).order_by('id')
    
    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('accept', '')
        
        def responder_erro(msg, status=400):
            if is_ajax:
                return JsonResponse({'sucesso': False, 'mensagem': msg}, status=status)
            messages.error(request, msg)
            return redirect('index')

        nome = request.POST.get('nome', '').strip()
        telefone = request.POST.get('telefone', '').strip()
        servicos_ids = request.POST.getlist('servicos')
        data_str = request.POST.get('data', '').strip()
        hora_str = request.POST.get('hora', '').strip()
        barbeiro_id = request.POST.get('barbeiro', '').strip()

        # 1. Validação do Nome do Cliente
        if not nome or len(nome) < 2 or len(nome) > 100:
            return responder_erro('Por favor, informe seu nome completo (entre 2 e 100 caracteres).')
        
        # 2. Validação do Telefone/WhatsApp do Cliente
        tel_digitos = re.sub(r'\D', '', telefone)
        if len(tel_digitos) < 10 or len(tel_digitos) > 13:
            return responder_erro('Por favor, informe um número de WhatsApp/telefone válido com DDD (ex: 34991395770).')

        # 3. Validação estrita do formato de Data e Hora
        try:
            data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return responder_erro('Data inválida. Use o formato AAAA-MM-DD.')

        try:
            hora_obj = datetime.strptime(hora_str, '%H:%M').time()
        except (ValueError, TypeError):
            return responder_erro('Horário inválido. Use o formato HH:MM.')

        # Fuso horário do estabelecimento
        agora_sp = datetime.now(SP_TZ)
        hoje_sp = agora_sp.date()

        # 4. Proibição de Agendamento em Datas Passadas
        if data_obj < hoje_sp:
            return responder_erro('Não é permitido agendar em datas que já passaram.')

        # 5. Proibição de Agendamento com mais de 60 dias de antecedência
        if data_obj > hoje_sp + timedelta(days=60):
            return responder_erro('Agendamentos só podem ser realizados com até 60 dias de antecedência.')

        # 6. Proibição de Domingos (Estabelecimento Fechado)
        if data_obj.weekday() == 6:
            return responder_erro('A barbearia não abre aos domingos. Por favor, selecione de segunda a sábado.')

        # 7. REGRA CRÍTICA DE SEGURANÇA: Se a data for HOJE, o horário NÃO pode estar no passado
        # Bloqueia qualquer horário anterior ao momento atual + 2 minutos de margem
        if data_obj == hoje_sp:
            agendamento_dt = datetime.combine(data_obj, hora_obj).replace(tzinfo=SP_TZ)
            if agendamento_dt <= agora_sp + timedelta(minutes=2):
                return responder_erro('Este horário já passou ou é muito próximo do horário atual. Por favor, escolha um horário futuro.')

        # 8. Validação dos Serviços
        if not servicos_ids:
            return responder_erro('Selecione ao menos um serviço para agendar.')

        valid_ids = []
        for s in servicos_ids:
            if str(s).isdigit():
                valid_ids.append(int(s))

        servicos_objs = list(Servico.objects.filter(id__in=valid_ids))
        if not servicos_objs:
            return responder_erro('Nenhum serviço válido foi selecionado.')

        duracao_minutos = calcular_duracao_servicos(servicos_objs)

        # 9. Verificação de Concorrência e Criação Atômica
        try:
            with transaction.atomic():
                barbeiro_escolhido = None
                barbeiros_ativos = list(Barbeiro.objects.filter(ativo=True).select_for_update())

                if not barbeiros_ativos:
                    return responder_erro('No momento não há barbeiros disponíveis para agendamento.')

                if barbeiro_id and barbeiro_id != 'qualquer':
                    if not str(barbeiro_id).isdigit():
                        return responder_erro('Barbeiro selecionado inválido.')

                    barbeiro_escolhido = Barbeiro.objects.filter(id=int(barbeiro_id), ativo=True).first()
                    if not barbeiro_escolhido:
                        return responder_erro('O barbeiro selecionado não está disponível.')

                    # Checa dia de trabalho do barbeiro
                    if not barbeiro_escolhido.trabalha_no_dia(data_obj):
                        return responder_erro(f'{barbeiro_escolhido.nome} não atende no dia da semana selecionado.')

                    # Checa limite de horário do barbeiro
                    h_ini = barbeiro_escolhido.horario_inicio or time(9, 0)
                    h_fim = barbeiro_escolhido.horario_fim or time(20, 0)
                    if hora_obj < h_ini:
                        return responder_erro(f'Horário anterior ao início do expediente de {barbeiro_escolhido.nome} ({h_ini.strftime("%H:%M")}).')

                    hora_fim_dt = datetime.combine(data_obj, hora_obj) + timedelta(minutes=duracao_minutos)
                    if hora_fim_dt > datetime.combine(data_obj, h_fim):
                        return responder_erro(f'Este atendimento ultrapassa o fim do expediente de {barbeiro_escolhido.nome} ({h_fim.strftime("%H:%M")}). Escolha um horário mais cedo.')

                    # Checa intervalo de almoço do barbeiro
                    if hasattr(barbeiro_escolhido, 'esta_no_horario_trabalho') and not barbeiro_escolhido.esta_no_horario_trabalho(hora_obj, duracao_minutos):
                        return responder_erro(f'O horário selecionado coincide com o intervalo de descanso de {barbeiro_escolhido.nome}.')

                    # Checa conflito de agendamento na agenda do barbeiro
                    if verificar_conflito(data_obj, hora_obj, duracao_minutos, barbeiro_escolhido):
                        return responder_erro(f'O barbeiro {barbeiro_escolhido.nome} já possui outro agendamento neste horário. Escolha outro horário.')
                else:
                    # Encontrar o primeiro barbeiro ativo livre na sua respectiva agenda
                    for b in barbeiros_ativos:
                        if not verificar_conflito(data_obj, hora_obj, duracao_minutos, b):
                            barbeiro_escolhido = b
                            break
                    
                    if not barbeiro_escolhido:
                        return responder_erro('Nenhum barbeiro disponível para a duração deste atendimento neste horário. Escolha outro horário.')

                # 10. Geração de token criptograficamente seguro no backend
                token_seguro = secrets.token_urlsafe(32)

                # Criar agendamento no banco de dados com lock e token seguro
                agendamento = Agendamento.objects.create(
                    nome_cliente=nome,
                    telefone=tel_digitos,
                    barbeiro=barbeiro_escolhido,
                    data=data_obj,
                    hora=hora_obj,
                    duracao_minutos=duracao_minutos,
                    token=token_seguro
                )
                agendamento.servicos.set(servicos_objs)

            tel_barbeiro = barbeiro_escolhido.telefone if (barbeiro_escolhido and barbeiro_escolhido.telefone) else '34991395770'
            link_cancelamento = request.build_absolute_uri(reverse('cancelar_cliente', args=[token_seguro]))

            if is_ajax:
                return JsonResponse({
                    'sucesso': True, 
                    'mensagem': 'Agendamento realizado com sucesso! Te esperamos.',
                    'barbeiro_nome': barbeiro_escolhido.nome if barbeiro_escolhido else 'Qualquer Barbeiro',
                    'barbeiro_telefone': tel_barbeiro,
                    'duracao': duracao_minutos,
                    'token': token_seguro,
                    'link_cancelamento': link_cancelamento
                })
            messages.success(request, 'Agendamento realizado com sucesso! Te esperamos.')
            return redirect('index')
        except Exception as e:
            if is_ajax:
                return JsonResponse({'sucesso': False, 'mensagem': f'Ocorreu um erro ao processar seu agendamento: {str(e)}'}, status=500)
            messages.error(request, 'Ocorreu um erro ao agendar. Tente novamente.')

    return render(request, 'agendamento/index.html', {
        'servicos': servicos,
        'barbeiros': barbeiros,
    })

def horarios_disponiveis(request):
    data_str = request.GET.get('data', '').strip()
    if not data_str: 
        return JsonResponse([], safe=False)
        
    try:
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return JsonResponse([], safe=False)

    agora_sp = datetime.now(SP_TZ)
    hoje_sp = agora_sp.date()
    if data_obj < hoje_sp or data_obj.weekday() == 6: 
        return JsonResponse([], safe=False)

    # Descobrir a duração solicitada
    servicos_ids = request.GET.getlist('servicos[]') or request.GET.getlist('servicos')
    duracao_param = request.GET.get('duracao')

    if servicos_ids:
        valid_ids = [int(s) for s in servicos_ids if str(s).isdigit()]
        servicos_objs = list(Servico.objects.filter(id__in=valid_ids))
        duracao_minutos = calcular_duracao_servicos(servicos_objs)
    elif duracao_param and str(duracao_param).isdigit():
        duracao_minutos = int(duracao_param)
    else:
        duracao_minutos = 45  # Padrão: 45 min (corte)

    # Identificar o barbeiro
    barbeiro_id = request.GET.get('barbeiro_id') or request.GET.get('barbeiro')
    barbeiros_ativos = list(Barbeiro.objects.filter(ativo=True))

    barbeiro_alvo = None
    if barbeiro_id and barbeiro_id != 'qualquer' and str(barbeiro_id).isdigit():
        barbeiro_alvo = Barbeiro.objects.filter(id=int(barbeiro_id), ativo=True).first()

    # Determinar horário de abertura e fechamento geral ou específico
    if barbeiro_alvo:
        hora_inicio_base = barbeiro_alvo.horario_inicio or time(9, 0)
        hora_fim_base = barbeiro_alvo.horario_fim or time(20, 0)
    elif barbeiros_ativos:
        hora_inicio_base = min(b.horario_inicio or time(9, 0) for b in barbeiros_ativos)
        hora_fim_base = max(b.horario_fim or time(20, 0) for b in barbeiros_ativos)
    else:
        hora_inicio_base = time(9, 0)
        hora_fim_base = time(20, 0)

    # Gerar grade com intervalos de 15 minutos + horários exatos de término de agendamentos
    candidatos_set = set()
    dt_atual = datetime.combine(data_obj, hora_inicio_base)
    dt_limite = datetime.combine(data_obj, hora_fim_base)

    while dt_atual < dt_limite:
        candidatos_set.add(dt_atual.time())
        dt_atual += timedelta(minutes=15)

    # Adicionar também horários que são términos de agendamentos existentes (para evitar buracos)
    filtro_ag = {'data': data_obj}
    if barbeiro_alvo:
        filtro_ag['barbeiro'] = barbeiro_alvo
    for ag in Agendamento.objects.filter(**filtro_ag):
        fim_ag = (datetime.combine(ag.data, ag.hora) + timedelta(minutes=ag.duracao_minutos)).time()
        if hora_inicio_base <= fim_ag < hora_fim_base:
            candidatos_set.add(fim_ag)

    horarios_ordenados = sorted(list(candidatos_set))
    horarios_validos = []

    for cand in horarios_ordenados:
        # Se for hoje, não pode estar no passado nem muito próximo do instante atual (buffer 2 min)
        cand_dt = datetime.combine(data_obj, cand).replace(tzinfo=SP_TZ)
        if data_obj == hoje_sp and cand_dt <= agora_sp + timedelta(minutes=2):
            continue

        if barbeiro_alvo:
            if not verificar_conflito(data_obj, cand, duracao_minutos, barbeiro_alvo):
                horarios_validos.append(cand.strftime('%H:%M'))
        else:
            # Sem preferência: livre se pelo menos UM barbeiro ativo puder atender sem conflito
            if not barbeiros_ativos:
                # Fallback sem barbeiros
                conflito_geral = False
                cand_inicio = datetime.combine(data_obj, cand)
                cand_fim = cand_inicio + timedelta(minutes=duracao_minutos)
                if cand_fim > dt_limite:
                    continue
                for ag in Agendamento.objects.filter(data=data_obj):
                    ag_inicio = datetime.combine(data_obj, ag.hora)
                    ag_fim = ag_inicio + timedelta(minutes=ag.duracao_minutos)
                    if max(cand_inicio, ag_inicio) < min(cand_fim, ag_fim):
                        conflito_geral = True
                        break
                if not conflito_geral:
                    horarios_validos.append(cand.strftime('%H:%M'))
            else:
                tem_barbeiro_livre = False
                for b in barbeiros_ativos:
                    if not verificar_conflito(data_obj, cand, duracao_minutos, b):
                        tem_barbeiro_livre = True
                        break
                if tem_barbeiro_livre:
                    horarios_validos.append(cand.strftime('%H:%M'))

    return JsonResponse(horarios_validos, safe=False)

@login_required
def painel_barbeiro(request):
    hoje = datetime.now(SP_TZ).date()
    barbeiros = Barbeiro.objects.all().order_by('id')
    barbeiro_filtro_id = request.GET.get('barbeiro_id') or request.GET.get('barbeiro')
    
    agendamentos_hoje_todos = Agendamento.objects.filter(data=hoje).select_related('barbeiro').prefetch_related('servicos').order_by('hora')
    agendamentos_futuros_todos = Agendamento.objects.filter(data__gt=hoje).select_related('barbeiro').prefetch_related('servicos').order_by('data', 'hora')
    
    barbeiro_ativo_filtro = None
    if barbeiro_filtro_id and barbeiro_filtro_id != 'todos':
        barbeiro_ativo_filtro = Barbeiro.objects.filter(id=barbeiro_filtro_id).first()
        if barbeiro_ativo_filtro:
            agendamentos_hoje = agendamentos_hoje_todos.filter(barbeiro=barbeiro_ativo_filtro)
            agendamentos_futuros = agendamentos_futuros_todos.filter(barbeiro=barbeiro_ativo_filtro)
        else:
            agendamentos_hoje = agendamentos_hoje_todos
            agendamentos_futuros = agendamentos_futuros_todos
    else:
        agendamentos_hoje = agendamentos_hoje_todos
        agendamentos_futuros = agendamentos_futuros_todos
        
    faturamento_hoje = sum(ag.total() for ag in agendamentos_hoje)
    
    # Contagens por barbeiro para os botões de filtro / abas
    contagem_por_barbeiro = {}
    for b in barbeiros:
        qtd_hoje = agendamentos_hoje_todos.filter(barbeiro=b).count()
        qtd_futuro = agendamentos_futuros_todos.filter(barbeiro=b).count()
        contagem_por_barbeiro[b.id] = {
            'hoje': qtd_hoje,
            'futuro': qtd_futuro,
            'total': qtd_hoje + qtd_futuro
        }

    # Dados completos estruturados para o Google Agenda (janela de -15 dias a +60 dias)
    agendamentos_cal = Agendamento.objects.filter(
        data__gte=hoje - timedelta(days=15),
        data__lte=hoje + timedelta(days=60)
    ).select_related('barbeiro').prefetch_related('servicos').order_by('data', 'hora')

    eventos_cal_lista = []
    for ag in agendamentos_cal:
        eventos_cal_lista.append({
            'id': ag.id,
            'cliente': ag.nome_cliente,
            'telefone': ag.telefone,
            'barbeiro_id': ag.barbeiro.id if ag.barbeiro else None,
            'barbeiro_nome': ag.barbeiro.nome if ag.barbeiro else 'Sem preferência',
            'data': ag.data.strftime('%Y-%m-%d'),
            'hora_inicio': ag.hora.strftime('%H:%M'),
            'hora_fim': ag.hora_fim.strftime('%H:%M'),
            'duracao': ag.duracao_minutos,
            'servicos': [s.nome for s in ag.servicos.all()],
            'total': float(ag.total()),
            'total_formatado': f"R$ {ag.total():.2f}".replace('.', ','),
            'cancel_url': reverse('cancelar_agendamento', args=[ag.id]),
        })

    barbeiros_cal_lista = []
    for b in barbeiros:
        barbeiros_cal_lista.append({
            'id': b.id,
            'nome': b.nome,
            'cargo': b.cargo,
            'telefone': b.telefone or '',
            'foto_url': b.foto_url,
            'horario_inicio': b.horario_inicio.strftime('%H:%M') if b.horario_inicio else '09:00',
            'horario_fim': b.horario_fim.strftime('%H:%M') if b.horario_fim else '20:00',
            'ativo': b.ativo,
        })

    agendamentos_calendario_json = json.dumps(eventos_cal_lista)
    barbeiros_calendario_json = json.dumps(barbeiros_cal_lista)
        
    return render(request, 'agendamento/painel.html', {
        'agendamentos_hoje': agendamentos_hoje,
        'agendamentos_futuros': agendamentos_futuros,
        'agendamentos_hoje_total_count': agendamentos_hoje_todos.count(),
        'agendamentos_futuros_total_count': agendamentos_futuros_todos.count(),
        'barbeiros': barbeiros,
        'barbeiro_ativo_filtro': barbeiro_ativo_filtro,
        'contagem_por_barbeiro': contagem_por_barbeiro,
        'faturamento_hoje': faturamento_hoje,
        'hoje': hoje,
        'agendamentos_calendario_json': agendamentos_calendario_json,
        'barbeiros_calendario_json': barbeiros_calendario_json,
    })

@login_required
def adicionar_barbeiro(request):
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        cargo = request.POST.get('cargo', 'Barbeiro Profissional').strip()
        telefone = request.POST.get('telefone', '').strip()
        horario_inicio_str = request.POST.get('horario_inicio', '09:00').strip()
        horario_fim_str = request.POST.get('horario_fim', '20:00').strip()
        intervalo_inicio_str = request.POST.get('intervalo_inicio', '').strip()
        intervalo_fim_str = request.POST.get('intervalo_fim', '').strip()
        foto = request.FILES.get('foto')

        if not nome:
            messages.error(request, 'O nome do barbeiro é obrigatório.')
            return redirect('painel')

        # Horários
        h_ini = datetime.strptime(horario_inicio_str, '%H:%M').time() if horario_inicio_str else time(9, 0)
        h_fim = datetime.strptime(horario_fim_str, '%H:%M').time() if horario_fim_str else time(20, 0)
        i_ini = datetime.strptime(intervalo_inicio_str, '%H:%M').time() if intervalo_inicio_str else None
        i_fim = datetime.strptime(intervalo_fim_str, '%H:%M').time() if intervalo_fim_str else None

        barbeiro = Barbeiro.objects.create(
            nome=nome,
            cargo=cargo if cargo else 'Barbeiro Profissional',
            telefone=telefone,
            horario_inicio=h_ini,
            horario_fim=h_fim,
            intervalo_inicio=i_ini,
            intervalo_fim=i_fim,
            foto=foto,
            ativo=True
        )
        messages.success(request, f'Barbeiro "{barbeiro.nome}" cadastrado com sucesso com agenda própria!')
    return redirect('painel')

@login_required
def editar_barbeiro(request, id):
    barbeiro = get_object_or_404(Barbeiro, id=id)
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        cargo = request.POST.get('cargo', '').strip()
        telefone = request.POST.get('telefone', '').strip()
        horario_inicio_str = request.POST.get('horario_inicio', '').strip()
        horario_fim_str = request.POST.get('horario_fim', '').strip()
        intervalo_inicio_str = request.POST.get('intervalo_inicio', '').strip()
        intervalo_fim_str = request.POST.get('intervalo_fim', '').strip()
        ativo = request.POST.get('ativo') == 'on' or request.POST.get('ativo') == 'true'
        foto = request.FILES.get('foto')

        if nome:
            barbeiro.nome = nome
        if cargo:
            barbeiro.cargo = cargo
        barbeiro.telefone = telefone
        barbeiro.ativo = ativo

        if horario_inicio_str:
            barbeiro.horario_inicio = datetime.strptime(horario_inicio_str, '%H:%M').time()
        if horario_fim_str:
            barbeiro.horario_fim = datetime.strptime(horario_fim_str, '%H:%M').time()
        
        if intervalo_inicio_str:
            barbeiro.intervalo_inicio = datetime.strptime(intervalo_inicio_str, '%H:%M').time()
        else:
            barbeiro.intervalo_inicio = None

        if intervalo_fim_str:
            barbeiro.intervalo_fim = datetime.strptime(intervalo_fim_str, '%H:%M').time()
        else:
            barbeiro.intervalo_fim = None

        if foto:
            barbeiro.foto = foto
        barbeiro.save()
        messages.success(request, f'Dados e agenda de "{barbeiro.nome}" atualizados com sucesso!')
    return redirect('painel')

@login_required
@require_POST
def excluir_barbeiro(request, id):
    barbeiro = get_object_or_404(Barbeiro, id=id)
    nome = barbeiro.nome
    barbeiro.delete()
    messages.success(request, f'Barbeiro "{nome}" foi removido da equipe com sucesso.')
    return redirect('painel')

@login_required
@require_POST
def cancelar_agendamento(request, id):
    agendamento = get_object_or_404(Agendamento, id=id)
    cliente = agendamento.nome_cliente
    agendamento.delete()
    messages.success(request, f'Agendamento de {cliente} cancelado com sucesso.')
    return redirect('painel')

def cancelar_cliente(request, token):
    # Proteção: tokens nulos, vazios ou curtos demais são rejeitados de imediato
    if not token or len(token.strip()) < 16:
        messages.error(request, 'Link de cancelamento inválido ou expirado.')
        return redirect('index')

    agendamento = Agendamento.objects.filter(token=token.strip()).first()
    if not agendamento:
        messages.error(request, 'Agendamento não encontrado ou já foi cancelado anteriormente.')
        return redirect('index')

    # Proteção essencial contra WhatsApp Crawler / Link Preview:
    # Robôs do WhatsApp/redes sociais fazem GET para gerar preview do link.
    # O cancelamento DEVE ser confirmado explicitamente via POST!
    if request.method == 'POST':
        cliente = agendamento.nome_cliente
        agendamento.delete()
        messages.success(request, f'Olá, {cliente}! Seu agendamento foi cancelado com sucesso e o horário foi liberado.')
        return redirect('index')

    return render(request, 'agendamento/cancelar_confirmacao.html', {
        'agendamento': agendamento
    })