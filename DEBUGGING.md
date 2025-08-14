# 🔍 Отладка ошибок ComfyUI

## Быстрый старт

Если вы видите ошибки типа "Error handling request from 127.0.0.1" без деталей:

### 1. Включите детальное логирование

```bash
export RUNPOD_DEBUG=true
```

### 2. Следите за логами в реальном времени

```bash
# Все логи
./scripts/debug-logs.sh -f

# Только ошибки
./scripts/debug-logs.sh -f -e
```

### 3. Анализируйте ошибки

```bash
# Анализ с деталями
./scripts/analyze-errors.py -d

# Проверка статуса
./scripts/debug-logs.sh -s
```

## Расположение логов

-   **Основной лог ComfyUI:** `/tmp/comfyui.log`
-   **Дублированный лог:** `/workspace/ComfyUI/user/comfyui.log`
-   **Логи handler:** в stdout (видны в RunPod логах)

## Переменные окружения

| Переменная                     | Значение     | Описание                               |
| ------------------------------ | ------------ | -------------------------------------- |
| `RUNPOD_DEBUG`                 | `true/false` | Детальное логирование handler          |
| `WEBSOCKET_TRACE`              | `true/false` | Трассировка websocket (очень подробно) |
| `WEBSOCKET_RECONNECT_ATTEMPTS` | число        | Попытки переподключения                |
| `WEBSOCKET_RECONNECT_DELAY_S`  | число        | Задержка между попытками               |

## Типичные ошибки

### "Error handling request"

-   **Причина:** Проблемы с форматом входных данных
-   **Решение:** Включить `RUNPOD_DEBUG=true` и проверить входные данные

### WebSocket ошибки

-   **Причина:** ComfyUI процесс упал или завис
-   **Решение:** Проверить статус процесса и память

### Validation ошибки

-   **Причина:** Отсутствующие модели или неправильные параметры
-   **Решение:** Проверить доступные модели и workflow

## Команды для диагностики

```bash
# Быстрая проверка
./scripts/debug-logs.sh -s

# Последние ошибки
./scripts/debug-logs.sh -e -l 20

# Анализ паттернов ошибок
./scripts/analyze-errors.py -d

# Мониторинг в реальном времени
./scripts/debug-logs.sh -f
```
