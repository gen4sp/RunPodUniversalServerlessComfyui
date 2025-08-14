# Диагностика и отладка ошибок ComfyUI

## Проблема

В логах ComfyUI часто появляются сообщения типа:

```
[2025-08-14 00:15:16.173] Error handling request from 127.0.0.1
```

Но детали ошибки не видны. Это происходит потому что:

1. **Неправильное расположение логов** - ComfyUI пишет в `/tmp/comfyui.log`, но пользователи смотрят в `/workspace/ComfyUI/user/comfyui.log`
2. **Недостаточное логирование** - обработчик ошибок не выводит детальную информацию
3. **Отсутствие контекста** - нет информации о входящих запросах

## Решение

### 1. Улучшенное логирование

Теперь логи ComfyUI записываются в оба места:

-   `/tmp/comfyui.log` (основной)
-   `/workspace/ComfyUI/user/comfyui.log` (для удобства пользователя)

### 2. Переменные окружения для отладки

```bash
# Включить детальное логирование
RUNPOD_DEBUG=true

# Включить трассировку websocket (очень подробно)
WEBSOCKET_TRACE=true

# Настройки переподключения websocket
WEBSOCKET_RECONNECT_ATTEMPTS=5
WEBSOCKET_RECONNECT_DELAY_S=3
```

### 3. Утилиты для диагностики

#### Скрипт мониторинга логов: `./scripts/debug-logs.sh`

```bash
# Следить за логами в реальном времени
./scripts/debug-logs.sh -f

# Показать только ошибки
./scripts/debug-logs.sh -e

# Последние 100 строк
./scripts/debug-logs.sh -l 100

# Проверить статус ComfyUI
./scripts/debug-logs.sh -s

# Показать все доступные логи
./scripts/debug-logs.sh --all-logs

# Очистить логи
./scripts/debug-logs.sh -c
```

#### Анализатор ошибок: `./scripts/analyze-errors.py`

```bash
# Анализ ошибок с деталями
./scripts/analyze-errors.py -d

# Проверка статуса системы
./scripts/analyze-errors.py -s

# Следить за ошибками в реальном времени
./scripts/analyze-errors.py -f -e
```

## Типы ошибок и их диагностика

### 1. "Error handling request from 127.0.0.1"

**Причины:**

-   Неправильный формат входных данных
-   Отсутствие обязательных полей в запросе
-   Проблемы с валидацией workflow

**Диагностика:**

```bash
# Проверить детали последних ошибок
./scripts/analyze-errors.py -d

# Включить детальное логирование
export RUNPOD_DEBUG=true
```

### 2. WebSocket ошибки

**Причины:**

-   ComfyUI процесс завис или упал
-   Проблемы с памятью (OOM)
-   Сетевые проблемы

**Диагностика:**

```bash
# Проверить статус ComfyUI
./scripts/debug-logs.sh -s

# Включить трассировку websocket
export WEBSOCKET_TRACE=true
```

### 3. Ошибки валидации workflow

**Причины:**

-   Отсутствующие модели
-   Неправильные параметры узлов
-   Несовместимые версии узлов

**Диагностика:**

```bash
# Проверить доступные модели
curl http://localhost:8188/object_info | jq '.CheckpointLoaderSimple.input.required.ckpt_name[0]'

# Анализ ошибок валидации
./scripts/analyze-errors.py -d | grep -i validation
```

## Новые возможности логирования

### В handler.py добавлено:

1. **Логирование входящих запросов**

    - ID задачи
    - Ключи входных данных
    - Время начала обработки
    - Краткое содержание запроса (без чувствительных данных)

2. **Детальное логирование ошибок**

    - Тип исключения
    - ID задачи и prompt_id
    - Полный traceback
    - Контекст запроса

3. **Отладочное логирование**
    - WebSocket сообщения (при `RUNPOD_DEBUG=true`)
    - Детали queue операций
    - Статистика выполнения

### В start.sh добавлено:

1. **Дублирование логов** в оба места
2. **Информация о местоположении логов**
3. **Улучшенная диагностика запуска**

## Рекомендации по использованию

### Для разработки:

```bash
export RUNPOD_DEBUG=true
export WEBSOCKET_TRACE=false  # включить только при проблемах с websocket
```

### Для production:

```bash
export RUNPOD_DEBUG=false
export WEBSOCKET_TRACE=false
```

### При проблемах:

1. **Включите детальное логирование:**

    ```bash
    export RUNPOD_DEBUG=true
    ```

2. **Следите за логами в реальном времени:**

    ```bash
    ./scripts/debug-logs.sh -f
    ```

3. **Анализируйте ошибки:**

    ```bash
    ./scripts/analyze-errors.py -d
    ```

4. **Проверьте статус системы:**
    ```bash
    ./scripts/debug-logs.sh -s
    ```

## Пример отладки

```bash
# 1. Проверить статус
./scripts/debug-logs.sh -s

# 2. Посмотреть последние ошибки
./scripts/analyze-errors.py -d

# 3. Включить детальное логирование
export RUNPOD_DEBUG=true

# 4. Следить за новыми ошибками
./scripts/debug-logs.sh -f -e

# 5. Отправить тестовый запрос и посмотреть что происходит
```

Теперь вместо неинформативного "Error handling request" вы будете видеть полную информацию об ошибке, включая тип исключения, traceback и контекст запроса.
