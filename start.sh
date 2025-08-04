#!/usr/bin/env bash
set -euo pipefail

VOL=/runpod-volume
APP=/workspace/ComfyUI

echo "🚀 Optimized ComfyUI startup with volume mounting..."

# 1. Проверяем наличие ComfyUI на volume и выбираем оптимальную стратегию
if [ -d "$VOL/ComfyUI" ] && [ -f "$VOL/ComfyUI/main.py" ]; then
    echo "✅ ComfyUI найден на volume, используем его напрямую"
    APP="$VOL/ComfyUI"
    
    # Создаем симлинк для совместимости
    if [ ! -L "/workspace/ComfyUI" ] || [ "$(readlink /workspace/ComfyUI)" != "$VOL/ComfyUI" ]; then
        rm -rf /workspace/ComfyUI
        ln -sf "$VOL/ComfyUI" /workspace/ComfyUI
    fi
else
    echo "📦 Используем встроенный ComfyUI из образа: $APP"
    
    # 2. Быстрое монтирование моделей через bind mount
    echo "⏩ Fast mounting models..."
    if [ -d "$VOL/ComfyUI/models" ]; then
        # Сохраняем оригинальную папку моделей если нужно
        if [ -d "$APP/models" ] && [ ! -L "$APP/models" ]; then
            mv "$APP/models" "$APP/models.original" 2>/dev/null || true
        fi
        # Создаем прямой симлинк на модели с volume
        rm -rf "$APP/models"
        ln -sf "$VOL/ComfyUI/models" "$APP/models"
        echo "✅ Модели смонтированы: $VOL/ComfyUI/models -> $APP/models"
    fi

    # 3. Быстрое монтирование кастом нодов
    echo "⏩ Fast mounting custom nodes..."
    if [ -d "$VOL/ComfyUI/custom_nodes" ]; then
        # Сохраняем оригинальные кастом ноды если нужно  
        if [ -d "$APP/custom_nodes" ] && [ ! -L "$APP/custom_nodes" ]; then
            mv "$APP/custom_nodes" "$APP/custom_nodes.original" 2>/dev/null || true
        fi
        # Создаем прямой симлинк на кастом ноды с volume
        rm -rf "$APP/custom_nodes"
        ln -sf "$VOL/ComfyUI/custom_nodes" "$APP/custom_nodes"
        echo "✅ Кастом ноды смонтированы: $VOL/ComfyUI/custom_nodes -> $APP/custom_nodes"
    fi

    # 4. Монтируем дополнительные папки если они есть
    for dir in input output user temp; do
        if [ -d "$VOL/ComfyUI/$dir" ]; then
            rm -rf "$APP/$dir" 2>/dev/null || true
            ln -sf "$VOL/ComfyUI/$dir" "$APP/$dir"
            echo "✅ Папка $dir смонтирована"
        fi
    done
fi

# Проверяем финальное состояние
echo "📁 Финальная проверка ComfyUI:"
echo "APP путь: $APP"
ls -la "$APP/" | head -10

echo "⏩ DEBUG"
./debug-modules.sh

# 5. Запускаем ComfyUI (без веб-интерфейса) в фоне
echo "⏩ Starting ComfyUI from: $APP"
cd "$APP"

# Проверяем наличие main.py
if [ ! -f "main.py" ]; then
    echo "❌ main.py не найден в $APP"
    echo "📁 Содержимое директории:"
    ls -la
    exit 1
fi

python -u main.py --dont-print-server &
COMFY_PID=$!
echo "🆔 ComfyUI PID: $COMFY_PID"

# 6. Ждём порт 8188 (макс. 60 с - увеличил время для первого запуска)
echo "⏩ Waiting for ComfyUI to start on port 8188..."
for i in {1..60}; do
  if nc -z localhost 8188; then
    echo "✅ ComfyUI is ready on port 8188"
    break
  fi
  if ! kill -0 $COMFY_PID 2>/dev/null; then
    echo "❌ ComfyUI process died"
    echo "📋 Последние логи процесса:"
    tail -20 /tmp/comfyui.log 2>/dev/null || echo "Логи недоступны"
    exit 1
  fi
  echo "⏳ Waiting... ($i/60)"
  sleep 1
done

# 7. Проверяем, что порт действительно открыт
if ! nc -z localhost 8188; then
    echo "❌ ComfyUI failed to start on port 8188 after 60 seconds"
    echo "🔍 Проверяем процесс ComfyUI:"
    ps aux | grep python || true
    echo "🔍 Проверяем сетевые соединения:"
    netstat -tlnp | grep 8188 || true
    exit 1
fi

echo "✅ ComfyUI started successfully!"

# 8. Стартуем serverless-handler
echo "⏩ Starting serverless handler..."
exec python -u /workspace/ComfyUI/handler.py