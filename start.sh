#!/usr/bin/env bash
set -euo pipefail

VOL=/runpod-volume
APP=/workspace/comfyui

# Проверяем, что runpod-volume подмонтирован
if [ ! -d "$VOL" ]; then
    echo "❌ ОШИБКА: $VOL не найден! Убедитесь, что runpod-volume подключён к endpoint'у"
    exit 1
fi

# 1. Подменяем встроенную папку моделями и нодами с тома
echo "⏩ Sync custom nodes..."
mkdir -p "$APP/custom_nodes"
rsync -a --delete "$VOL/ComfyUI/custom_nodes/" "$APP/custom_nodes/" || true

echo "⏩ Mount models..."
mkdir -p "$APP/models"
ln -sf "$VOL/ComfyUI/models" "$APP/models/local"

# 2. Запускаем ComfyUI (без веб-интерфейса) в фоне
python -u "$APP/main.py" --dont-print-server &

# 3. Ждём порт 8188 (макс. 15 с)
for i in {1..15}; do
  nc -z localhost 8188 && break
  sleep 1
done

# 4. Стартуем serverless-handler
exec python -u /workspace/handler.py