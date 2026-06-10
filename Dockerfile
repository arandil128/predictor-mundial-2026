# Imagen base liviana con Python 3.13
FROM python:3.13-slim

# Buenas prácticas: sin .pyc, salida sin buffer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Instalar dependencias primero (mejor cacheo de capas)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la app
COPY . .

# Puerto que expone el contenedor (EasyPanel lo mapea)
EXPOSE 8000

# Arranque: respeta $PORT si la plataforma lo define, si no usa 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
