#!/bin/bash

# Скрипт для тестирования сборки Docker образа
# Использование: ./test-build.sh

set -e

echo "🐳 Проверяем доступность Docker..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker не установлен или недоступен"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "❌ Docker daemon не запущен. Запустите Docker Desktop или docker daemon"
    exit 1
fi

echo "✅ Docker доступен"

echo "🔨 Начинаем сборку образа..."
echo "Это может занять несколько минут..."

# Сборка с подробными логами
docker build --platform linux/amd64 -t runpod-comfy-universal:latest . \
    --no-cache \
    --progress=plain \
    2>&1 | tee build.log

if [ $? -eq 0 ]; then
    echo "✅ Сборка завершена успешно!"
    echo "📊 Размер образа:"
    docker images runpod-comfy-universal:latest
    
    echo "🧪 Тестируем запуск контейнера..."
    docker run --rm runpod-comfy-universal:latest echo "Контейнер работает!"
    
    echo "🎉 Все тесты прошли успешно!"
else
    echo "❌ Сборка завершилась с ошибкой"
    echo "📋 Логи сохранены в build.log"
    exit 1
fi