"""
keyboards.py
Все клавиатуры бота
"""
from typing import List, Dict, Any  
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
import config
import re
import database

def main_menu():
    """Базовое главное меню (без промокодов - будет заменено динамически)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🍽️ МЕНЮ РЕСТОРАНА", callback_data="menu_food"),
        ],
        [
            InlineKeyboardButton(text="🚚 ЗАКАЗАТЬ ДОСТАВКУ", callback_data="menu_delivery"),
        ],
        [
            InlineKeyboardButton(text="📅 БРОНИРОВАНИЕ СТОЛОВ", callback_data="booking"),
        ],
        [
            InlineKeyboardButton(text="🎉 РЕГИСТРАЦИЯ НА МЕРОПРИЯТИЯ", callback_data="event_registration"),
        ],
        [
            InlineKeyboardButton(text="📍 КАК НАС НАЙТИ", callback_data="about_us"),
        ],
        [
            InlineKeyboardButton(text="⭐ ОТЗЫВЫ ГОСТЕЙ", callback_data="reviews"),
        ],
        [
            InlineKeyboardButton(text="❓ ЧАСТЫЕ ВОПРОСЫ", callback_data="faq"),
        ],
        [
            InlineKeyboardButton(text="📞 СВЯЗАТЬСЯ С НАМИ", callback_data="contact_us"),
        ]
    ])
def food_menu():
    """Меню еды с прямой ссылкой на мини-приложение"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 ЭЛЕКТРОННОЕ МЕНЮ", web_app=types.WebAppInfo(url="https://sabyget.ru/menu/mashkovrest_77")),
        ],
        [
            InlineKeyboardButton(text="📋 PDF МЕНЮ С БАРНОЙ КАРТОЙ", callback_data="menu_pdf"),
        ],
        [
            InlineKeyboardButton(text="🚚 ЗАКАЗАТЬ ДОСТАВКУ", callback_data="menu_delivery"),
        ],
        [
            InlineKeyboardButton(text="🎉 БАНКЕТНОЕ МЕНЮ", callback_data="menu_banquet"),
        ],
        [
            InlineKeyboardButton(text="⬅️ НАЗАД В ГЛАВНОЕ МЕНЮ", callback_data="back_main"),
        ]
    ])
def delivery_type_keyboard() -> types.InlineKeyboardMarkup:
    """Клавиатура выбора типа заказа"""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="🚚 Доставка", callback_data="order_delivery"),
            types.InlineKeyboardButton(text="🏃 Самовывоз", callback_data="order_pickup")
        ],
        [
            types.InlineKeyboardButton(text="🛒 Корзина", callback_data="view_cart"),
            types.InlineKeyboardButton(text="🏠 Главная", callback_data="back_main")
        ]
    ])

def location_keyboard() -> types.InlineKeyboardMarkup:
    """Клавиатура для отправки местоположения"""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📍 Поделиться местоположением", callback_data="share_location")],
        [types.InlineKeyboardButton(text="📝 Ввести адрес вручную", callback_data="enter_address_manually")]
    ])

def payment_keyboard(sale_key: str) -> types.InlineKeyboardMarkup:
    """Клавиатура для оплаты"""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💳 Оплатить онлайн", callback_data=f"pay_now_{sale_key}")],
        [types.InlineKeyboardButton(text="🔍 Проверить оплату", callback_data=f"check_payment_{sale_key}")],
        [types.InlineKeyboardButton(text="🏠 Главная", callback_data="back_main")]
    ])
