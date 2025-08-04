# 🚀 Быстрый старт - RunPod ComfyUI Universal

## Оптимизированный Docker образ для RunPod с PyTorch 2.8.0

### ⚡ Основные преимущества

-   **PyTorch 2.8.0** + **CUDA 12.8.1** - современное окружение
-   **Два режима работы** - максимальная производительность или стабильность
-   **Быстрое монтирование** - symlinks вместо копирования (1-3 сек vs 30-120 сек)
-   **Совместимость** - работает со всеми существующими workflow

---

## 🛠️ Сборка образа

```bash
git clone <your-repo>
cd runpodComfyUniversal
docker build -t runpod-comfy-universal:latest .
```

**Тестирование:**

```bash
./test-build-new.sh
```

---

## 🎯 Использование

### На RunPod Platform

1. **Загрузите образ** в RunPod Registry или Docker Hub
2. **Создайте Serverless Endpoint:**
    - Image: `your-registry/runpod-comfy-universal:latest`
    - Volume: подключите Network Volume с моделями
3. **Запустите** - система автоматически выберет оптимальный режим

### Локальное тестирование

```bash
# С GPU
docker run --rm --gpus all -p 8188:8188 \
  -v $(pwd)/test-volume:/runpod-volume \
  runpod-comfy-universal:latest

# Только CPU (для тестирования)
docker run --rm -p 8188:8188 \
  -v $(pwd)/test-volume:/runpod-volume \
  runpod-comfy-universal:latest
```

---

## 📁 Структура RunPod Volume

### Оптимальная структура:

```
/runpod-volume/ComfyUI/
├── main.py                 # (опционально) Ваша версия ComfyUI
├── models/                 # 🎯 Ваши модели
│   ├── checkpoints/
│   │   ├── sd_xl_base_1.0.safetensors
│   │   └── ...
│   ├── loras/
│   ├── vae/
│   └── controlnet/
├── custom_nodes/          # 🔧 Ваши кастом ноды
│   ├── ComfyUI-Manager/
│   ├── ComfyUI-Impact-Pack/
│   └── ...
├── input/                 # 📥 Входные файлы
├── output/                # 📤 Результаты
└── user/                  # ⚙️ Настройки
```

---

## 🔄 Режимы работы

### 🚀 Volume-First Mode (Рекомендуется)

**Когда активируется:** Есть `/runpod-volume/ComfyUI/main.py`

✅ **Преимущества:**

-   Мгновенный старт (<1 сек)
-   Нет дублирования данных
-   Все изменения сохраняются
-   Используется ваша версия ComfyUI

⚙️ **Как настроить:**

1. Скопируйте ComfyUI на volume
2. Добавьте модели и кастом ноды
3. Запустите - система автоматически выберет этот режим

### 🔧 Hybrid Mode (Стабильный)

**Когда активируется:** НЕТ `/runpod-volume/ComfyUI/main.py`

✅ **Преимущества:**

-   Гарантированные зависимости из образа
-   Быстрое монтирование (1-3 сек)
-   Стабильная работа
-   Автоматическое монтирование ресурсов

⚙️ **Как настроить:**

1. Создайте папки моделей и кастом нодов на volume
2. НЕ копируйте main.py
3. Система использует встроенный ComfyUI + ваши ресурсы

---

## 🔧 Настройка и диагностика

### Проверка режима работы

```bash
# В контейнере или логах
echo "Current mode: $APP"
# /runpod-volume/ComfyUI = Volume-First
# /workspace/ComfyUI = Hybrid
```

### Диагностика проблем

```bash
# Проверка модулей Python
./debug-modules.sh

# Проверка монтирования
ls -la /workspace/ComfyUI/models/
ls -la /workspace/ComfyUI/custom_nodes/

# Проверка объема данных
du -sh /workspace/ComfyUI/* 2>/dev/null
du -sh /runpod-volume/ComfyUI/* 2>/dev/null
```

### Логи запуска

Следите за сообщениями при старте:

-   `✅ ComfyUI найден на volume` = Volume-First Mode
-   `📦 Используем встроенный ComfyUI` = Hybrid Mode
-   `✅ Модели смонтированы` = Успешное монтирование

---

## 📊 Производительность

| Операция      | Старый rsync   | Новый symlink | Volume-First   |
| ------------- | -------------- | ------------- | -------------- |
| **Старт**     | 30-120 сек     | 1-3 сек       | <1 сек         |
| **Место**     | +2-10 GB       | +500 MB       | 0 дублирования |
| **Изменения** | Не сохраняются | Сохраняются   | Сохраняются    |

---

## ⚠️ Troubleshooting

### ComfyUI не стартует

```bash
# Проверяем путь
ls -la /workspace/ComfyUI/main.py
ls -la /runpod-volume/ComfyUI/main.py

# Проверяем зависимости
cd /workspace/ComfyUI && python -c "import torch; print(torch.__version__)"
```

### Модели не найдены

```bash
# Проверяем symlink
ls -la /workspace/ComfyUI/models
readlink /workspace/ComfyUI/models

# Проверяем содержимое
find /workspace/ComfyUI/models -name "*.safetensors" | head -5
```

### Кастом ноды не работают

```bash
# Проверяем symlink
ls -la /workspace/ComfyUI/custom_nodes
cd /workspace/ComfyUI && python -c "import sys; sys.path.append('custom_nodes'); import ComfyUI-Manager"
```

---

## 🔗 Полезные ссылки

-   [📚 Подробная документация](docs/new-pytorch-upgrade.md)
-   [🔧 Стратегия монтирования](docs/volume-mounting-strategy.md)
-   [🐛 Исправления сборки](docs/build-fixes.md)
-   [📖 Основной README](docs/readme.md)

---

## 💡 Советы по оптимизации

### Для максимальной производительности:

1. **Используйте Volume-First Mode** - скопируйте ComfyUI на volume
2. **NVMe Volume** - используйте быстрые диски в RunPod
3. **Предзагрузка** - держите часто используемые модели на volume

### Для максимальной стабильности:

1. **Используйте Hybrid Mode** - не копируйте main.py на volume
2. **Резервные копии** - регулярно бэкапьте volume
3. **Тестирование** - проверяйте кастом ноды перед продакшеном

### Для разработки:

1. **Volume-First** для быстрых итераций
2. **Локальное монтирование** для разработки нодов
3. **debug-modules.sh** для диагностики проблем
