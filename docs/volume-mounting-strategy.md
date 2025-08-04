# Стратегия монтирования Volume для оптимальной производительности

## Обзор

Новая система оптимизирована для максимальной производительности при работе с RunPod volume, где уже может быть установлен ComfyUI с моделями и кастом нодами.

## Архитектура

### Два режима работы

#### 1. Volume-First Mode (Приоритет volume)

**Когда:** ComfyUI уже установлен на `/runpod-volume/ComfyUI/`
**Действие:** Используется ComfyUI с volume напрямую

```bash
APP=/runpod-volume/ComfyUI
ln -sf /runpod-volume/ComfyUI /workspace/ComfyUI  # Совместимость
```

**Преимущества:**

-   ⚡ Мгновенный старт без копирования
-   💾 Нет дублирования данных
-   🔄 Все изменения сохраняются на volume
-   📦 Используются кастом ноды и модели с volume

#### 2. Hybrid Mode (Гибридный режим)

**Когда:** ComfyUI НЕ найден на volume
**Действие:** Используется встроенный ComfyUI с монтированием ресурсов

```bash
APP=/workspace/ComfyUI  # Встроенный
# Быстрое монтирование через symlinks:
ln -sf /runpod-volume/ComfyUI/models /workspace/ComfyUI/models
ln -sf /runpod-volume/ComfyUI/custom_nodes /workspace/ComfyUI/custom_nodes
ln -sf /runpod-volume/ComfyUI/input /workspace/ComfyUI/input
ln -sf /runpod-volume/ComfyUI/output /workspace/ComfyUI/output
```

**Преимущества:**

-   🛡️ Гарантированные зависимости из образа
-   ⚡ Быстрое монтирование через symlinks (не копирование!)
-   💾 Модели и кастом ноды остаются на volume
-   🔄 Персистентные данные

### Структура файлов

#### В образе Docker:

```
/workspace/ComfyUI/          # Установленный ComfyUI с зависимостями
├── main.py
├── requirements.txt
├── comfy/
├── models/                  # Может быть заменен symlink'ом
├── custom_nodes/           # Может быть заменен symlink'ом
└── ...
```

#### На RunPod Volume:

```
/runpod-volume/ComfyUI/     # Пользовательские данные
├── main.py                 # (опционально) Пользовательская версия
├── models/                 # Модели пользователя
│   ├── checkpoints/
│   ├── loras/
│   ├── vae/
│   └── ...
├── custom_nodes/          # Кастом ноды пользователя
│   ├── ComfyUI-Manager/
│   └── ...
├── input/                 # Входные файлы
├── output/                # Выходные файлы
└── user/                  # Пользовательские настройки
```

## Алгоритм выбора режима

```bash
if [ -d "$VOL/ComfyUI" ] && [ -f "$VOL/ComfyUI/main.py" ]; then
    # Volume-First Mode
    APP="$VOL/ComfyUI"
    echo "✅ Используем ComfyUI с volume"
else
    # Hybrid Mode
    APP="/workspace/ComfyUI"
    echo "📦 Используем встроенный ComfyUI + монтирование"

    # Быстрое монтирование через symlinks
    for dir in models custom_nodes input output user temp; do
        if [ -d "$VOL/ComfyUI/$dir" ]; then
            rm -rf "$APP/$dir"
            ln -sf "$VOL/ComfyUI/$dir" "$APP/$dir"
        fi
    done
fi
```

## Производительность

### Время старта

| Метод                    | Время старта | Использование места |
| ------------------------ | ------------ | ------------------- |
| **rsync копирование**    | 30-120 сек   | Дублирование данных |
| **symlink монтирование** | 1-3 сек      | Без дублирования    |
| **Volume-first**         | <1 сек       | Нет копирования     |

### Использование дискового пространства

-   **Volume-First:** 0 дублирования
-   **Hybrid с symlinks:** ~500MB (только ComfyUI core)
-   **Старый rsync:** 2-10GB дублирования

## Безопасность

### Сохранение оригинальных данных

```bash
# Перед заменой сохраняем оригинал
if [ -d "$APP/models" ] && [ ! -L "$APP/models" ]; then
    mv "$APP/models" "$APP/models.original"
fi
```

### Проверки целостности

```bash
# Проверяем что main.py существует
if [ ! -f "$APP/main.py" ]; then
    echo "❌ ComfyUI не найден в $APP"
    exit 1
fi
```

## Отладка

### Проверка режима работы

```bash
echo "Текущий режим: $APP"
if [ "$APP" = "/runpod-volume/ComfyUI" ]; then
    echo "🟢 Volume-First Mode"
else
    echo "🟡 Hybrid Mode"
fi
```

### Проверка symlinks

```bash
for dir in models custom_nodes input output; do
    if [ -L "$APP/$dir" ]; then
        echo "📁 $dir -> $(readlink $APP/$dir)"
    fi
done
```

### Диагностика проблем

```bash
# Размеры директорий
du -sh /workspace/ComfyUI/* 2>/dev/null || true
du -sh /runpod-volume/ComfyUI/* 2>/dev/null || true

# Проверка доступности файлов
ls -la /workspace/ComfyUI/main.py
ls -la /runpod-volume/ComfyUI/main.py 2>/dev/null || echo "Volume ComfyUI not present"
```

## Рекомендации

### Для максимальной производительности

1. Держите ComfyUI на volume для Volume-First режима
2. Используйте быстрые NVMe volumes в RunPod
3. Регулярно очищайте временные файлы

### Для максимальной стабильности

1. Используйте встроенный ComfyUI (Hybrid режим)
2. Регулярно делайте backup volume
3. Тестируйте кастом ноды перед продакшеном

### Для разработки

1. Используйте Volume-First для быстрых итераций
2. Монтируйте локальную папку для разработки кастом нодов
3. Используйте debug-modules.sh для диагностики

## Troubleshooting

### Проблема: ComfyUI не стартует

```bash
# Проверяем режим
echo "Current APP: $APP"
ls -la "$APP/main.py"

# Проверяем зависимости
cd "$APP" && python -c "import torch; print(torch.__version__)"
```

### Проблема: Модели не найдены

```bash
# Проверяем symlink моделей
ls -la "$APP/models"
find "$APP/models" -name "*.safetensors" | head -5
```

### Проблема: Кастом ноды не работают

```bash
# Проверяем symlink кастом нодов
ls -la "$APP/custom_nodes"
cd "$APP" && python -c "import sys; print(sys.path)"
```
