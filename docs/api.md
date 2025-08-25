# API Документация RunPod ComfyUI Handler

## Обзор

Данный сервис предоставляет API для выполнения ComfyUI workflow'ов в serverless среде RunPod. Handler принимает JSON-запросы с workflow'ами и медиафайлами, обрабатывает их через ComfyUI и возвращает результаты.

## Структура запроса

### Основная структура job объекта

```json
{
    "id": "unique-job-id",
    "input": {
        // Входные параметры (см. ниже)
    }
}
```

### Входные параметры (job.input)

#### Обязательные параметры

| Параметр   | Тип      | Описание                                                                                    |
| ---------- | -------- | ------------------------------------------------------------------------------------------- |
| `workflow` | `object` | ComfyUI workflow в JSON формате. Обязательный параметр для всех запросов кроме local режима |

#### Медиафайлы

| Параметр | Тип      | Описание                                                                    |
| -------- | -------- | --------------------------------------------------------------------------- |
| `images` | `array`  | Массив изображений для загрузки в ComfyUI                                   |
| `videos` | `array`  | Массив видеофайлов для загрузки в ComfyUI                                   |
| `files`  | `object` | Объект с произвольными файлами (ключ - имя файла, значение - base64 строка) |

##### Формат массива images

```json
{
    "images": [
        {
            "name": "input_image.png",
            "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..." // или просто base64 строка
        }
    ]
}
```

##### Формат массива videos

```json
{
    "videos": [
        {
            "name": "input_video.mp4",
            "video": "data:video/mp4;base64,AAAAIGZ0eXBpc29tAAACAGlzb21pc28y..." // или просто base64 строка
        }
    ]
}
```

##### Формат объекта files

```json
{
    "files": {
        "audio.wav": "UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=",
        "model.safetensors": "base64_encoded_model_data...",
        "config.json": "eyJhcmNoaXRlY3R1cmUiOiAiU0QxLjUifQ=="
    }
}
```

#### Параметры вывода

| Параметр        | Тип       | По умолчанию | Описание                                                                                                |
| --------------- | --------- | ------------ | ------------------------------------------------------------------------------------------------------- |
| `return_base64` | `boolean` | `false`      | Если `true`, возвращает изображения в base64 формате. Если `false`, загружает в bucket и возвращает URL |
| `path`          | `string`  | `""`         | Префикс пути для загрузки в bucket. Итоговый путь: `rp/{path}/filename`                                 |

#### Специальные режимы

| Параметр           | Тип       | По умолчанию  | Описание                                                                      |
| ------------------ | --------- | ------------- | ----------------------------------------------------------------------------- |
| `local`            | `boolean` | `false`       | Локальный тестовый режим - обходит ComfyUI и возвращает локальное изображение |
| `local_image_path` | `string`  | `"/girs.png"` | Путь к локальному изображению для тестового режима                            |

## Примеры использования

### 1. Базовый запрос с workflow

```json
{
    "id": "job-001",
    "input": {
        "workflow": {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "sd_xl_base_1.0.safetensors"
                }
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "a beautiful landscape",
                    "clip": ["1", 1]
                }
            }
            // ... остальная часть workflow
        }
    }
}
```

### 2. Запрос с изображениями

```json
{
    "id": "job-002",
    "input": {
        "workflow": {
            /* workflow */
        },
        "images": [
            {
                "name": "source.jpg",
                "image": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD..."
            }
        ]
    }
}
```

### 3. Запрос с произвольными файлами

```json
{
    "id": "job-003",
    "input": {
        "workflow": {
            /* workflow */
        },
        "files": {
            "input_audio.wav": "UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=",
            "reference_image.png": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        }
    }
}
```

### 4. Запрос с настройкой вывода

```json
{
    "id": "job-004",
    "input": {
        "workflow": {
            /* workflow */
        },
        "return_base64": true,
        "path": "my-project/generation-001"
    }
}
```

### 5. Локальный тестовый режим

```json
{
    "id": "job-local",
    "input": {
        "local": true,
        "local_image_path": "/workspace/test_image.png",
        "return_base64": false,
        "path": "test-outputs"
    }
}
```

## Структура ответа

### Успешный ответ

```json
{
    "images": [
        {
            "filename": "output_001.png",
            "type": "url", // или "base64"
            "data": "https://storage.googleapis.com/bucket/rp/path/output_001.png"
        }
    ],
    "errors": [] // Необязательное поле с предупреждениями
}
```

### Ответ с base64

```json
{
    "images": [
        {
            "filename": "output_001.png",
            "type": "base64",
            "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        }
    ]
}
```

