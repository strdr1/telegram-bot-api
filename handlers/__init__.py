"""
handlers/__init__.py - ПОЛНЫЙ ИСПРАВЛЕННЫЙ С ЛИЧНЫМ КАБИНЕТОМ
Инициализация всех модулей обработчиков
"""

# Импортируем роутеры из всех модулей
from .handlers_main import router as main_router
from .handlers_admin import router as admin_router
from .handlers_booking import router as booking_router
from .handlers_delivery import router as delivery_router
from .handlers_registration import router as registration_router
from .handlers_personal_cabinet import router as personal_cabinet_router  # <-- ДОБАВИТЬ ЭТО

# Импортируем общие утилиты
from .utils import (
    safe_send_message,
    safe_edit_message,
    safe_delete_message,
    update_message,
    check_user_registration_fast,
    is_admin_fast,
    clear_user_cache,
    send_admin_notification,
    send_order_notification,
    last_message_ids,
    user_registration_cache,
    admin_cache
)

# Импортируем общие состояния
from .handlers_booking import BookingStates
from .handlers_admin import AdminStates
from .handlers_registration import RegistrationStates
from .handlers_delivery import MenuDeliveryStates, DeliveryOrderStates
from .handlers_personal_cabinet import PersonalCabinetStates  # <-- ДОБАВИТЬ ЭТО

# Импортируем часто используемые функции из handlers_main
from .handlers_main import (
    show_main_menu,
    show_reviews_handler,
    error_handler
)

# Импортируем часто используемые функции из handlers_registration
from .handlers_registration import (
    ask_for_registration_phone,
    ask_for_event_registration_phone,
    handle_post_registration_redirect,
    RegistrationStates,
    EventRegistrationStates
)

# Импортируем часто используемые функции из handlers_booking
from .handlers_booking import (
    booking_start,
)

# Импортируем ВСЕ функции из handlers_delivery
from .handlers_delivery import (
    menu_delivery_handler,
    menu_food_handler,
    menu_delivery_callback,
    menu_food_callback,
    menu_pdf_callback,
    menu_banquet_callback,
    make_order_callback,
    show_static_menu,
    show_cart,
    cleanup_all_other_messages,
    update_main_message,
    user_main_message,
    user_message_history,
    user_photo_messages,
    cleanup_photo_messages,
    show_category_photos,
    send_dish_photo,
    format_full_dish_description,
    view_full_desc_handler,
    back_from_detail_handler,
    select_category_handler
)

# Импортируем часто используемые функции из handlers_admin
from .handlers_admin import (
    show_admin_panel,
    admin_newsletter_handler,
    admin_command_handler,
    admin_back_callback,
    admin_stats_callback,
    admin_orders_callback,
    admin_newsletter_callback,
    admin_create_newsletter_callback,
    admin_reviews_callback,
    admin_faq_callback,
    admin_settings_callback,
    admin_menu_files_callback,
    admin_upload_pdf_callback,
    admin_upload_banquet_callback,
    admin_download_menus_callback
)

# Импортируем функции из handlers_personal_cabinet
from .handlers_personal_cabinet import (
    personal_cabinet_handler,
    register_or_login_handler,
    share_phone_for_registration_handler,
    change_phone_handler,
    change_name_handler,
    booking_history_handler
)

# Определяем, что будет доступно при импорте из пакета
__all__ = [
    # Роутеры
    'main_router',
    'admin_router',
    'booking_router',
    'delivery_router',
    'registration_router',
    'personal_cabinet_router',  # <-- ДОБАВИТЬ ЭТО
    
    # Утилиты
    'safe_send_message',
    'safe_edit_message',
    'safe_delete_message',
    'update_message',
    'check_user_registration_fast',
    'is_admin_fast',
    'clear_user_cache',
    'send_order_notification',
    'send_admin_notification',
    'last_message_ids',
    'user_registration_cache',
    'admin_cache',
    
    # Состояния
    'BookingStates',
    'AdminStates',
    'RegistrationStates',
    'EventRegistrationStates',
    'MenuDeliveryStates',
    'DeliveryOrderStates',
    'PersonalCabinetStates',  # <-- ДОБАВИТЬ ЭТО
    
    # Часто используемые функции из handlers_main
    'show_main_menu',
    'show_reviews_handler',
    'error_handler',
    
    # Часто используемые функции из handlers_registration
    'ask_for_registration_phone',
    'ask_for_event_registration_phone',
    'handle_post_registration_redirect',
    
    # Часто используемые функции из handlers_booking
    'booking_start',
    
    # Часто используемые функции из handlers_delivery
    'menu_delivery_handler',
    'menu_food_handler',
    'menu_delivery_callback',
    'menu_food_callback',
    'menu_pdf_callback',
    'menu_banquet_callback',
    'make_order_callback',
    'show_static_menu',
    'show_cart',
    'cleanup_all_other_messages',
    'update_main_message',
    'user_main_message',
    'user_message_history',
    'user_photo_messages',
    'cleanup_photo_messages',
    'show_category_photos',
    'send_dish_photo',
    'format_full_dish_description',
    'view_full_desc_handler',
    'back_from_detail_handler',
    'select_category_handler',
    
    # Часто используемые функции из handlers_admin
    'show_admin_panel',
    'admin_newsletter_handler',
    'admin_command',
    'admin_back_callback',
    'admin_stats_callback',
    'admin_orders_callback',
    'admin_newsletter_callback',
    'admin_create_newsletter_callback',
    'admin_reviews_callback',
    'admin_faq_callback',
    'admin_settings_callback',
    'admin_menu_files_callback',
    'admin_upload_pdf_callback',
    'admin_upload_banquet_callback',
    'admin_download_menus_callback',
    
    # Функции из handlers_personal_cabinet
    'personal_cabinet_handler',
    'register_or_login_handler',
    'share_phone_for_registration_handler',
    'change_phone_handler',
    'change_name_handler',
    'booking_history_handler'
]

print("✅ handlers/__init__.py: Все модули и функции импортированы успешно!")