def about_menu():
    """Меню 'О нас' - широкие кнопки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📸 ФОТО ЭКСТЕРЬЕРА И ИНТЕРЬЕРА", callback_data="photos"),
        ],
        [
            InlineKeyboardButton(text="🗺️ КАК ДОБРАТЬСЯ", url="https://yandex.ru/maps/-/CDqRIRXq"),
        ],
        [
            InlineKeyboardButton(text="⬅️ НАЗАД В ГЛАВНОЕ МЕНЮ", callback_data="back_main"),
        ]
    ])

def faq_menu(faq_list=None):
    """Меню FAQ - динамические кнопки"""
    keyboard = []
    
    if faq_list:
        for faq_id, question, answer in faq_list:
            # Обрезаем длинные вопросы
            button_text = question[:30] + "..." if len(question) > 30 else question
            keyboard.append([
                InlineKeyboardButton(text=f"❓ {button_text}", callback_data=f"faq_{faq_id}")
            ])
    
    # Добавляем кнопку "Связаться с нами"
    keyboard.append([
        InlineKeyboardButton(text="📞 НЕ НАШЛИ ОТВЕТ? СВЯЖИТЕСЬ С НАМИ!", callback_data="contact_us")
    ])
    
    keyboard.append([
        InlineKeyboardButton(text="⬅️ НАЗАД В ГЛАВНОЕ МЕНЮ", callback_data="back_main")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def calendar_menu():
    """Календарь - широкие кнопки"""
    today = datetime.now()
    keyboard = []
    
    for i in range(14):
        date = today + timedelta(days=i)
        date_str = date.strftime("%d.%m.%Y")
        callback_data = f"date_{date.strftime('%Y-%m-%d')}"
        
        if i == 0:
            label = f"🗓️ СЕГОДНЯ ({date_str})"
        elif i == 1:
            label = f"🗓️ ЗАВТРА ({date_str})"
        else:
            day_name = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"][date.weekday()]
            label = f"🗓️ {day_name} {date_str}"
        
        keyboard.append([InlineKeyboardButton(text=label, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton(text="⬅️ НАЗАД К БРОНИРОВАНИЮ", callback_data="book_now")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def time_menu():
    """Выбор времени - широкие кнопки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🕐 12:00", callback_data="time_12"),
            InlineKeyboardButton(text="🕐 13:00", callback_data="time_13"),
            InlineKeyboardButton(text="🕐 14:00", callback_data="time_14")
        ],
        [
            InlineKeyboardButton(text="🕐 15:00", callback_data="time_15"),
            InlineKeyboardButton(text="🕐 16:00", callback_data="time_16"),
            InlineKeyboardButton(text="🕐 17:00", callback_data="time_17")
        ],
        [
            InlineKeyboardButton(text="🕐 18:00", callback_data="time_18"),
            InlineKeyboardButton(text="🕐 19:00", callback_data="time_19"),
            InlineKeyboardButton(text="🕐 20:00", callback_data="time_20")
        ],
        [
            InlineKeyboardButton(text="🕐 21:00", callback_data="time_21"),
            InlineKeyboardButton(text="🕐 22:00", callback_data="time_22")
        ],
        [
            InlineKeyboardButton(text="⬅️ НАЗАД К ВЫБОРУ ДАТЫ", callback_data="book_now")
        ]
    ])

def guests_menu():
    """Выбор количества гостей - широкие кнопки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👤 1 ГОСТЬ", callback_data="guests_1"),
            InlineKeyboardButton(text="👥 2 ГОСТЯ", callback_data="guests_2")
        ],
        [
            InlineKeyboardButton(text="👥 3 ГОСТЯ", callback_data="guests_3"),
            InlineKeyboardButton(text="👥 4 ГОСТЯ", callback_data="guests_4")
        ],
        [
            InlineKeyboardButton(text="👥 5 ГОСТЕЙ", callback_data="guests_5"),
            InlineKeyboardButton(text="👥 6 ГОСТЕЙ", callback_data="guests_6")
        ],
        [
            InlineKeyboardButton(text="👥 7+ ГОСТЕЙ", callback_data="guests_7")
        ],
        [
            InlineKeyboardButton(text="⬅️ НАЗАД К ВЫБОРУ ВРЕМЕНИ", callback_data="time_back")
        ]
    ])

def back_to_main():
    """Кнопка назад в главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В ГЛАВНОЕ МЕНЮ", callback_data="back_main")]
    ])

