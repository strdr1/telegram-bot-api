"""
Тестовый скрипт для проверки системы лимитов AI генераций
"""
import database

# Инициализируем базу данных
database.init_database()

# Тестовый пользователь (не админ)
test_user_id = 123456789

print("=== Тест системы лимитов AI генераций ===\n")

# Проверяем начальное состояние
can_generate, remaining = database.check_ai_generation_limit(test_user_id)
print(f"Начальное состояние:")
print(f"  Можно генерировать: {can_generate}")
print(f"  Осталось генераций: {remaining}\n")

# Первая генерация
print("Генерация #1...")
database.increment_ai_generation(test_user_id)
can_generate, remaining = database.check_ai_generation_limit(test_user_id)
print(f"  Можно генерировать: {can_generate}")
print(f"  Осталось генераций: {remaining}\n")

# Вторая генерация
print("Генерация #2...")
database.increment_ai_generation(test_user_id)
can_generate, remaining = database.check_ai_generation_limit(test_user_id)
print(f"  Можно генерировать: {can_generate}")
print(f"  Осталось генераций: {remaining}\n")

# Попытка третьей генерации (должна быть заблокирована)
print("Попытка генерации #3...")
can_generate, remaining = database.check_ai_generation_limit(test_user_id)
print(f"  Можно генерировать: {can_generate}")
print(f"  Осталось генераций: {remaining}\n")

# Статистика
stats = database.get_ai_generation_stats(test_user_id)
print(f"Статистика пользователя {test_user_id}:")
print(f"  Сегодня: {stats['today']}")
print(f"  Всего: {stats['total']}")
print(f"  Админ: {stats['is_admin']}\n")

# Тест для админа
print("=== Тест для админа ===\n")
admin_id = 515216260  # Замените на реальный ID админа

# Добавляем админа если его нет
database.add_admin(admin_id)

can_generate, remaining = database.check_ai_generation_limit(admin_id)
print(f"Админ {admin_id}:")
print(f"  Можно генерировать: {can_generate}")
print(f"  Осталось генераций: {remaining} (безлимит)")

print("\n=== Тест завершен ===")
