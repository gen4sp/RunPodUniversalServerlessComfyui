# Используем новый базовый образ RunPod с PyTorch 2.8.0
FROM runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04

# Устанавливаем переменные окружения
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    # Основные утилиты
    build-essential \
    g++ \
    gcc \
    cmake \
    git \
    wget \
    curl \
    rsync \
    netcat-openbsd \
    unzip \
    # Библиотеки для обработки изображений и видео
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # FFmpeg для обработки видео/аудио
    ffmpeg \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    # Дополнительные зависимости
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Обновляем pip и базовые инструменты Python
RUN pip install --upgrade pip setuptools wheel

# Устанавливаем RunPod SDK и базовые зависимости
RUN pip install runpod>=1.7.0 requests websocket-client

# Клонируем ComfyUI в /workspace/ComfyUI (регистр важен!)
WORKDIR /workspace
RUN git clone https://github.com/comfyanonymous/ComfyUI.git ComfyUI

# Устанавливаем зависимости ComfyUI 
WORKDIR /workspace/ComfyUI
RUN pip install --no-cache-dir -r requirements.txt

# Дополнительные зависимости будут установлены из нашего requirements.txt ниже

# Копируем файлы проекта
COPY requirements.txt /tmp/custom_requirements.txt
COPY start.sh /start.sh
COPY debug-modules.sh /debug-modules.sh
COPY handler.py /handler.py
COPY snapshot.json /snapshot.json

# Делаем скрипты исполняемыми
RUN chmod +x /start.sh /debug-modules.sh

# Устанавливаем дополнительные зависимости из нашего requirements.txt
RUN if [ -s /tmp/custom_requirements.txt ]; then \
    echo "Устанавливаем дополнительные пакеты из requirements.txt..." && \
    pip install --no-cache-dir --timeout=300 -r /tmp/custom_requirements.txt || \
    (echo "ВНИМАНИЕ: Некоторые пакеты не удалось установить, устанавливаем по одному..." && \
     while IFS= read -r line; do \
       if [[ ! "$line" =~ ^[[:space:]]*# ]] && [[ -n "$line" ]]; then \
         echo "Устанавливаем: $line" && \
         pip install --no-cache-dir "$line" || echo "Не удалось установить: $line"; \
       fi; \
     done < /tmp/custom_requirements.txt); \
    fi

# Создаем необходимые директории и устанавливаем права
RUN mkdir -p /workspace /runpod-volume \
    && mkdir -p /workspace/ComfyUI/models /workspace/ComfyUI/custom_nodes /workspace/ComfyUI/input /workspace/ComfyUI/output /workspace/ComfyUI/temp \
    && chmod -R 755 /workspace/ComfyUI

# Очищаем кэш пакетов
RUN pip cache purge && \
    rm -rf /tmp/* /var/tmp/* /root/.cache

# Устанавливаем переменные окружения для ComfyUI
ENV COMFYUI_PATH=/workspace/ComfyUI \
    SKIP_MODEL_DOWNLOAD=1 \
    PYTHONUNBUFFERED=1 \
    CUDA_VISIBLE_DEVICES=0

# Создаем volume точки
VOLUME ["/runpod-volume"]

# Устанавливаем рабочую директорию
WORKDIR /

# Запускаем наш start.sh скрипт
CMD ["/start.sh"]