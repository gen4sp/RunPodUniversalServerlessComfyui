# Используем новый темплейт с предустановленным ComfyUI и моделями
FROM hearmeman/comfyui-wan-template:v8

# Устанавливаем переменные окружения
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Устанавливаем только недостающие системные зависимости
RUN apt-get update && apt-get install -y \
    # Только недостающие утилиты (большинство уже есть в базовом образе)
    rsync \
    netcat-openbsd \
    net-tools \
    iproute2 \
    unzip \
    # Дополнительные библиотеки для совместимости
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # FFmpeg dev пакеты (сам ffmpeg уже есть)
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    # Дополнительные image libs
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Создаем совместимость путей - ComfyUI в темплейте находится в /ComfyUI
# Создаем симлинк для совместимости с нашими скриптами
RUN mkdir -p /workspace && \
    ln -sf /ComfyUI /workspace/ComfyUI

# Копируем файлы проекта
COPY requirements.txt /tmp/custom_requirements.txt
COPY start.sh /start.sh
COPY debug-modules.sh /debug-modules.sh
COPY handler.py /handler.py
COPY snapshot.json /snapshot.json

# Делаем скрипты исполняемыми
RUN chmod +x /start.sh /debug-modules.sh

# Устанавливаем только дополнительные зависимости (большинство уже есть в базовом образе)
RUN if [ -s /tmp/custom_requirements.txt ]; then \
    echo "Устанавливаем дополнительные пакеты из requirements.txt..." && \
    # Сначала пытаемся установить все сразу \
    pip install --no-cache-dir --timeout=300 -r /tmp/custom_requirements.txt || \
    # Если не получилось, устанавливаем по одному \
    (echo "ВНИМАНИЕ: Некоторые пакеты не удалось установить, устанавливаем по одному..." && \
     while IFS= read -r line; do \
       if [[ ! "$line" =~ ^[[:space:]]*# ]] && [[ -n "$line" ]]; then \
         echo "Устанавливаем: $line" && \
         pip install --no-cache-dir "$line" || \
         # Специальная обработка для triton и sageattention \
         (if [[ "$line" =~ "triton" ]]; then \
           echo "Пробуем альтернативную установку triton..." && \
           pip install --no-cache-dir --pre triton || echo "Не удалось установить triton"; \
         elif [[ "$line" =~ "sageattention" ]]; then \
           echo "Пробуем установку sageattention без triton..." && \
           pip install --no-cache-dir --no-deps sageattention || echo "Не удалось установить sageattention"; \
         else \
           echo "Не удалось установить: $line"; \
         fi); \
       fi; \
     done < /tmp/custom_requirements.txt); \
    fi

# Создаем необходимые директории и устанавливаем права
RUN mkdir -p /runpod-volume

# Очищаем временные файлы
RUN rm -rf /tmp/* /var/tmp/* /root/.cache

# Устанавливаем переменные окружения для совместимости
ENV COMFYUI_PATH=/workspace/ComfyUI \
    SKIP_MODEL_DOWNLOAD=1 \
    PYTHONUNBUFFERED=1 \
    CUDA_VISIBLE_DEVICES=0

# Создаем volume точки
VOLUME ["/runpod-volume"]

# Устанавливаем рабочую директорию
WORKDIR /

# Запускаем наш start.sh скрипт (адаптированный под новый темплейт)
CMD ["/start.sh"]