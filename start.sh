#!/usr/bin/env bash
set -euo pipefail

VOL=/runpod-volume
# ИЗМЕНЕНИЕ: Базовый ComfyUI теперь находится в /ComfyUI (из темплейта)
# но мы создали симлинк /workspace/ComfyUI -> /ComfyUI для совместимости
APP=/workspace/ComfyUI
BASE_COMFYUI=/ComfyUI

echo "🚀 Optimized ComfyUI startup with volume mounting (template v8 compatible)..."

# 1. Проверяем наличие ComfyUI на volume и выбираем оптимальную стратегию
if [ -d "$VOL/ComfyUI" ] && [ -f "$VOL/ComfyUI/main.py" ]; then
    echo "✅ ComfyUI найден на volume, используем его напрямую"
    APP="$VOL/ComfyUI"
    
    # Обновляем симлинк для совместимости
    if [ ! -L "/workspace/ComfyUI" ] || [ "$(readlink /workspace/ComfyUI)" != "$VOL/ComfyUI" ]; then
        rm -rf /workspace/ComfyUI
        ln -sf "$VOL/ComfyUI" /workspace/ComfyUI
    fi
else
    echo "📦 Используем встроенный ComfyUI из темплейта: $BASE_COMFYUI -> $APP"
    
    # Проверяем что симлинк существует (создан в Dockerfile)
    if [ ! -L "$APP" ]; then
        echo "⚠️ Симлинк не найден, создаем: $BASE_COMFYUI -> $APP"
        mkdir -p /workspace
        ln -sf "$BASE_COMFYUI" "$APP"
    fi
    
    # 2. Быстрое монтирование моделей через bind mount
    echo "⏩ Fast mounting models..."
    if [ -d "$VOL/ComfyUI/models" ]; then
        # Сохраняем оригинальную папку моделей если нужно
        if [ -d "$BASE_COMFYUI/models" ] && [ ! -L "$BASE_COMFYUI/models" ]; then
            mv "$BASE_COMFYUI/models" "$BASE_COMFYUI/models.original" 2>/dev/null || true
        fi
        # Создаем прямой симлинк на модели с volume
        rm -rf "$BASE_COMFYUI/models"
        ln -sf "$VOL/ComfyUI/models" "$BASE_COMFYUI/models"
        echo "✅ Модели смонтированы: $VOL/ComfyUI/models -> $BASE_COMFYUI/models"
    fi

    # 3. Быстрое монтирование кастом нодов
    echo "⏩ Fast mounting custom nodes..."
    if [ -d "$VOL/ComfyUI/custom_nodes" ]; then
        # Сохраняем оригинальные кастом ноды если нужно  
        if [ -d "$BASE_COMFYUI/custom_nodes" ] && [ ! -L "$BASE_COMFYUI/custom_nodes" ]; then
            mv "$BASE_COMFYUI/custom_nodes" "$BASE_COMFYUI/custom_nodes.original" 2>/dev/null || true
        fi
        # Создаем прямой симлинк на кастом ноды с volume
        rm -rf "$BASE_COMFYUI/custom_nodes"
        ln -sf "$VOL/ComfyUI/custom_nodes" "$BASE_COMFYUI/custom_nodes"
        echo "✅ Кастом ноды смонтированы: $VOL/ComfyUI/custom_nodes -> $BASE_COMFYUI/custom_nodes"
    fi

    # 4. Монтируем дополнительные папки если они есть
    for dir in input output user temp; do
        if [ -d "$VOL/ComfyUI/$dir" ]; then
            rm -rf "$BASE_COMFYUI/$dir" 2>/dev/null || true
            ln -sf "$VOL/ComfyUI/$dir" "$BASE_COMFYUI/$dir"
            echo "✅ Папка $dir смонтирована"
        fi
    done
fi

# 4.5 Очистка мусорных директорий, мешающих импорту кастомных нод
if [ -d "$APP/custom_nodes" ]; then
    echo "🧹 Removing .ipynb_checkpoints from custom_nodes..."
    find "$APP/custom_nodes" -type d -name ".ipynb_checkpoints" -exec rm -rf {} + || true
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

echo "🔍 Дополнительная диагностика перед запуском:"
echo "📁 Проверяем права доступа к main.py:"
ls -la main.py
echo "📁 Проверяем models директорию:"
if [ -d "models" ]; then
    echo "✅ models найдена"
    ls -la models/ | head -5
else
    echo "⚠️ models директория не найдена"
fi
echo "📁 Проверяем custom_nodes директорию:"  
if [ -d "custom_nodes" ]; then
    echo "✅ custom_nodes найдена"
    ls -la custom_nodes/ | head -5
else
    echo "⚠️ custom_nodes директория не найдена"
fi
echo "🐍 Проверяем возможность импорта ComfyUI модулей:"
python -c "import sys; sys.path.append('.'); import folder_paths; print('✅ folder_paths импортирован')" 2>/dev/null || echo "⚠️ Проблемы с импортом folder_paths"

echo "🚀 Запускаем ComfyUI с логированием..."
# Создаем директорию для логов если её нет
mkdir -p /workspace/ComfyUI/user
# Запускаем ComfyUI с перенаправлением логов в оба места для совместимости
python -u main.py --verbose 2>&1 | tee /tmp/comfyui.log /workspace/ComfyUI/user/comfyui.log &
COMFY_PID=$!
echo "🆔 ComfyUI PID: $COMFY_PID"
echo "📝 Логи ComfyUI записываются в:"
echo "   - /tmp/comfyui.log"
echo "   - /workspace/ComfyUI/user/comfyui.log"

# 6. Не блокируем запуск воркера ожиданием порта — хендлер сам подождёт готовности API
sleep 2  # Даем время для начала записи в лог
echo "📋 Первые строки лога ComfyUI:"
head -20 /tmp/comfyui.log 2>/dev/null || echo "Лог пока пустой"
echo "════════════════════════════════════════"

# Информируем, что ожидание порта пропущено — хендлер выполнит check_server с ретраями
echo "✅ Skipping port wait; handler will wait for ComfyUI readiness."

# Если процесс внезапно упал сразу после старта — покажем логи, но не останавливаемся
if ! kill -0 $COMFY_PID 2>/dev/null; then
    echo "❌ ComfyUI process appears to have exited early"
    echo "📋 Последние логи процесса:"
    tail -50 /tmp/comfyui.log 2>/dev/null || echo "Логи недоступны"
fi

# 8. Стартуем serverless-handler (немедленно, без ожидания порта)
echo "⏩ Starting serverless handler..."
# ИЗМЕНЕНИЕ: handler.py теперь скопирован в корень (не в ComfyUI папку)
exec python -u /handler.py