# Админские клавиатуры
def admin_menu():
    """Меню админки - широкие кнопки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💬 УПРАВЛЕНИЕ ЧАТАМИ", url="https://t.me/MashkovRestBot/Admin"),
        ],
        [
            InlineKeyboardButton(text="📊 СТАТИСТИКА БОТА", callback_data="admin_stats"),
        ],
        [
            InlineKeyboardButton(text="👥 УПРАВЛЕНИЕ АДМИНАМИ", callback_data="admin_manage_admins"),
        ],
        [
            InlineKeyboardButton(text="📢 УПРАВЛЕНИЕ РАССЫЛКАМИ", callback_data="admin_newsletter"),
        ],
        [
            InlineKeyboardButton(text="⭐ УПРАВЛЕНИЕ ОТЗЫВАМИ", callback_data="admin_reviews"),
        ],
        [
            InlineKeyboardButton(text="❓ УПРАВЛЕНИЕ FAQ", callback_data="admin_faq"),
        ],
        [
            InlineKeyboardButton(text="🤖 СИСТЕМНЫЕ ПРОМПТЫ", callback_data="admin_system_prompts"),
        ],
        [
            InlineKeyboardButton(text="📋 УПРАВЛЕНИЕ ФАЙЛАМИ МЕНЮ", callback_data="admin_menu_files"),
        ],
        [
            InlineKeyboardButton(text="⚙️ НАСТРОЙКИ БОТА", callback_data="admin_settings"),
        ],
        [
            InlineKeyboardButton(text="🏠 В ГЛАВНОЕ МЕНЮ", callback_data="back_main")
        ]
    ])
def dish_selection_keyboard(dishes: List[Dict], selected_dishes: List[int] = None, page: int = 0, page_size: int = 10):
    """Клавиатура для выбора блюд"""
    if selected_dishes is None:
        selected_dishes = []
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    start_idx = page * page_size
    end_idx = start_idx + page_size
    page_dishes = dishes[start_idx:end_idx]
    
    for dish in page_dishes:
        dish_id = dish.get('id')
        dish_name = dish.get('name', 'Без названия')
        is_selected = dish_id in selected_dishes
        
        button_text = f"{'✅' if is_selected else '⬜'} {dish_name[:20]}"
        if dish.get('price'):
            button_text += f" - {dish['price']}₽"
        
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=button_text,
                callback_data=f"toggle_dish_{dish_id}"
            )
        ])
    
    # Кнопки навигации
    navigation_buttons = []
    
    if page > 0:
        navigation_buttons.append(
            types.InlineKeyboardButton(text="⬅️ Предыдущие", callback_data=f"dish_page_{page-1}")
        )
    
    if end_idx < len(dishes):
        navigation_buttons.append(
            types.InlineKeyboardButton(text="Следующие ➡️", callback_data=f"dish_page_{page+1}")
        )
    
    if navigation_buttons:
        keyboard.inline_keyboard.append(navigation_buttons)
    
    # Кнопка подтверждения
    if selected_dishes:
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text=f"✅ Выбрано {len(selected_dishes)} блюд", callback_data="confirm_dishes_selection")
        ])
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_promocode_type")
    ])
    
    return keyboard

def category_selection_keyboard(categories: List[Dict], selected_categories: List[int] = None):
    """Клавиатура для выбора категорий"""
    if selected_categories is None:
        selected_categories = []
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    for category in categories:
        category_id = category.get('id')
        category_name = category.get('display_name', category.get('name', 'Категория'))
        is_selected = category_id in selected_categories
        
        button_text = f"{'✅' if is_selected else '⬜'} {category_name}"
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=button_text,
                callback_data=f"toggle_category_{category_id}"
            )
        ])
    
    if selected_categories:
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text=f"✅ Выбрано {len(selected_categories)} категорий", callback_data="confirm_categories_selection")
        ])
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_promocode_type")
    ])
    
    return keyboard
def promocodes_admin_menu():
    """Меню управления промокодами в админке"""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_add_promocode")],
        [types.InlineKeyboardButton(text="📋 Все промокоды", callback_data="admin_view_promocodes")],
        [types.InlineKeyboardButton(text="📊 Статистика промокодов", callback_data="admin_promocodes_stats")],
        [types.InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_back")]
    ])
def promocodes_management_menu():
    """Меню управления промокодами"""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Активировать/деактивировать", callback_data="admin_toggle_promocode")],
        [types.InlineKeyboardButton(text="✏️ Изменить промокод", callback_data="admin_edit_promocode")],
        [types.InlineKeyboardButton(text="🗑️ Удалить промокод", callback_data="admin_delete_promocode")],
        [types.InlineKeyboardButton(text="📊 Статистика промокодов", callback_data="admin_promocodes_stats")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_promocodes")]
    ])

def my_promocodes_menu():
    """Меню для раздела 'Мои промокоды' пользователя"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 Перейти к корзине", callback_data="view_cart")],
        [types.InlineKeyboardButton(text="🍽️ Сделать заказ", callback_data="menu_delivery")],
        [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
    ])

