#!/usr/bin/env bash
set -euo pipefail

# Скрипт для тестирования нового Docker образа на базе runpod/pytorch:2.8.0

IMAGE_NAME="runpod-comfy-universal:new"
CONTAINER_NAME="test-runpod-comfy-new"

echo "🏗️ Сборка нового Docker образа..."
docker build -t "$IMAGE_NAME" .

echo "🧪 Тестирование образа..."
# Запускаем контейнер для проверки базовой функциональности
docker run --rm \
    --name "$CONTAINER_NAME-test" \
    --gpus all \
    -e SKIP_MODEL_DOWNLOAD=1 \
    "$IMAGE_NAME" \
    python -c "
import torch
import runpod
import sys
import os

print('🔍 Проверка основных зависимостей...')
print(f'Python версия: {sys.version}')
print(f'PyTorch версия: {torch.__version__}')
print(f'CUDA доступна: {torch.cuda.is_available()}')

if torch.cuda.is_available():
    print(f'CUDA версия: {torch.version.cuda}')
    print(f'GPU устройств: {torch.cuda.device_count()}')
    for i in range(torch.cuda.device_count()):
        print(f'GPU {i}: {torch.cuda.get_device_name(i)}')

# Проверяем что ComfyUI установлен в правильном месте
if os.path.exists('/workspace/ComfyUI/main.py'):
    print('✅ ComfyUI найден в /workspace/ComfyUI/')
else:
    print('❌ ComfyUI НЕ найден в /workspace/ComfyUI!')
    sys.exit(1)

# Проверяем handler.py
if os.path.exists('/handler.py'):
    print('✅ Handler найден')
else:
    print('❌ Handler НЕ найден!')
    sys.exit(1)

# Проверяем start.sh
if os.path.exists('/start.sh'):
    print('✅ Start script найден')
else:
    print('❌ Start script НЕ найден!')
    sys.exit(1)

print('🎉 Базовые проверки пройдены успешно!')
"

echo "✅ Тестирование завершено успешно!"
echo "📦 Образ '$IMAGE_NAME' готов к использованию"

# Показываем размер образа
echo "📊 Размер образа:"
docker images "$IMAGE_NAME" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

echo ""
echo "🚀 Для запуска контейнера используйте:"
echo "docker run --rm --gpus all -p 8188:8188 -v \$(pwd)/test-volume:/runpod-volume $IMAGE_NAME"