#!/usr/bin/env python3
"""
Проверка здоровья OCR сервиса
Использование: python3 scripts/utils/check_ocr_health.py
"""
import requests
import sys

def check_health():
    """Проверка health endpoint OCR сервиса"""
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        data = response.json()
        
        print("╔════════════════════════════════════════╗")
        print("║   OCR Service Health Check             ║")
        print("╚════════════════════════════════════════╝")
        print(f"Status:        {data['status']}")
        print(f"Model loaded:  {data['model_loaded']}")
        print(f"CUDA:          {data['cuda_available']}")
        if 'cuda_device' in data:
            print(f"GPU:           {data['cuda_device']}")
        print("═" * 42)
        
        if data["status"] == "healthy" and data["model_loaded"]:
            print("✅ OCR сервис готов к работе")
            return 0
        else:
            print("⚠️  OCR сервис не готов (модель загружается...)")
            return 1
            
    except requests.exceptions.ConnectionError:
        print("❌ OCR сервис недоступен (Connection refused)")
        print("   Запустите сервис:")
        print("   python -m uvicorn scripts.pdf_to_context.ocr_service.app:app --port 8000")
        return 2
    except Exception as e:
        print(f"❌ Ошибка проверки: {e}")
        return 3

if __name__ == "__main__":
    sys.exit(check_health())

