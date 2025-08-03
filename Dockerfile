FROM runpod/worker-comfyui:5.3.0-base

# 1) Устанавливаем build tools и необходимые утилиты
RUN apt-get update && apt-get install -y \
    build-essential \
    g++ \
    gcc \
    cmake \
    git \
    rsync \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# 2) Копируем snapshot и скрипт
COPY snapshot.json /snapshot.json
COPY start.sh /start.sh
RUN chmod +x /start.sh

# 3) Обновляем pip и устанавливаем базовые инструменты
RUN pip install --upgrade pip setuptools wheel

# 4) (опц.) ставим extra-deps с улучшенной обработкой ошибок
COPY requirements.txt /tmp/req.txt
RUN if [ -s /tmp/req.txt ]; then \
    echo "Устанавливаем пакеты из requirements.txt..." && \
    pip install --no-cache-dir --timeout=300 --verbose -r /tmp/req.txt && \
    echo "Все пакеты успешно установлены!" || \
    (echo "ВНИМАНИЕ: Некоторые пакеты не удалось установить, но продолжаем сборку..." && \
     echo "Попробуем установить пакеты по одному..." && \
     while IFS= read -r line; do \
       if [[ ! "$line" =~ ^[[:space:]]*# ]] && [[ -n "$line" ]]; then \
         echo "Устанавливаем: $line" && \
         pip install --no-cache-dir "$line" || echo "Не удалось установить: $line"; \
       fi; \
     done < /tmp/req.txt); \
    fi

# 5) Включаем быстрый старт
ENV SKIP_MODEL_DOWNLOAD=1 \
    PYTHONUNBUFFERED=1
    
VOLUME ["/runpod-volume"]

CMD ["/start.sh"]