### Успешный ответ без изображений

```json
{
    "status": "success_no_images",
    "images": []
}
```

### Ответ с ошибкой

```json
{
    "error": "Workflow validation failed",
    "details": [
        "Node 1 (validation): ckpt_name 'invalid_model.safetensors' not in list"
    ]
}
```

## Поддерживаемые типы файлов

### Изображения

-   `.png` - image/png
-   `.jpg`, `.jpeg` - image/jpeg
-   `.webp` - image/webp
-   `.bmp` - image/bmp
-   `.gif` - image/gif

### Видео

-   `.mp4`, `.m4v` - video/mp4
-   `.mov` - video/quicktime
-   `.webm` - video/webm
-   `.avi` - video/x-msvideo
-   `.mkv` - video/x-matroska

## Обработка файлов

### Загрузка в ComfyUI

1. **images** - загружаются через `/upload/image` endpoint
2. **videos** - загружаются через `/upload/image` endpoint (ComfyUI принимает любые файлы)
3. **files** - сохраняются в `ComfyUI/input/` директорию для доступа по имени файла

### Поддерживаемые директории для files

-   `/workspace/ComfyUI/input`
-   `/runpod-volume/ComfyUI/input`

## Переменные окружения

| Переменная                     | По умолчанию | Описание                                     |
| ------------------------------ | ------------ | -------------------------------------------- |
| `RUNPOD_DEBUG`                 | `false`      | Включает детальное логирование               |
| `LOCAL_MODE`                   | `false`      | Включает локальный тестовый режим            |
| `LOCAL_IMAGE_PATH`             | `/girs.png`  | Путь к изображению для локального режима     |
| `WEBSOCKET_RECONNECT_ATTEMPTS` | `5`          | Количество попыток переподключения WebSocket |
| `WEBSOCKET_RECONNECT_DELAY_S`  | `3`          | Задержка между попытками переподключения     |
| `WEBSOCKET_TRACE`              | `false`      | Включает трассировку WebSocket               |

## Конфигурация bucket'а

Для загрузки результатов в облачное хранилище используется файл конфигурации:

**Пути поиска:**

-   `/runpod-volume/keys/gc_hmac.json` (в worker)
-   `/keys/gc_hmac.json` (для локальных запусков)

**Формат файла:**

```json
{
    "endpoint_url": "https://storage.googleapis.com",
    "bucket": "your-bucket-name",
    "aws_access_key_id": "your-access-key",
    "aws_secret_access_key": "your-secret-key"
}
```

## Валидация входных данных

Handler выполняет следующие проверки:

1. **Обязательные поля:** `workflow` должен быть предоставлен (кроме local режима)
2. **Формат images:** массив объектов с полями `name` и `image`
3. **Формат videos:** массив объектов с полями `name` и `video`
4. **Формат files:** объект с строковыми ключами и значениями
5. **JSON валидация:** если входные данные переданы как строка, они парсятся как JSON

## Обработка ошибок

### Типы ошибок

1. **Валидация входных данных** - неправильный формат запроса
2. **ComfyUI недоступен** - сервер ComfyUI не отвечает
3. **Ошибки загрузки файлов** - проблемы с загрузкой медиафайлов
4. **Ошибки workflow** - валидация workflow'а не прошла
5. **WebSocket ошибки** - проблемы с соединением во время выполнения
6. **Ошибки загрузки в bucket** - проблемы с сохранением результатов

### Стратегии обработки

-   **WebSocket переподключение:** до 5 попыток с задержкой 3 секунды
-   **Проверка доступности ComfyUI:** до 500 попыток с интервалом 50ms
-   **Graceful degradation:** при ошибках загрузки в bucket возвращается base64

## Логирование

Handler предоставляет подробное логирование:

-   Время начала и окончания обработки
-   Детали входных параметров (без чувствительных данных)
-   Статус загрузки файлов
-   Прогресс выполнения workflow'а
-   Ошибки и предупреждения
-   WebSocket события (при включенном WEBSOCKET_TRACE)

## Производительность

### Рекомендации

1. **Размер файлов:** оптимальный размер изображений до 10MB
2. **Количество файлов:** рекомендуется до 10 файлов за запрос
3. **Timeout'ы:**
    - Загрузка изображений: 30 секунд
    - Загрузка видео: 120 секунд
    - WebSocket соединение: 10 секунд
    - Получение результатов: 60 секунд

### Мониторинг

Handler логирует время выполнения каждого запроса для анализа производительности.