def back_to_promocodes():
    """Назад к промокодам"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ НАЗАД К ПРОМОКОДАМ", callback_data="admin_promocodes")]
    ])

def back_to_admin():
    """Назад в админку"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ НАЗАД В АДМИНКУ", callback_data="admin_back")]
    ])

def newsletter_menu():
    """Меню управления рассылками"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 СОЗДАТЬ НОВУЮ РАССЫЛКУ", callback_data="admin_create_newsletter")],
        [InlineKeyboardButton(text="📊 СТАТИСТИКА ВСЕХ РАССЫЛОК", callback_data="admin_all_newsletters")],
        [InlineKeyboardButton(text="⏰ ОТЛОЖЕННЫЕ РАССЫЛКИ", callback_data="admin_scheduled_newsletters")],
        [InlineKeyboardButton(text="⬅️ НАЗАД В АДМИНКУ", callback_data="admin_back")]
    ])

def back_to_newsletter():
    """Назад к рассылкам"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ НАЗАД К РАССЫЛКАМ", callback_data="admin_newsletter")]
    ])

def reviews_admin_menu():
    """Меню управления отзывами"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 СПАРСИТЬ ОТЗЫВЫ С ЯНДЕКСА", callback_data="parse_reviews")],
        [InlineKeyboardButton(text="👁️ ПРОСМОТРЕТЬ ВСЕ ОТЗЫВЫ", callback_data="admin_view_reviews")],
        [InlineKeyboardButton(text="🗑️ УДАЛИТЬ ОДИН ОТЗЫВ", callback_data="admin_delete_review_start")],
        [InlineKeyboardButton(text="💣 УДАЛИТЬ ВСЕ ОТЗЫВЫ", callback_data="admin_delete_all_reviews")],
        [InlineKeyboardButton(text="⬅️ НАЗАД В АДМИНКУ", callback_data="admin_back")]
    ])

def reviews_edit_menu():
    """Меню редактирования отзывов"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ УДАЛИТЬ ОТЗЫВ", callback_data="admin_delete_review_start")],
        [InlineKeyboardButton(text="⬅️ НАЗАД", callback_data="admin_reviews")]
    ])

def faq_admin_menu():
    """Меню управления FAQ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ ДОБАВИТЬ НОВЫЙ FAQ", callback_data="admin_add_faq")],
        [InlineKeyboardButton(text="👁️ ПРОСМОТРЕТЬ ВСЕ FAQ", callback_data="admin_view_faq")],
        [InlineKeyboardButton(text="🗑️ УДАЛИТЬ FAQ", callback_data="admin_delete_faq_start")],
        [InlineKeyboardButton(text="⬅️ НАЗАД В АДМИНКУ", callback_data="admin_back")]
    ])

def faq_edit_menu():
    """Меню редактирования FAQ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ УДАЛИТЬ FAQ", callback_data="admin_delete_faq_start")],
        [InlineKeyboardButton(text="⬅️ НАЗАД", callback_data="admin_faq")]
    ])

def settings_menu():
    """Меню настроек"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🏷️ Изменить название ресторана", callback_data="edit_setting_restaurant_name")],
        [types.InlineKeyboardButton(text="📍 Изменить адрес", callback_data="edit_setting_restaurant_address")],
        [types.InlineKeyboardButton(text="📞 Изменить телефон", callback_data="edit_setting_restaurant_phone")],
        [types.InlineKeyboardButton(text="🕐 Изменить часы работы", callback_data="edit_setting_restaurant_hours")],
        [types.InlineKeyboardButton(text="🗺️ Изменить 'Как добраться'", callback_data="edit_setting_how_to_get")],
        [types.InlineKeyboardButton(text="📝 Изменить описание концепта", callback_data="edit_setting_concept_description")],
        [types.InlineKeyboardButton(text="💬 Изменить стартовое сообщение", callback_data="edit_setting_start_message")],
        [types.InlineKeyboardButton(text="🚚 Изменить стоимость доставки", callback_data="edit_setting_delivery_cost")],
        [types.InlineKeyboardButton(text="💰 Изменить минимум для бесплатной доставки", callback_data="edit_setting_free_delivery_min")],
        [types.InlineKeyboardButton(text="⏱️ Изменить время доставки", callback_data="edit_setting_delivery_time")],
        [types.InlineKeyboardButton(text="🏭 Настройка чата для поставщиков", callback_data="edit_setting_suppliers_chat_id")],
        [types.InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_back")]
    ])

def admin_menu_files_menu():
    """Меню управления файлами меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 ЗАГРУЗИТЬ PDF МЕНЮ", callback_data="admin_upload_pdf")],
        [InlineKeyboardButton(text="📊 ЗАГРУЗИТЬ БАНКЕТНОЕ МЕНЮ", callback_data="admin_upload_banquet")],
        [InlineKeyboardButton(text="📤 СКАЧАТЬ ТЕКУЩИЕ ФАЙЛЫ", callback_data="admin_download_menus")],
        [InlineKeyboardButton(text="⬅️ НАЗАД В АДМИНКУ", callback_data="admin_back")]
    ])

