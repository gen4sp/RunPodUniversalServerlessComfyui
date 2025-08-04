# ComfyUI Serverless Template для Runpod

---

docker build --platform linux/amd64 -t comfy-universal .
docker run --platform linux/amd64 -p 8188:8188 -v $(pwd)/test-volume:/runpod-volume -e SKIP_MODEL_DOWNLOAD=1 -e PYTHONUNBUFFERED=1 --name comfy-test comfy-universal

Готовый шаблон «fork-и-запусти» для **serverless-энпойнта ComfyUI** на Runpod с подключённым **runpod-volume**, **кастомными нодами**, авто-установкой всех зависимостей и минимальным временем холодного старта (≈ 35-45 с на A6000).

## Особенности

-   ✅ **Быстрый старт** - холодный старт ≈ 35-45 с на A6000
-   ✅ **Кастомные ноды** - автоматическая установка через snapshot.json
-   ✅ **Runpod Volume** - модели хранятся на persistent volume
-   ✅ **Оптимизированный образ** - базируется на официальном `runpod/worker-comfyui:5.3.0-base`
-   ✅ **Минимальный размер** - только необходимые файлы

## Структура проекта

```text
.
├── Dockerfile          # Docker образ на базе runpod/worker-comfyui
├── start.sh            # Bootstrap скрипт для синхронизации с volume
├── snapshot.json       # Конфигурация кастомных нод ComfyUI
├── requirements.txt    # Дополнительные Python зависимости
└── readme.md          # Эта документация
```

## Быстрый старт

### 1. Подготовка репозитория

1. **Fork** этого репозитория
2. Клонируйте форк локально
3. Настройте `snapshot.json` под ваши нужды (опционально)
4. Добавьте дополнительные зависимости в `requirements.txt` (опционально)
5. Запушьте изменения

### 2. Создание Runpod Volume

1. В Runpod перейдите в **Storage → Volumes**
2. Создайте новый volume (рекомендуется 50+ GB)
3. Загрузите ваши модели в структуру:
    ```text
    /runpod-volume/
    ├── models/
    │   ├── checkpoints/
    │   ├── vae/
    │   ├── controlnet/
    │   └── ...
    └── custom_nodes/  # (опционально, если нужна синхронизация)
    ```

### 3. Деплой Serverless Endpoint

1. В Runpod перейдите в **Serverless → Endpoints**
2. Нажмите **New Endpoint**
3. Выберите **GitHub** и укажите ваш fork
4. В настройках:
    - ✅ **Attach Volume** - выберите созданный volume, путь `/runpod-volume`
    - Выберите нужный GPU тип (A6000, L40S и т.д.)
    - Установите **Container Disk** (10-20 GB достаточно)
5. Нажмите **Deploy**

### 4. Проверка работы

После успешного деплоя (статус "Testing → Completed"):

```bash
curl -X GET https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/health
```

Должен вернуть: `{"status":"READY"}`

## Настройка кастомных нод

Отредактируйте `snapshot.json` для добавления нужных custom nodes:

```json
{
    "custom_nodes": {
        "ComfyUI-Manager": {
            "url": "https://github.com/ltdrdata/ComfyUI-Manager",
            "path": "/workspace/ComfyUI/custom_nodes/ComfyUI-Manager",
            "disabled": false
        },
        "ВАШ-КАСТОМНЫЙ-НОД": {
            "url": "https://github.com/user/custom-node",
            "path": "/workspace/ComfyUI/custom_nodes/custom-node",
            "disabled": false
        }
    },
    "python_packages": ["opencv-python", "mediapipe"]
}
```

## Переменные окружения

| Переменная                  | Описание                              | По умолчанию |
| --------------------------- | ------------------------------------- | ------------ |
| `SKIP_MODEL_DOWNLOAD`       | Отключает загрузку моделей при старте | `1`          |
| `PYTHONUNBUFFERED`          | Вывод Python в реальном времени       | `1`          |
| `HF_HUB_ENABLE_HF_TRANSFER` | Быстрая загрузка с HuggingFace        | `1`          |

## Использование API

Пример запроса к вашему endpoint:

```python
import requests
import json

endpoint_url = "https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/runsync"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}

payload = {
    "input": {
        "workflow": {
            # Ваш ComfyUI workflow JSON
        }
    }
}

response = requests.post(endpoint_url, headers=headers, json=payload)
result = response.json()
```

## Оптимизация времени старта

-   **Модели на volume**: Храните все модели на persistent volume, а не в образе
-   **Минимальный snapshot**: Включайте только необходимые custom nodes
-   **Лёгкий requirements.txt**: Избегайте тяжёлых зависимостей, если они не критичны
-   **Правильный GPU**: A6000 стартует быстрее L40S для большинства задач

## Устранение проблем

### Долгий старт (>2 мин)

-   Проверьте размер образа (должен быть <5GB)
-   Убедитесь, что модели на volume, а не в образе
-   Проверьте `SKIP_MODEL_DOWNLOAD=1`

### Ошибки custom nodes

-   Проверьте корректность URLs в `snapshot.json`
-   Убедитесь, что все зависимости указаны в `python_packages`
-   Проверьте логи билда образа

### Проблемы с volume

-   Убедитесь, что volume подключен к `/runpod-volume`
-   Проверьте структуру папок на volume
-   Права доступа должны позволять чтение/запись

## Полезные ссылки

-   [Официальный репозиторий runpod-workers/worker-comfyui](https://github.com/runpod-workers/worker-comfyui)
-   [Документация Runpod Serverless](https://docs.runpod.io/serverless/overview)
-   [ComfyUI Manager](https://github.com/ltdrdata/ComfyUI-Manager)

---

**Время холодного старта**: ≈ 35-45 с на A6000 | ≈ 50-60 с на L40S
