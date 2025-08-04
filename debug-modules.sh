#!/bin/bash

echo "🔍 ДИАГНОСТИКА PYTHON МОДУЛЕЙ ДЛЯ COMFYUI"
echo "=========================================="
echo ""

# Функция для проверки модуля Python
check_module() {
    local module_name=$1
    local import_name=$2
    
    if [ -z "$import_name" ]; then
        import_name=$module_name
    fi
    
    echo -n "📦 Проверяем $module_name ($import_name)... "
    
    python3 -c "
import sys
try:
    import $import_name
    if hasattr($import_name, '__version__'):
        print(f'✅ OK - версия: {$import_name.__version__}')
    else:
        print('✅ OK - версия не определена')
except ImportError as e:
    print(f'❌ ОТСУТСТВУЕТ: {e}')
except Exception as e:
    print(f'⚠️  ОШИБКА: {e}')
    " 2>/dev/null || echo "❌ КРИТИЧЕСКАЯ ОШИБКА при импорте"
}

# Функция для установки модуля
install_module() {
    local module_name=$1
    echo "🔧 Попытка установки $module_name..."
    pip3 install "$module_name" --user --quiet
    if [ $? -eq 0 ]; then
        echo "✅ $module_name установлен успешно"
    else
        echo "❌ Не удалось установить $module_name"
    fi
}

echo "1️⃣ ПРОВЕРКА ОСНОВНЫХ ПРОБЛЕМНЫХ МОДУЛЕЙ"
echo "----------------------------------------"

# Проверяем основные проблемные модули
check_module "opencv-python-headless" "cv2"
check_module "PyWavelets" "pywt" 
check_module "diffusers" "diffusers"
check_module "transformers" "transformers"
check_module "accelerate" "accelerate"

echo ""
echo "2️⃣ ПРОВЕРКА ДОПОЛНИТЕЛЬНЫХ МОДУЛЕЙ ИЗ REQUIREMENTS"
echo "------------------------------------------------"

# Другие модули из requirements.txt
check_module "pillow" "PIL"
check_module "numpy" "numpy"
check_module "mediapipe" "mediapipe"
check_module "onnxruntime-gpu" "onnxruntime"
check_module "scikit-image" "skimage"
check_module "torchvision" "torchvision"
check_module "requests" "requests"
check_module "tqdm" "tqdm"
check_module "imageio-ffmpeg" "imageio_ffmpeg"
check_module "setuptools" "setuptools"
check_module "wheel" "wheel"
check_module "matplotlib-inline" "matplotlib_inline"
check_module "ipython" "IPython"
check_module "gguf" "gguf"
check_module "sageattention" "sageattention"

echo ""
echo "3️⃣ ПРОВЕРКА СИСТЕМНОЙ ИНФОРМАЦИИ"
echo "--------------------------------"

echo "🐍 Python версия:"
python3 --version

echo ""
echo "📂 Python путь:"
python3 -c "import sys; print('\\n'.join(sys.path))"

echo ""
echo "🏠 Pip версия:"
pip3 --version

echo ""
echo "📍 Pip установочная директория:"
python3 -c "import site; print('User site:', site.getusersitepackages())"

echo ""
echo "4️⃣ АНАЛИЗ REQUIREMENTS.TXT"
echo "-------------------------"

if [ -f "requirements.txt" ]; then
    echo "📋 Найден requirements.txt, анализируем..."
    echo ""
    
    # Читаем requirements.txt и проверяем каждый пакет
    while IFS= read -r line; do
        # Пропускаем комментарии и пустые строки
        if [[ ! "$line" =~ ^[[:space:]]*# ]] && [[ -n "$(echo "$line" | tr -d '[:space:]')" ]]; then
            # Извлекаем имя пакета (до >=, ==, и т.д.)
            package_name=$(echo "$line" | sed 's/[><=!].*//' | tr -d '[:space:]')
            if [ -n "$package_name" ]; then
                echo "📦 Из requirements: $package_name"
                pip3 show "$package_name" --quiet > /dev/null 2>&1
                if [ $? -eq 0 ]; then
                    version=$(pip3 show "$package_name" 2>/dev/null | grep "Version:" | cut -d' ' -f2)
                    echo "   ✅ Установлен: $version"
                else
                    echo "   ❌ НЕ УСТАНОВЛЕН"
                fi
            fi
        fi
    done < requirements.txt
else
    echo "❌ Файл requirements.txt не найден"
fi

echo ""
echo "5️⃣ РЕКОМЕНДАЦИИ ПО ИСПРАВЛЕНИЮ"
echo "------------------------------"

missing_critical=()

# Проверяем критически важные модули
python3 -c "import cv2" 2>/dev/null || missing_critical+=("opencv-python-headless")
python3 -c "import pywt" 2>/dev/null || missing_critical+=("PyWavelets")
python3 -c "import diffusers" 2>/dev/null || missing_critical+=("diffusers")
python3 -c "import sageattention" 2>/dev/null || missing_critical+=("sageattention")

if [ ${#missing_critical[@]} -gt 0 ]; then
    echo "🚨 КРИТИЧЕСКИ ВАЖНЫЕ ОТСУТСТВУЮЩИЕ МОДУЛИ:"
    for module in "${missing_critical[@]}"; do
        echo "   - $module"
    done
    echo ""
    echo "💡 Для быстрого исправления выполните:"
    echo "   pip3 install ${missing_critical[*]}"
    echo ""
    
    read -p "🤖 Хотите автоматически установить отсутствующие модули? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🔧 Устанавливаем отсутствующие модули..."
        for module in "${missing_critical[@]}"; do
            install_module "$module"
        done
        
        echo ""
        echo "🔄 ПОВТОРНАЯ ПРОВЕРКА ПОСЛЕ УСТАНОВКИ"
        echo "------------------------------------"
        check_module "opencv-python-headless" "cv2"
        check_module "PyWavelets" "pywt" 
        check_module "diffusers" "diffusers"
        check_module "sageattention" "sageattention"
    fi
else
    echo "✅ Все критически важные модули установлены!"
fi

echo ""
echo "6️⃣ ПРОВЕРКА КОНФЛИКТОВ ВЕРСИЙ"
echo "-----------------------------"

echo "🔍 Проверяем конфликты numpy..."
python3 -c "
import numpy as np
print(f'NumPy версия: {np.__version__}')

# Проверяем совместимость с другими пакетами
try:
    import torch
    print(f'PyTorch версия: {torch.__version__}')
    print(f'PyTorch требует numpy: совместимо')
except ImportError:
    print('PyTorch не установлен')

try:
    import cv2
    print(f'OpenCV версия: {cv2.__version__}')
    print('OpenCV совместим с numpy')
except ImportError:
    print('OpenCV не установлен')
" 2>/dev/null || echo "❌ Ошибка при проверке версий"

echo ""
echo "📊 ИТОГОВЫЙ ОТЧЕТ"
echo "================"
echo "Дата: $(date)"
echo "Система: $(uname -a)"
echo "Скрипт завершен. Проверьте вывод выше для диагностики проблем."