def download_menus_menu():
    """Меню скачивания файлов меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 СКАЧАТЬ PDF МЕНЮ", callback_data="download_pdf")],
        [InlineKeyboardButton(text="📊 СКАЧАТЬ БАНКЕТНОЕ МЕНЮ", callback_data="download_banquet")],
        [InlineKeyboardButton(text="⬅️ НАЗАД", callback_data="admin_menu_files")]
    ])

# Клавиатуры для подтверждения бронирования
def confirm_booking_menu():
    """Меню подтверждения бронирования"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ БРОНЬ", callback_data="confirm_booking"),
            InlineKeyboardButton(text="❌ ОТМЕНИТЬ", callback_data="cancel_booking")
        ]
    ])

def booking_confirmed_menu():
    """Меню после подтверждения бронирования"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 ЗАБРОНИРОВАТЬ ЕЩЁ", callback_data="booking")],
        [InlineKeyboardButton(text="🍽️ ПОСМОТРЕТЬ МЕНЮ", callback_data="menu_food")],
        [InlineKeyboardButton(text="🏠 В ГЛАВНОЕ МЕНЮ", callback_data="back_main")]
    ])

# Клавиатуры для заказа доставки
def order_menu():
    """Меню для заказа доставки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 СДЕЛАТЬ ЗАКАЗ", callback_data="make_order")],
        [InlineKeyboardButton(text="📞 СВЯЗАТЬСЯ С ОПЕРАТОРОМ", callback_data="contact_us")],
        [InlineKeyboardButton(text="⬅️ НАЗАД", callback_data="menu_delivery")]
    ])

