
import logging
from category_handler import check_category_match

# Настройка логирования
logging.basicConfig(level=logging.INFO)

def test_matching():
    test_cases = [
        ("салаты", "салаты"),
        ("а покажи салаты", "салаты"),
        ("хочу горячее", "горячие блюда"),
        ("по салатам", "салаты"),
        ("по горячему", "горячие блюда"),
        ("что по напиткам", "напитки"),
        ("какие есть супы", "супы"),
        ("меню завтраков", "завтраки"),
        ("а есть пицца?", "пицца"),
    ]

    print("\n--- Testing check_category_match ---")
    failed = 0
    for input_text, expected in test_cases:
        result = check_category_match(input_text)
        status = "✅ OK" if result == expected else f"❌ FAIL (Expected '{expected}', got '{result}')"
        print(f"Input: '{input_text}' -> {status}")
        if result != expected:
            failed += 1
            
    if failed == 0:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️ {failed} tests failed.")

if __name__ == "__main__":
    test_matching()
