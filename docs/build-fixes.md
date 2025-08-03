# Исправления проблем сборки Docker образа

## Проблемы и решения

### 1. Ошибка компиляции insightface

**Проблема**: `error: command 'x86_64-linux-gnu-g++' failed: No such file or directory`

**Решение**:

-   Добавлены build tools в Dockerfile
-   insightface временно отключен (закомментирован в requirements.txt)
-   Можно использовать альтернативы: `face-recognition` или предварительно скомпилированные wheels

### 2. Оптимизация установки пакетов

**Изменения в Dockerfile**:

-   Добавлена установка `build-essential`, `g++`, `gcc`, `cmake`, `git`
-   Обновление pip, setuptools, wheel перед установкой пакетов
-   Улучшенная обработка ошибок с fallback на поштучную установку
-   Использование `--no-cache-dir` для экономии места

**Изменения в requirements.txt**:

-   Замена `opencv-python` на `opencv-python-headless` (лучше для Docker)
-   Временное отключение проблемных пакетов
-   Добавление базовых пакетов для стабильности

### 3. Альтернативные подходы

**Для insightface**:

```bash
# Вариант 1: Установка из wheel (если доступен)
pip install insightface --find-links https://download.pytorch.org/whl/torch_stable.html

# Вариант 2: Использование альтернативы
pip install face-recognition

# Вариант 3: Установка в runtime (не в build time)
# Добавить в start.sh установку проблемных пакетов
```

**Для mediapipe**:

```bash
# Использовать конкретную версию, которая точно работает
pip install mediapipe==0.10.14
```

## Тестирование сборки

1. **Запустить полную сборку**:

    ```bash
    ./test-build.sh
    ```

2. **Тестирование с минимальными пакетами**:

    ```bash
    # Временно переименовать файлы
    mv requirements.txt requirements-full.txt
    mv requirements-minimal.txt requirements.txt

    # Собрать
    docker build -t test-minimal .

    # Вернуть обратно
    mv requirements.txt requirements-minimal.txt
    mv requirements-full.txt requirements.txt
    ```

3. **Отладка конкретного пакета**:

    ```bash
    # Запустить контейнер в интерактивном режиме
    docker run -it runpod/worker-comfyui:5.3.0-base bash

    # Внутри контейнера тестировать установку
    apt-get update && apt-get install -y build-essential g++
    pip install insightface
    ```

## Рекомендации

1. **Поэтапная установка**: Сначала соберите образ с минимальными пакетами, затем добавляйте проблемные
2. **Использование pre-compiled wheels**: Ищите готовые wheels на PyPI или других источниках
3. **Multi-stage build**: Рассмотрите использование multi-stage Docker build для оптимизации размера
4. **Кеширование слоев**: Устанавливайте стабильные пакеты в отдельных RUN командах для лучшего кеширования

## Логи и отладка

-   Логи сборки сохраняются в `build.log` при использовании `test-build.sh`
-   Для детальной отладки используйте `--progress=plain` и `--no-cache`
-   Проверяйте доступность пакетов на PyPI перед добавлением в requirements.txt
