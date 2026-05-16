FROM python:3.12-slim

WORKDIR /app

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Переменные окружения
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Установка Python-зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY app/ ./app/

# Создаём директорию для БД
RUN mkdir -p /data

# Порт
EXPOSE 8000

# Запуск
CMD ["uvicorn", "app.app:app", "--host", "0.0.0.0", "--port", "8000"]