from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from datetime import datetime, timedelta, date
from django.contrib.auth.decorators import login_required
from .models import Servico, Agendamento

def index(request):
    servicos = Servico.objects.all()
    
    if request.method == 'POST':
        nome = request.POST.get('nome')
        telefone = request.POST.get('telefone')
        servicos_ids = request.POST.getlist('servicos')
        data = request.POST.get('data')
        hora = request.POST.get('hora')
        token = request.POST.get('token')
        
        try:
            data_obj = datetime.strptime(data, '%Y-%m-%d').date()
            hoje = date.today()
            
            if data_obj < hoje or data_obj.weekday() == 6:
                messages.error(request, 'Data inválida ou domingo.')
                return redirect('index')

            se_ocupado = Agendamento.objects.filter(data=data, hora=hora).exists()
            
            if se_ocupado:
                messages.error(request, 'Este horário acabou de ser reservado. Escolha outro.')
            else:
                agendamento = Agendamento.objects.create(
                    nome_cliente=nome,
                    telefone=telefone,
                    data=data,
                    hora=hora,
                    token=token
                )
                for s_id in servicos_ids:
                    agendamento.servicos.add(s_id)
                    
                messages.success(request, 'Agendamento realizado com sucesso! Te esperamos.')
            return redirect('index')
        except Exception as e:
            messages.error(request, 'Ocorreu um erro ao agendar. Tente novamente.')

    return render(request, 'agendamento/index.html', {'servicos': servicos})

def horarios_disponiveis(request):
    data_str = request.GET.get('data')
    if not data_str: return JsonResponse([])
        
    data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
    hoje = date.today()
    if data_obj < hoje or data_obj.weekday() == 6: return JsonResponse([])
    
    horarios_possiveis = []
    hora_atual = datetime.strptime('09:00', '%H:%M')
    hora_fim = datetime.strptime('20:00', '%H:%M')
    agora = datetime.now()
    
    while hora_atual <= hora_fim:
        if data_obj == hoje:
            if hora_atual.time() > agora.time(): horarios_possiveis.append(hora_atual.strftime('%H:%M'))
        else:
            horarios_possiveis.append(hora_atual.strftime('%H:%M'))
        hora_atual += timedelta(minutes=30)
        
    horarios_ocupados = [ag.hora.strftime('%H:%M') for ag in Agendamento.objects.filter(data=data_str)]
    return JsonResponse([h for h in horarios_possiveis if h not in horarios_ocupados], safe=False)

@login_required
def painel_barbeiro(request):
    hoje = date.today()
    agendamentos_hoje = Agendamento.objects.filter(data=hoje).order_by('hora')
    agendamentos_futuros = Agendamento.objects.filter(data__gt=hoje).order_by('data', 'hora')
    
    faturamento_hoje = sum(ag.total() for ag in agendamentos_hoje)
    
    return render(request, 'agendamento/painel.html', {
        'agendamentos_hoje': agendamentos_hoje,
        'agendamentos_futuros': agendamentos_futuros,
        'faturamento_hoje': faturamento_hoje,
        'hoje': hoje,
    })

@login_required
def cancelar_agendamento(request, id):
    Agendamento.objects.filter(id=id).delete()
    return redirect('painel')

def cancelar_cliente(request, token):
    agendamento = Agendamento.objects.filter(token=token).first()
    if agendamento:
        agendamento.delete()
        messages.success(request, 'Seu agendamento foi CANCELADO com sucesso. O horário foi liberado.')
    else:
        messages.error(request, 'Agendamento não encontrado ou já foi cancelado.')
    return redirect('index')