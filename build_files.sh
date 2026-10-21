echo "Instalando dependencias do requirements.txt..."
python3 -m pip install -r requirements.txt --break-system-packages

echo "Coletando arquivos estaticos..."
python3 manage.py collectstatic --noinput