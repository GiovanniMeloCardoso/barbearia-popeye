import os
from django.db import models
from datetime import datetime, timedelta, date, time

def converter_imagem_para_base64(imagem_arquivo):
    """
    Converte um arquivo de imagem para Data URI Base64 otimizada (JPEG 360x360).
    Garante persistência permanente de fotos em ambientes com filesystem efêmero (como Render free tier).
    """
    try:
        from PIL import Image, ImageOps
        import io, base64

        if hasattr(imagem_arquivo, 'path') and not os.path.exists(imagem_arquivo.path):
            return None

        if hasattr(imagem_arquivo, 'seek'):
            imagem_arquivo.seek(0)
            img = Image.open(imagem_arquivo)
        elif hasattr(imagem_arquivo, 'file'):
            imagem_arquivo.file.seek(0)
            img = Image.open(imagem_arquivo.file)
        elif hasattr(imagem_arquivo, 'path'):
            img = Image.open(imagem_arquivo.path)
        else:
            img = Image.open(imagem_arquivo)

        img = ImageOps.exif_transpose(img)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        img.thumbnail((360, 360), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=85, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        if hasattr(imagem_arquivo, 'seek'):
            imagem_arquivo.seek(0)

        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return None

class Barbeiro(models.Model):
    nome = models.CharField(max_length=120)
    cargo = models.CharField(max_length=100, default='Barbeiro Profissional')
    foto = models.ImageField(upload_to='barbeiros/', null=True, blank=True)
    foto_base64 = models.TextField(null=True, blank=True, verbose_name="Foto em Base64 (Persistente no Banco)")
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

    def save(self, *args, **kwargs):
        if self.foto:
            # Se for novo upload ou ainda não tem base64 gerado
            if not self.foto_base64 or hasattr(self.foto, 'file'):
                b64 = converter_imagem_para_base64(self.foto)
                if b64:
                    self.foto_base64 = b64
        else:
            self.foto_base64 = None
        super().save(*args, **kwargs)

    @property
    def foto_url(self):
        if self.foto_base64:
            return self.foto_base64
        if self.foto:
            try:
                if hasattr(self.foto, 'path') and os.path.exists(self.foto.path):
                    return self.foto.url
            except Exception:
                pass
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