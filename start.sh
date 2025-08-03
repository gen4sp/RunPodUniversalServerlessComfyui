#!/usr/bin/env bash
set -euo pipefail

VOL=/runpod-volume
APP=/workspace/comfyui

# 1. Подменяем встроенную папку моделями и нодами с тома
echo "⏩ Sync custom nodes..."
mkdir -p "$APP/custom_nodes"
rsync -a "$VOL/ComfyUI/custom_nodes/" "$APP/custom_nodes/" || true

echo "⏩ Mount models..."
mkdir -p "$APP/models"
if [ -d "$VOL/ComfyUI/models" ]; then
    rm -f "$APP/models/local"
    ln -sf "$VOL/ComfyUI/models" "$APP/models/local"
fi

# 3. Запускаем ComfyUI (без веб-интерфейса) в фоне
echo "⏩ Starting ComfyUI..."
cd "$APP"
python -u main.py --dont-print-server &
COMFY_PID=$!

# 4. Ждём порт 8188 (макс. 30 с)
echo "⏩ Waiting for ComfyUI to start..."
for i in {1..30}; do
  if nc -z localhost 8188; then
    echo "✅ ComfyUI is ready on port 8188"
    break
  fi
  if ! kill -0 $COMFY_PID 2>/dev/null; then
    echo "❌ ComfyUI process died"
    exit 1
  fi
  echo "⏳ Waiting... ($i/30)"
  sleep 1
done

# 5. Проверяем, что порт действительно открыт
if ! nc -z localhost 8188; then
    echo "❌ ComfyUI failed to start on port 8188"
    exit 1
fi

# 6. Стартуем serverless-handler
echo "⏩ Starting serverless handler..."
exec python -u /workspace/handler.py