def contact_menu():
    """Меню контактов"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📞 Позвонить", callback_data="call_us")],
        [types.InlineKeyboardButton(text="💬 Написать сообщение", callback_data="chat_operator")],
        [types.InlineKeyboardButton(text="🏭 Для поставщиков", callback_data="suppliers_contact")],
        [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
    ])

# ===== ДОБАВЛЯЕМ В keyboards.py =====

def main_menu_with_profile(user_id: int = None) -> types.InlineKeyboardMarkup:
    """Главное меню с мини-аппами вместо доставки"""
    from database import check_user_registration_fast

    if user_id:
        registration_status = check_user_registration_fast(user_id)

        if registration_status == 'completed':
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🍽️ МЕНЮ РЕСТОРАНА", callback_data="menu_food")],
                [types.InlineKeyboardButton(text="🚚 ЗАКАЗАТЬ ДОСТАВКУ", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))],
                [types.InlineKeyboardButton(text="📅 БРОНИРОВАНИЕ СТОЛОВ", callback_data="booking")],
                [types.InlineKeyboardButton(text="🎉 РЕГИСТРАЦИЯ НА МЕРОПРИЯТИЯ", callback_data="event_registration")],
                [types.InlineKeyboardButton(text="📱 НАШЕ ПРИЛОЖЕНИЕ", callback_data="our_app")],
                [types.InlineKeyboardButton(text="👤 ЛИЧНЫЙ КАБИНЕТ", callback_data="personal_cabinet")],
                [types.InlineKeyboardButton(text="📍 КАК НАС НАЙТИ", callback_data="about_us")],
                [types.InlineKeyboardButton(text="⭐ ОТЗЫВЫ ГОСТЕЙ", callback_data="reviews")],
                [types.InlineKeyboardButton(text="❓ ЧАСТЫЕ ВОПРОСЫ", callback_data="faq")],
                [types.InlineKeyboardButton(text="📞 СВЯЗАТЬСЯ С НАМИ", callback_data="contact_us")]
            ])
        else:
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🍽️ МЕНЮ РЕСТОРАНА", callback_data="menu_food")],
                [types.InlineKeyboardButton(text="🚚 ЗАКАЗАТЬ ДОСТАВКУ", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))],
                [types.InlineKeyboardButton(text="📅 БРОНИРОВАНИЕ СТОЛОВ", callback_data="booking")],
                [types.InlineKeyboardButton(text="🎉 РЕГИСТРАЦИЯ НА МЕРОПРИЯТИЯ", callback_data="event_registration")],
                [types.InlineKeyboardButton(text="📱 НАШЕ ПРИЛОЖЕНИЕ", callback_data="our_app")],
                [types.InlineKeyboardButton(text="📱 РЕГИСТРАЦИЯ/ВХОД", callback_data="register_or_login")],
                [types.InlineKeyboardButton(text="📍 КАК НАС НАЙТИ", callback_data="about_us")],
                [types.InlineKeyboardButton(text="⭐ ОТЗЫВЫ ГОСТЕЙ", callback_data="reviews")],
                [types.InlineKeyboardButton(text="❓ ЧАСТЫЕ ВОПРОСЫ", callback_data="faq")],
                [types.InlineKeyboardButton(text="📞 СВЯЗАТЬСЯ С НАМИ", callback_data="contact_us")]
            ])
    else:
        # По умолчанию показываем без регистрации
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🍽️ МЕНЮ РЕСТОРАНА", callback_data="menu_food")],
            [types.InlineKeyboardButton(text="🚚 ЗАКАЗАТЬ ДОСТАВКУ", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))],
            [types.InlineKeyboardButton(text="📅 БРОНИРОВАНИЕ СТОЛОВ", callback_data="booking")],
            [types.InlineKeyboardButton(text="🎉 РЕГИСТРАЦИЯ НА МЕРОПРИЯТИЯ", callback_data="event_registration")],
            [types.InlineKeyboardButton(text="📱 НАШЕ ПРИЛОЖЕНИЕ", callback_data="our_app")],
            [types.InlineKeyboardButton(text="📱 РЕГИСТРАЦИЯ/ВХОД", callback_data="register_or_login")],
            [types.InlineKeyboardButton(text="📍 КАК НАС НАЙТИ", callback_data="about_us")],
            [types.InlineKeyboardButton(text="⭐ ОТЗЫВЫ ГОСТЕЙ", callback_data="reviews")],
            [types.InlineKeyboardButton(text="❓ ЧАСТЫЕ ВОПРОСЫ", callback_data="faq")],
            [types.InlineKeyboardButton(text="📞 СВЯЗАТЬСЯ С НАМИ", callback_data="contact_us")]
        ])

    return keyboard

def personal_cabinet_menu() -> types.InlineKeyboardMarkup:
    """Упрощенное меню личного кабинета"""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📱 Изменить телефон", callback_data="change_phone")],
        [types.InlineKeyboardButton(text="👤 Изменить имя", callback_data="change_name")],
        [types.InlineKeyboardButton(text="📅 История бронирований", callback_data="booking_history")],
        [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
    ])

def my_addresses_menu(addresses: List[Dict]) -> types.InlineKeyboardMarkup:
    """Меню управления адресами"""
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    for address in addresses[:5]:  # Ограничиваем 5 адресами
        address_text = address['address'][:30]
        if len(address['address']) > 30:
            address_text += "..."
        
        button_text = f"{'⭐ ' if address.get('is_default') else ''}{address_text}"
        
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=button_text,
                callback_data=f"view_address_{address['id']}"
            )
        ])
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="➕ Добавить новый адрес", callback_data="add_new_address")
    ])
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="⬅️ Назад в ЛК", callback_data="personal_cabinet")
    ])
    
    return keyboard

def address_management_menu(address_id: int) -> types.InlineKeyboardMarkup:
    """Меню управления конкретным адресом"""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⭐ Сделать основным", callback_data=f"set_default_address_{address_id}")],
        [types.InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_address_{address_id}")],
        [types.InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_address_{address_id}")],
        [types.InlineKeyboardButton(text="⬅️ Мои адреса", callback_data="my_addresses")]
    ])

def order_history_menu(orders: List[Dict], page: int = 0) -> types.InlineKeyboardMarkup:
    """Меню истории заказов с пагинацией"""
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    # Показываем 5 заказов на странице
    start_idx = page * 5
    end_idx = start_idx + 5
    page_orders = orders[start_idx:end_idx]
    
    for i, order in enumerate(page_orders, start_idx + 1):
        order_date = order.get('created_at', '')[:10]
        total = order.get('total_amount', 0)
        
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=f"📦 Заказ #{order['id']} - {total}₽ ({order_date})",
                callback_data=f"view_order_{order['id']}"
            )
        ])
    
    # Кнопки навигации
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(
            types.InlineKeyboardButton(text="⬅️ Предыдущие", callback_data=f"orders_page_{page-1}")
        )
    
    if end_idx < len(orders):
        nav_buttons.append(
            types.InlineKeyboardButton(text="Следующие ➡️", callback_data=f"orders_page_{page+1}")
        )
    
    if nav_buttons:
        keyboard.inline_keyboard.append(nav_buttons)
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="⬅️ Назад в ЛК", callback_data="personal_cabinet")
    ])
    
    return keyboard

def order_details_menu(order_id: int) -> types.InlineKeyboardMarkup:
    """Меню деталей заказа"""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔄 Повторить заказ", callback_data=f"repeat_order_{order_id}")],
        [types.InlineKeyboardButton(text="⬅️ История заказов", callback_data="order_history")]
    ])

def booking_history_menu(bookings: List[Dict], page: int = 0) -> types.InlineKeyboardMarkup:
    """Меню истории бронирований с пагинацией"""
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    # Показываем 5 броней на странице
    start_idx = page * 5
    end_idx = start_idx + 5
    page_bookings = bookings[start_idx:end_idx]
    
    for i, booking in enumerate(page_bookings, start_idx + 1):
        date_display = booking.get('date_display', '')[:10]
        time_display = booking.get('time', '')[:5]
        
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=f"📅 {date_display} {time_display} - {booking.get('guests', 0)} гостей",
                callback_data=f"view_booking_{booking.get('external_id', '')}"
            )
        ])
    
    # Кнопки навигации
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(
            types.InlineKeyboardButton(text="⬅️ Предыдущие", callback_data=f"bookings_page_{page-1}")
        )
    
    if end_idx < len(bookings):
        nav_buttons.append(
            types.InlineKeyboardButton(text="Следующие ➡️", callback_data=f"bookings_page_{page+1}")
        )
    
    if nav_buttons:
        keyboard.inline_keyboard.append(nav_buttons)
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="⬅️ Назад в ЛК", callback_data="personal_cabinet")
    ])
    
    return keyboard

def register_or_login_menu() -> types.InlineKeyboardMarkup:
    """Меню регистрации/входа"""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📞 Поделиться номером телефона", callback_data="share_phone_for_registration")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])

def back_to_cabinet() -> types.InlineKeyboardMarkup:
    """Назад в личный кабинет"""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад в ЛК", callback_data="personal_cabinet")]
    ])

def photos_menu():
    """Меню фотогалереи"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 ПОСМОТРЕТЬ ЕЩЕ ФОТО", callback_data="more_photos")],
        [InlineKeyboardButton(text="⬅️ НАЗАД", callback_data="about_us")]
    ])

def empty_menu():
    """Пустая клавиатура (скрывает кнопки)"""
    return InlineKeyboardMarkup(inline_keyboard=[])

def event_registration_menu():
    """Меню регистрации на мероприятия"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 ОСТАВИТЬ ЗАЯВКУ", callback_data="event_application")],
        [InlineKeyboardButton(text="📞 СВЯЗАТЬСЯ С НАМИ", callback_data="contact_us")],
        [InlineKeyboardButton(text="⬅️ НАЗАД В ГЛАВНОЕ МЕНЮ", callback_data="back_main")]
    ])

def get_character_keyboard():
    """Клавиатура для создания персонажа"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎭 ВВЕСТИ ИМЯ ПЕРСОНАЖА", callback_data="start_character_creation")],
        [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_character")]
    ])
