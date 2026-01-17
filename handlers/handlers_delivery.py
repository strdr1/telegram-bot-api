from aiogram import Router, F, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, BufferedInputFile, InputMediaPhoto
import keyboards
import database
import config
import asyncio
import logging
import os
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime, time, timedelta
import pytz
import json
import aiohttp
from .utils import update_message, check_user_registration_fast
from .handlers_registration import RegistrationStates, ask_for_registration_phone
from presto_api import PrestoAPI
from menu_cache import menu_cache
from cart_manager import cart_manager
from presto_api import PrestoAPI

logger = logging.getLogger(__name__)

router = Router()
presto_api = PrestoAPI()
FILES_DIR = "files/menu"
PDF_MENU_PATH = os.path.join(FILES_DIR, "Menu.pdf")
BANQUET_MENU_PATH = os.path.join(FILES_DIR, "MenuBanket.xlsx")

MOSCOW_TZ = pytz.timezone('Europe/Moscow')

user_main_message = {}
user_message_history = {}
user_photo_messages = {}
user_document_history = {}

pending_payments = {}

temp_messages = {}

async def add_temp_message(user_id: int, message_id: int):
    if user_id not in temp_messages:
        temp_messages[user_id] = []
    temp_messages[user_id].append(message_id)

async def cleanup_temp_messages(user_id: int, bot):
    """Очистка всех временных сообщений"""
    if user_id in temp_messages:
        for msg_id in temp_messages[user_id][:]:
            try:
                await bot.delete_message(user_id, msg_id)
            except Exception as e:
                logger.debug(f"Не удалось удалить временное сообщение {msg_id}: {e}")
            temp_messages[user_id].remove(msg_id)
        # Очищаем список
        temp_messages[user_id] = []


async def get_district_for_address(address_text: str, latitude: float, longitude: float) -> Optional[Dict]:
    """
    Получение района для адреса с проверкой нахождения в зоне доставки
    
    Возвращает:
    - Dict с данными района если адрес в зоне доставки
    - Dict с флагом 'unavailable': True если адрес вне зоны доставки
    - None при ошибке
    """
    try:
        logger.info(f"📍 Получение района для адреса: {address_text}")
        logger.info(f"📍 Координаты для проверки: lat={latitude:.6f}, lon={longitude:.6f}")
        
        # Получаем районы доставки
        districts = await presto_api.get_delivery_districts(with_coordinates=True)
        
        if not districts:
            logger.warning("⚠️ Нет районов доставки, используем дефолтный")
            return create_default_district(latitude, longitude)
        
        # ВЫВОДИМ ВСЕ РАЙОНЫ ДЛЯ ДИАГНОСТИКИ
        logger.info(f"📍 Получено {len(districts)} районов доставки:")
        for i, district in enumerate(districts):
            name = district.get('name', 'Без названия')
            district_id = district.get('districtId', district.get('id', 'N/A'))
            cost = district.get('cost', '?')
            min_order = district.get('minOrderSum', '1000')
            logger.info(f"   {i+1}. {name} (ID: {district_id}, Стоимость: {cost}₽, Мин. сумма: {min_order}₽)")
        
        selected_district = None
        found_in_district = False
        
        # Проверяем каждый район
        for district in districts:
            coordinates = district.get('coordinates', [])
            district_name = district.get('name', '')
            district_id = district.get('districtId')
            
            logger.info(f"📍 Проверяем район '{district_name}' (ID: {district_id})")
            
            # Проверяем координаты
            if not coordinates or not isinstance(coordinates, list):
                logger.info(f"   ❌ Нет координат для района '{district_name}'")
                continue
            
            polygon_points = []
            
            # Анализируем структуру координат
            for coord_group in coordinates:
                if not isinstance(coord_group, list):
                    continue
                    
                for point in coord_group:
                    if isinstance(point, list) and len(point) >= 2:
                        try:
                            val1 = float(point[0])
                            val2 = float(point[1])
                            
                            # Определяем порядок координат по диапазонам
                            # Москва: lat ≈ 55-56, lon ≈ 37-38
                            
                            if 30 <= val1 <= 40 and 50 <= val2 <= 60:
                                # Вероятно [lon, lat] - переворачиваем
                                lon = val1
                                lat = val2
                                logger.debug(f"   ↻ Обнаружен порядок [lon,lat]: {lon:.6f}, {lat:.6f} → {lat:.6f}, {lon:.6f}")
                                polygon_points.append([lat, lon])
                            elif 50 <= val1 <= 60 and 30 <= val2 <= 40:
                                # Стандартный порядок [lat, lon]
                                lat = val1
                                lon = val2
                                polygon_points.append([lat, lon])
                            else:
                                # Непонятный порядок
                                logger.warning(f"   ⚠️ Непонятные координаты: {val1}, {val2}")
                                polygon_points.append([val1, val2])
                                
                        except (ValueError, TypeError) as e:
                            logger.error(f"   ❌ Ошибка парсинга координат {point}: {e}")
                            continue
            
            if not polygon_points:
                logger.info(f"   ❌ Нет валидных точек полигона для района '{district_name}'")
                continue
            
            # Показываем информацию о полигоне
            logger.info(f"   📍 Полигон '{district_name}' имеет {len(polygon_points)} точек")
            
            # Проверяем диапазон координат полигона
            if polygon_points:
                lats = [p[0] for p in polygon_points]
                lons = [p[1] for p in polygon_points]
                min_lat = min(lats)
                max_lat = max(lats)
                min_lon = min(lons)
                max_lon = max(lons)
                logger.info(f"   📍 Диапазон полигона: lat[{min_lat:.6f}-{max_lat:.6f}], lon[{min_lon:.6f}-{max_lon:.6f}]")
                logger.info(f"   📍 Наша точка: lat={latitude:.6f}, lon={longitude:.6f}")
            
            # Проверяем точку в полигоне
            if polygon_points and point_in_polygon((latitude, longitude), polygon_points):
                logger.info(f"   ✅ Точка {latitude:.6f}, {longitude:.6f} внутри района '{district_name}'")
                selected_district = district
                found_in_district = True
                break
            else:
                logger.info(f"   ❌ Точка {latitude:.6f}, {longitude:.6f} ВНЕ района '{district_name}'")
        
        # ВАЖНОЕ ИЗМЕНЕНИЕ: Если точка НЕ входит ни в один полигон
        if not found_in_district:
            logger.error(f"❌ Адрес ВНЕ зоны доставки! Координаты: {latitude:.6f}, {longitude:.6f}")
            
            # Находим ближайший район для информационного сообщения
            closest_district = None
            min_distance = float('inf')
            closest_polygon_center = None
            
            for district in districts:
                coordinates = district.get('coordinates', [])
                district_name = district.get('name', '')
                
                if not coordinates:
                    continue
                
                # Находим центр полигона (среднее арифметическое)
                polygon_points = []
                for coord_group in coordinates:
                    if isinstance(coord_group, list):
                        for point in coord_group:
                            if isinstance(point, list) and len(point) >= 2:
                                try:
                                    val1 = float(point[0])
                                    val2 = float(point[1])
                                    
                                    # Анализируем порядок координат
                                    if 30 <= val1 <= 40 and 50 <= val2 <= 60:
                                        # [lon, lat]
                                        polygon_points.append([val2, val1])  # Переворачиваем
                                    elif 50 <= val1 <= 60 and 30 <= val2 <= 40:
                                        # [lat, lon]
                                        polygon_points.append([val1, val2])
                                except:
                                    continue
                
                if polygon_points:
                    # Вычисляем центр полигона
                    center_lat = sum(p[0] for p in polygon_points) / len(polygon_points)
                    center_lon = sum(p[1] for p in polygon_points) / len(polygon_points)
                    
                    # Расстояние в градусах (упрощенно)
                    distance = ((latitude - center_lat) ** 2 + (longitude - center_lon) ** 2) ** 0.5
                    
                    if distance < min_distance:
                        min_distance = distance
                        closest_district = district
                        closest_polygon_center = (center_lat, center_lon)
            
            # Возвращаем специальный объект с флагом недоступности
            unavailable_district = {
                'unavailable': True,
                'address': address_text,
                'latitude': latitude,
                'longitude': longitude,
                'closest_district': closest_district,
                'closest_district_name': closest_district.get('name') if closest_district else 'Не определено',
                'distance_degrees': min_distance,
                'distance_km': min_distance * 111,  # 1 градус ≈ 111 км
                'closest_center': closest_polygon_center,
                'message': f'Адрес находится вне зоны доставки. Ближайший район: {closest_district.get("name") if closest_district else "не определен"}'
            }
            
            logger.warning(f"⚠️ Возвращаем объект с флагом недоступности: {unavailable_district}")
            return unavailable_district
        
        # Если точка в зоне доставки, продолжаем обычную обработку
        logger.info(f"✅ Окончательный выбор: район '{selected_district.get('name')}'")
        
        # Приводим cost к float (ТОЛЬКО если он не None!)
        if 'cost' in selected_district and selected_district['cost'] is not None:
            try:
                selected_district['cost'] = float(selected_district['cost'])
            except (ValueError, TypeError):
                selected_district['cost'] = 300.0
        # Если cost равен None - ОСТАВЛЯЕМ ЕГО None!
        
        # Приводим costForFreeDelivery к float
        if 'costForFreeDelivery' in selected_district:
            try:
                selected_district['costForFreeDelivery'] = float(selected_district['costForFreeDelivery'])
            except (ValueError, TypeError):
                selected_district['costForFreeDelivery'] = 3000.0
        
        # Формируем JSON адреса для Presto API
        address_json_obj = {
            'Address': address_text,
            'Locality': 'Москва',
            'Coordinates': {
                'Lat': latitude,
                'Lon': longitude
            },
            'AptNum': '',
            'Entrance': '',
            'Floor': '',
            'DoorCode': ''
        }
        
        address_json = json.dumps(address_json_obj, ensure_ascii=False)
        
        # Добавляем дополнительные поля
        selected_district['address_json'] = address_json
        selected_district['address_full'] = address_text
        selected_district['coordinates_point'] = {'lat': latitude, 'lon': longitude}
        
        # Гарантируем наличие ID
        if 'districtId' not in selected_district:
            selected_district['districtId'] = selected_district.get('id')
        if 'id' not in selected_district and 'districtId' in selected_district:
            selected_district['id'] = selected_district['districtId']
        
        # Получаем минимальную сумму заказа
        min_order_sum = selected_district.get('minOrderSum')
        if min_order_sum is not None:
            try:
                selected_district['minOrderSum'] = float(min_order_sum)
                logger.info(f"💰 Минимальная сумма заказа для района: {selected_district['minOrderSum']}₽")
            except:
                selected_district['minOrderSum'] = 1000.0  # Дефолтное значение
        else:
            selected_district['minOrderSum'] = 1000.0
        
        return selected_district
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения района: {e}", exc_info=True)
        return create_default_district(latitude, longitude)

def point_in_polygon(point: Tuple[float, float], polygon: List[List[float]]) -> bool:
    """Улучшенная проверка точки в полигоне с диагностикой"""
    if not polygon or len(polygon) < 3:
        logger.debug(f"❌ Невалидный полигон: {len(polygon)} точек")
        return False
    
    x, y = point  # x = latitude, y = longitude
    n = len(polygon)
    inside = False
    
    # Проверяем, что координаты в разумных пределах
    if not (40 <= x <= 60 and 30 <= y <= 40):  # Примерно Москва и область
        logger.warning(f"⚠️ Подозрительные координаты точки: ({x:.6f}, {y:.6f})")
    
    # Алгоритм ray casting
    p1x, p1y = polygon[0]
    
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        
        # Проверяем пересечение горизонтального луча с ребром полигона
        if ((p1y > y) != (p2y > y)):
            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
            if x < xinters:
                inside = not inside
        
        p1x, p1y = p2x, p2y
    
    return inside
def create_default_district(latitude: float, longitude: float) -> Dict:
    return {
        'districtId': 20646,
        'id': 20646,
        'name': 'Город',
        'description': 'Доставка по городу',
        'cost': 300.0,
        'costForFreeDelivery': 3000.0,
        'sumThresholds': [
            {'From': 0, 'Price': 300.0},
            {'From': 3000, 'Price': 0.0}
        ],
        'deliveryTime': '45-60 минут',
        'minOrderSum': 0.0,
        'coordinates_point': {'lat': latitude, 'lon': longitude}
    }

async def geocode_address_local(address_or_message):
    try:
        if hasattr(address_or_message, 'text'):
            address_text = address_or_message.text
        else:
            address_text = str(address_or_message)
        
        address_text = address_text.strip()
        
        logger.info(f"📍 Геокодирование адреса: {address_text}")
        
        return await presto_api.geocode_address(address_text)
            
    except Exception as e:
        logger.error(f"❌ Ошибка геокодирования: {e}")
        return {'lat': 55.7558, 'lon': 37.6176}

class MenuDeliveryStates(StatesGroup):
    viewing_category = State()
    viewing_dish_detail = State()
    searching_dishes = State()
    viewing_cart = State()
    checkout = State()

class DeliveryOrderStates(StatesGroup):
    choosing_order_type = State()
    entering_address = State()
    checking_delivery = State()
    entering_address_details = State()
    entering_comment = State()
    entering_promocode = State()
    final_confirmation = State()

async def update_main_message(user_id: int, text: str, reply_markup=None, 
                            parse_mode="HTML", bot=None, message_id=None) -> bool:
    if bot is None:
        return False
    
    try:
        # Если передали конкретный message_id, используем его
        if message_id:
            try:
                await bot.edit_message_text(
                    chat_id=user_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                user_main_message[user_id] = message_id
                return True
            except Exception as e:
                logger.debug(f"Не удалось отредактировать сообщение {message_id}: {e}")
        
        # Иначе используем сохраненный message_id
        saved_message_id = user_main_message.get(user_id)
        
        if saved_message_id:
            try:
                await bot.edit_message_text(
                    chat_id=user_id,
                    message_id=saved_message_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                return True
            except Exception as e:
                logger.debug(f"Не удалось отредактировать сохраненное сообщение {saved_message_id}: {e}")
                # Пробуем удалить и создать новое
                try:
                    await bot.delete_message(user_id, saved_message_id)
                except:
                    pass
                del user_main_message[user_id]
        
        # Создаем новое сообщение
        message = await bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        
        user_main_message[user_id] = message.message_id
        return True
        
    except Exception as e:
        logger.error(f"Ошибка обновления основного сообщения: {e}")
        return False

async def cleanup_photo_messages(user_id: int, bot):
    if user_id in user_photo_messages:
        for msg_id in user_photo_messages[user_id]:
            try:
                await bot.delete_message(user_id, msg_id)
            except Exception as e:
                logger.debug(f"Не удалось удалить фото сообщение {msg_id}: {e}")
        user_photo_messages[user_id] = []

async def cleanup_all_other_messages(user_id: int, bot, keep_message_id: int = None):
    try:
        if user_id in user_photo_messages:
            for msg_id in user_photo_messages[user_id][:]:
                if msg_id != keep_message_id:
                    try:
                        await bot.delete_message(user_id, msg_id)
                    except Exception as e:
                        logger.debug(f"Не удалось удалить фото сообщение {msg_id}: {e}")
                    finally:
                        user_photo_messages[user_id].remove(msg_id)
        
        if user_id in user_message_history:
            for msg_id in user_message_history[user_id][:]:
                if msg_id != keep_message_id and msg_id != user_main_message.get(user_id):
                    try:
                        await bot.delete_message(user_id, msg_id)
                    except:
                        pass
                    finally:
                        user_message_history[user_id].remove(msg_id)
        
    except Exception as e:
        logger.debug(f"Ошибка очистки сообщений: {e}")

async def show_no_menu_available(user_id: int, bot):
    text = """🍽️ <b>Меню доставки</b>

⚠️ <b>В настоящее время меню недоступно</b>

Возможные причины:
• Обновление меню
• Технические работы
• Ресторан закрыт

Пожалуйста, попробуйте позже или свяжитесь с нами по телефону."""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="menu_delivery")],
        [types.InlineKeyboardButton(text="📞 Связаться", callback_data="contact_us")],
        [types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_main")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)

async def menu_delivery_handler(user_id: int, bot, state: FSMContext = None):
    if user_id in user_document_history and user_document_history[user_id]:
        for doc_id in user_document_history[user_id][:]:
            try:
                await bot.delete_message(user_id, doc_id)
            except Exception as e:
                logger.debug(f"Не удалось удалить документ {doc_id} при входе в меню доставки: {e}")
        user_document_history[user_id] = []
    
    if user_id in user_photo_messages:
        await cleanup_photo_messages(user_id, bot)
    
    # УБРАНА проверка регистрации здесь!
    # Теперь можно заходить в меню без регистрации
    
    await menu_cache.load_all_menus()
    
    available_menus = menu_cache.get_available_menus()
    
    if not available_menus:
        await show_no_menu_available(user_id, bot)
        return
    
    cart_summary = cart_manager.get_cart_summary(user_id)
    
    text = f"""🍽️ <b>Меню доставки</b>

🛒 <b>Корзина ({cart_summary['item_count']}):</b> {cart_summary['item_count']} позиций на {cart_summary['total']}₽

<i>Выберите меню:</i>"""
    
    current_time = datetime.now(MOSCOW_TZ).time()
    if current_time > time(16, 0):
        text += "\n⚠️ <i>Завтраки доступны только до 16:00</i>"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    for menu in available_menus:
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=menu['name'],
                callback_data=f"select_menu_{menu['id']}"
            )
        ])
    
    cart_button_text = f"🛒 Корзина ({cart_summary['item_count']})"
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="🔍 Поиск блюда", callback_data="search_dish"),
        types.InlineKeyboardButton(text=cart_button_text, callback_data="view_cart")
    ])
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="🔄 Обновить меню", callback_data="refresh_menu_all")
    ])
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="📋 PDF меню с барной картой", callback_data="menu_pdf"),
        types.InlineKeyboardButton(text="🎉 Банкетное меню", callback_data="menu_banquet")
    ])
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=bot)


@router.callback_query(F.data == "menu_delivery")
async def menu_delivery_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    if callback.message:
        user_main_message[callback.from_user.id] = callback.message.message_id
    
    await menu_delivery_handler(callback.from_user.id, callback.bot, state)

async def format_full_dish_description(dish: Dict) -> str:
    text = f"<b>{dish['name']}</b>\n\n"
    
    if dish.get('description'):
        text += f"📝 <b>Описание:</b> {dish['description']}\n\n"
    
    if dish.get('calories_per_100') is not None and dish.get('weight'):
        try:
            weight_str = str(dish['weight']).replace('г', '').replace('мл', '').strip()
            if weight_str.replace('.', '').isdigit():
                weight_grams = float(weight_str)
            else:
                weight_grams = 100
            
            calories_per_100 = float(dish['calories_per_100'])
            total_calories = (calories_per_100 * weight_grams) / 100
            
            text += f"🔥 <b>Общая калорийность:</b> {total_calories:.1f} ккал\n"
            text += f"⚖️ <b>Вес:</b> {dish['weight']}\n"
            text += f"📊 <b>На 100г:</b> {calories_per_100:.1f} ккал\n"
        except:
            if dish.get('calories'):
                text += f"🔥 <b>Ккал:</b> {dish['calories']:.1f} ккал\n"
    
    elif dish.get('calories'):
        text += f"🔥 <b>Ккал:</b> {dish['calories']:.1f} ккал\n"
    
    if dish.get('protein') or dish.get('fat') or dish.get('carbohydrate'):
        bju = []
        if dish.get('protein'): bju.append(f"Б {dish['protein']:.1f}г")
        if dish.get('fat'): bju.append(f"Ж {dish['fat']:.1f}г")
        if dish.get('carbohydrate'): bju.append(f"У {dish['carbohydrate']:.1f}г")
        if bju:
            text += f"🏋️ <b>БЖУ:</b> {' / '.join(bju)}\n"
    
    if dish.get('price', 0) > 0:
        text += f"\n💰 <b>Цена:</b> {dish['price']}₽\n"
    
    if dish.get('unit') and dish['unit'] != 'шт':
        text += f"📏 <b>Единица:</b> {dish['unit']}"
    
    return text

async def send_dish_photo(user_id: int, dish: Dict, menu_id: int, category_id: int, bot):
    try:
        caption = f"<b>{dish['name']}</b>\n"
        
        if dish.get('price', 0) > 0:
            caption += f"💰 <b>Цена:</b> {dish['price']}₽\n"
        
        if dish.get('weight'):
            caption += f"⚖️ <b>Вес:</b> {dish['weight']}\n"
        
        if dish.get('unit') and dish['unit'] != 'шт':
            caption += f"📏 <b>Единица:</b> {dish['unit']}"
        
        cart_summary = cart_manager.get_cart_summary(user_id)
        in_cart_count = 0
        for item in cart_summary['items']:
            if item['dish_id'] == dish['id']:
                in_cart_count = item['quantity']
                break
        
        cart_button_text = "Добавить в корзину 🛒"
        if in_cart_count > 0:
            cart_button_text = f"Добавлено ({in_cart_count}) ✅"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(text=cart_button_text, callback_data=f"add_to_cart_{menu_id}_{dish['id']}"),
                types.InlineKeyboardButton(text="📝 Полное описание", callback_data=f"view_full_desc_{menu_id}_{category_id}_{dish['id']}")
            ],
            [types.InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data=f"back_from_photos_{menu_id}")]
        ])
        
        image_path = dish.get('image_local_path')
        if not image_path and dish.get('image_filename'):
            image_path = os.path.join(config.MENU_IMAGES_DIR, dish['image_filename'])
        
        if image_path and os.path.exists(image_path):
            with open(image_path, 'rb') as photo_file:
                message = await bot.send_photo(
                    chat_id=user_id,
                    photo=BufferedInputFile(photo_file.read(), filename="dish.jpg"),
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
        else:
            message = await bot.send_message(
                chat_id=user_id,
                text=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        
        if user_id not in user_photo_messages:
            user_photo_messages[user_id] = []
        user_photo_messages[user_id].append(message.message_id)
        
    except Exception as e:
        logger.error(f"Ошибка отправки фото блюда {dish['id']}: {e}")

async def show_category_photos(user_id: int, menu_id: int, category_id: int, bot, state: FSMContext):
    dishes = menu_cache.get_category_items(menu_id, category_id)
    
    if not dishes:
        await update_message(user_id, "❌ В этой категории нет товаров",
                           reply_markup=keyboards.back_to_main(),
                           parse_mode="HTML",
                           bot=bot)
        return
    
    await state.update_data({
        'current_menu_id': menu_id,
        'current_category_id': category_id
    })
    
    categories = menu_cache.get_menu_categories(menu_id)
    category_name = ""
    display_name = ""
    
    for cat in categories:
        if cat['id'] == category_id:
            category_name = cat.get('name', 'Категория')
            display_name = cat.get('display_name', category_name)
            break
    
    if not display_name:
        try:
            cat_info = menu_cache.get_category_by_id(menu_id, category_id)
            if cat_info:
                display_name = cat_info.get('display_name', cat_info.get('name', 'Категория'))
            else:
                display_name = f"Категория {category_id}"
        except:
            display_name = f"Категория {category_id}"
    
    await cleanup_photo_messages(user_id, bot)
    
    text = f"""📸 <b>{display_name}</b>

<i>Все блюда категории:</i>
👆 Под каждой фотографией есть кнопки:
🛒 - добавить в корзину
📝 - полное описание
"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data=f"select_menu_{menu_id}")],
        [types.InlineKeyboardButton(text="🛒 Корзина", callback_data="view_cart")],
        [types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_main")]
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=bot)
    
    for dish in dishes:
        await send_dish_photo(user_id, dish, menu_id, category_id, bot)
    
    await state.set_state(MenuDeliveryStates.viewing_category)

@router.callback_query(F.data.startswith("select_menu_"))
async def select_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    try:
        menu_id = int(callback.data.replace("select_menu_", ""))
        
        if menu_id == 90:
            current_time = datetime.now(MOSCOW_TZ).time()
            start_time = time(8, 0)
            end_time = time(16, 0)
            
            if current_time < start_time or current_time > end_time:
                time_message = "⏰ Завтраки доступны с 8:00 до 16:00 по московскому времени"
                if current_time < start_time:
                    time_message = f"⏰ Завтраки станут доступны в 8:00 по московскому времени"
                else:
                    time_message = f"⏰ Завтраки доступны только до 16:00 по московскому времени"
                
                await callback.answer(f"{time_message}\n\nТекущее время: {current_time.strftime('%H:%M')}", show_alert=True)
                return
        
        await cleanup_photo_messages(callback.from_user.id, callback.bot)
        
        await state.update_data({
            'selected_menu_id': menu_id
        })
        
        await show_menu_categories(callback.from_user.id, menu_id, callback.bot, state)
        
    except Exception as e:
        logger.error(f"Ошибка выбора меню: {e}")
        await callback.answer("❌ Ошибка загрузки меню", show_alert=True)

async def show_menu_categories(user_id: int, menu_id: int, bot, state: FSMContext):
    categories = menu_cache.get_menu_categories(menu_id)
    
    if not categories:
        await update_message(user_id, "❌ В этом меню нет категорий",
                           reply_markup=keyboards.back_to_main(),
                           parse_mode="HTML",
                           bot=bot)
        return
    
    cart_summary = cart_manager.get_cart_summary(user_id)
    
    menu_name = ""
    available_menus = menu_cache.get_available_menus()
    for menu in available_menus:
        if menu['id'] == menu_id:
            menu_name = menu['name']
            break
    
    text = f"""📋 <b>{menu_name}</b>

<i>Выберите категорию:</i>

📊 <b>Всего категорий:</b> {len(categories)}"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    for i in range(0, len(categories), 2):
        row = []
        
        cat1 = categories[i]
        display_name1 = cat1.get('display_name', cat1.get('name', 'Категория'))
        button_text1 = f"{display_name1} ({cat1['item_count']})"
        
        row.append(types.InlineKeyboardButton(
            text=button_text1,
            callback_data=f"select_category_{menu_id}_{cat1['id']}"
        ))
        
        if i + 1 < len(categories):
            cat2 = categories[i + 1]
            display_name2 = cat2.get('display_name', cat2.get('name', 'Категория'))
            button_text2 = f"{display_name2} ({cat2['item_count']})"
            
            row.append(types.InlineKeyboardButton(
                text=button_text2,
                callback_data=f"select_category_{menu_id}_{cat2['id']}"
            ))
        
        keyboard.inline_keyboard.append(row)
    
    cart_button_text = f"🛒 Корзина ({cart_summary['item_count']})"
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="🔍 Поиск в меню", callback_data=f"search_in_menu_{menu_id}"),
        types.InlineKeyboardButton(text=cart_button_text, callback_data="view_cart")
    ])
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_delivery"),
        types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_main")
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=bot)

@router.callback_query(F.data.startswith("select_category_"))
async def select_category_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    try:
        parts = callback.data.replace("select_category_", "").split("_")
        if len(parts) != 2:
            return
        
        menu_id = int(parts[0])
        category_id = int(parts[1])
        
        await show_category_photos(callback.from_user.id, menu_id, category_id, callback.bot, state)
        
    except Exception as e:
        logger.error(f"Ошибка выбора категории: {e}")
        await callback.answer("❌ Ошибка загрузки категории", show_alert=True)

@router.callback_query(F.data.startswith("view_full_desc_"))
async def view_full_desc_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    try:
        parts = callback.data.replace("view_full_desc_", "").split("_")
        if len(parts) != 3:
            return
        
        menu_id = int(parts[0])
        category_id = int(parts[1])
        dish_id = int(parts[2])
        
        dish = menu_cache.get_dish_by_id(menu_id, dish_id)
        if not dish:
            await callback.answer("❌ Блюдо не найдено", show_alert=True)
            return
        
        cart_summary = cart_manager.get_cart_summary(callback.from_user.id)
        in_cart_count = 0
        for item in cart_summary['items']:
            if item['dish_id'] == dish_id:
                in_cart_count = item['quantity']
                break
        
        text = await format_full_dish_description(dish)
        
        cart_button_text = f"Добавлено ({in_cart_count}) ✅" if in_cart_count > 0 else "Добавить в корзину 🛒"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(text=cart_button_text, callback_data=f"add_to_cart_{menu_id}_{dish_id}"),
                types.InlineKeyboardButton(text="⬅️ Назад к фото", callback_data=f"back_to_photo_{menu_id}_{category_id}_{dish_id}")
            ]
        ])
        
        image_path = dish.get('image_local_path')
        if not image_path and dish.get('image_filename'):
            image_path = os.path.join(config.MENU_IMAGES_DIR, dish['image_filename'])
        
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, 'rb') as photo_file:
                    await callback.bot.edit_message_media(
                        chat_id=callback.from_user.id,
                        message_id=callback.message.message_id,
                        media=InputMediaPhoto(
                            media=BufferedInputFile(photo_file.read(), filename="dish.jpg"),
                            caption=text,
                            parse_mode="HTML"
                        ),
                        reply_markup=keyboard
                    )
            except Exception as e:
                logger.debug(f"Не удалось обновить фото на описание: {e}")
                await callback.bot.edit_message_caption(
                    chat_id=callback.from_user.id,
                    message_id=callback.message.message_id,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
        else:
            await callback.bot.edit_message_text(
                chat_id=callback.from_user.id,
                message_id=callback.message.message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        
        await state.update_data({
            'last_description_message_id': callback.message.message_id,
            'last_description_dish_id': dish_id,
            'last_description_menu_id': menu_id,
            'last_description_category_id': category_id
        })
        
    except Exception as e:
        logger.error(f"Ошибка показа описания: {e}")
        await callback.answer("❌ Ошибка загрузки описания", show_alert=True)

@router.callback_query(F.data.startswith("back_to_photo_"))
async def back_to_photo_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    try:
        parts = callback.data.replace("back_to_photo_", "").split("_")
        if len(parts) != 3:
            return
        
        menu_id = int(parts[0])
        category_id = int(parts[1])
        dish_id = int(parts[2])
        
        dish = menu_cache.get_dish_by_id(menu_id, dish_id)
        if not dish:
            await callback.answer("❌ Блюдо не найдено", show_alert=True)
            return
        
        caption = f"<b>{dish['name']}</b>\n"
        
        if dish.get('price', 0) > 0:
            caption += f"💰 <b>Цена:</b> {dish['price']}₽\n"
        
        if dish.get('weight'):
            caption += f"⚖️ <b>Вес:</b> {dish['weight']}\n"
        
        if dish.get('unit') and dish['unit'] != 'шт':
            caption += f"📏 <b>Единица:</b> {dish['unit']}"
        
        cart_summary = cart_manager.get_cart_summary(callback.from_user.id)
        in_cart_count = 0
        for item in cart_summary['items']:
            if item['dish_id'] == dish_id:
                in_cart_count = item['quantity']
                break
        
        cart_button_text = f"Добавлено ({in_cart_count}) ✅" if in_cart_count > 0 else "Добавить в корзину 🛒"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(text=cart_button_text, callback_data=f"add_to_cart_{menu_id}_{dish_id}"),
                types.InlineKeyboardButton(text="📝 Полное описание", callback_data=f"view_full_desc_{menu_id}_{category_id}_{dish_id}")
            ],
            [types.InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data=f"back_from_photos_{menu_id}")]
        ])
        
        image_path = dish.get('image_local_path')
        if not image_path and dish.get('image_filename'):
            image_path = os.path.join(config.MENU_IMAGES_DIR, dish['image_filename'])
        
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, 'rb') as photo_file:
                    await callback.bot.edit_message_media(
                        chat_id=callback.from_user.id,
                        message_id=callback.message.message_id,
                        media=InputMediaPhoto(
                            media=BufferedInputFile(photo_file.read(), filename="dish.jpg"),
                            caption=caption,
                            parse_mode="HTML"
                        ),
                        reply_markup=keyboard
                    )
            except Exception as e:
                logger.debug(f"Не удалось вернуть фото: {e}")
                await callback.bot.edit_message_caption(
                    chat_id=callback.from_user.id,
                    message_id=callback.message.message_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
        else:
            await callback.bot.edit_message_text(
                chat_id=callback.from_user.id,
                message_id=callback.message.message_id,
                text=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        
    except Exception as e:
        logger.error(f"Ошибка возврата к фото: {e}")
        await callback.answer("❌ Ошибка возврата к фото", show_alert=True)

@router.callback_query(F.data.startswith("back_from_detail_"))
async def back_from_detail_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    try:
        parts = callback.data.replace("back_from_detail_", "").split("_")
        if len(parts) != 2:
            return
        
        menu_id = int(parts[0])
        category_id = int(parts[1])
        
        try:
            await callback.bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        
        await show_category_photos(callback.from_user.id, menu_id, category_id, callback.bot, state)
        
    except Exception as e:
        logger.error(f"Ошибка возврата из деталей: {e}")

@router.callback_query(F.data.startswith("add_to_cart_"))
async def add_to_cart_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    try:
        parts = callback.data.replace("add_to_cart_", "").split("_")
        if len(parts) != 2:
            return
        
        menu_id = int(parts[0])
        dish_id = int(parts[1])
        
        user_id = callback.from_user.id
        registration_status = check_user_registration_fast(user_id)
        
        if registration_status != 'completed':
            # Запрашиваем регистрацию
            await ask_for_registration_phone(user_id, callback.bot, context="add_to_cart")
            
            await state.update_data({
                'context': 'add_to_cart',
                'pending_dish': {'menu_id': menu_id, 'dish_id': dish_id}
            })
            await state.set_state(RegistrationStates.waiting_for_phone)
            return
        
        # Если регистрация пройдена - добавляем в корзину
        dish = menu_cache.get_dish_by_id(menu_id, dish_id)
        
        if not dish:
            await callback.answer("❌ Блюдо не найдено", show_alert=True)
            return
        
        success = cart_manager.add_to_cart(
            user_id=user_id,
            dish_id=dish_id,
            dish_name=dish['name'],
            price=dish['price'],
            quantity=1,
            image_url=dish.get('image_url')
        )
        
        if success:
            cart_summary = cart_manager.get_cart_summary(user_id)
            new_count = 0
            for item in cart_summary['items']:
                if item['dish_id'] == dish_id:
                    new_count = item['quantity']
                    break
            
            try:
                cart_button_text = f"Добавлено ({new_count}) ✅"
                keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                    [
                        types.InlineKeyboardButton(text=cart_button_text, callback_data=f"add_to_cart_{menu_id}_{dish_id}"),
                        types.InlineKeyboardButton(text="📝 Полное описание", callback_data=f"view_full_desc_{menu_id}_{0}_{dish_id}")
                    ],
                    [types.InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data=f"back_from_photos_{menu_id}")]
                ])
                
                await callback.bot.edit_message_reply_markup(
                    chat_id=user_id,
                    message_id=callback.message.message_id,
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.debug(f"Не удалось обновить кнопку: {e}")
            
            await callback.answer(f"✅ {dish['name']} добавлен в корзину")
        else:
            await callback.answer("❌ Ошибка добавления в корзину", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка добавления в корзину: {e}")
        await callback.answer("❌ Ошибка добавления в корзину", show_alert=True)

async def show_cart(user_id: int, bot, state: FSMContext = None):
    await cleanup_photo_messages(user_id, bot)
    
    cart_summary = cart_manager.get_cart_summary(user_id)
    
    if not cart_summary['items']:
        text = "🛒 <b>Ваша корзина пуста</b>\n\nДобавьте блюда из меню!"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🍽️ К меню", callback_data="menu_delivery")],
            [types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_main")]
        ])
    else:
        text = f"🛒 <b>Ваша корзина ({cart_summary['item_count']})</b>\n\n"
        
        total = 0
        for i, item in enumerate(cart_summary['items'], 1):
            text += f"{i}. <b>{item['name']}</b>\n"
            text += f"   {item['quantity']} × {item['price']:.0f}₽ = {item['total_price']:.0f}₽\n\n"
            total += item['total_price']
        
        delivery_cost = int(database.get_setting('delivery_cost', config.DELIVERY_COST))
        free_delivery_min = int(database.get_setting('free_delivery_min', config.FREE_DELIVERY_MIN))
        delivery_time = database.get_setting('delivery_time', config.DELIVERY_TIME)
        
        
        text += f"<b>Сумма заказа:</b> {total:.0f}₽\n"
        
        # НЕ показываем "Итого к оплате" с доставкой, только сумму заказа
        # text += f"<b>Итого к оплате:</b> {final_total:.0f}₽\n\n"
        
        text += f"⏱️ <b>Время доставки:</b> {delivery_time}\n"
        text += "💳 <b>Оплата:</b> онлайн\n\n"
        
        text += "<i>Управление корзиной:</i>"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
        
        for item in cart_summary['items']:
            row = []
            
            if item['quantity'] > 1:
                row.append(
                    types.InlineKeyboardButton(
                        text=f"➖ {item['name'][:10]}...",
                        callback_data=f"cart_decrease_{item['dish_id']}"
                    )
                )
            else:
                row.append(
                    types.InlineKeyboardButton(
                        text=f"🗑️ {item['name'][:10]}...",
                        callback_data=f"cart_remove_{item['dish_id']}"
                    )
                )
            
            row.append(
                types.InlineKeyboardButton(
                    text=f"✏️ {item['quantity']}",
                    callback_data=f"cart_edit_{item['dish_id']}"
                )
            )
            
            row.append(
                types.InlineKeyboardButton(
                    text=f"➕",
                    callback_data=f"cart_increase_{item['dish_id']}"
                )
            )
            
            keyboard.inline_keyboard.append(row)
        
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text="🧹 Очистить корзину", callback_data="cart_clear_confirm")
        ])
        
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text="🚚 Оформить заказ", callback_data="start_order_from_cart")
        ])
        
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text="🍽️ Добавить ещё", callback_data="menu_delivery"),
            types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_main")
        ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)

@router.callback_query(F.data == "start_order_from_cart")
async def start_order_from_cart_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    cart_summary = cart_manager.get_cart_summary(user_id)
    
    if not cart_summary['items']:
        await callback.answer("🛒 Корзина пуста", show_alert=True)
        return
    
    # Регистрация будет проверяться в show_order_type_selection_from_cart
    await state.update_data(cart_summary=cart_summary)
    await show_order_type_selection_from_cart(user_id, callback.bot, state)

async def show_order_registration_from_cart(user_id: int, bot, state: FSMContext, cart_summary: Dict):
    text = """📝 <b>Необходима регистрация</b>

Для оформления заказа нам нужны ваши данные:
• Телефон для связи
• Имя для обращения

Это займет всего минуту!"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📞 Зарегистрироваться", callback_data="register_for_order_from_cart")],
        [types.InlineKeyboardButton(text="🛒 Вернуться в корзину", callback_data="view_cart")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
    
    await state.update_data({
        'context': 'order_from_cart',
        'cart_summary': cart_summary
    })

async def ask_for_comment(user_id: int, bot, state: FSMContext, message_id: int = None):
    """Запрос комментария к заказу"""
    
    text = """💬 <b>Комментарий к заказу</b>

Вы можете добавить комментарий к заказу:
• Позвонить перед доставкой
• Оставить у двери
• Указания курьеру
• Особенности для самовывоза
• Другое

Или нажмите "Пропустить", если комментарий не нужен."""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_comment")],
        [
            types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_order_type"),
            types.InlineKeyboardButton(text="🛒 В корзину", callback_data="view_cart")
        ]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot,
                            message_id=message_id)
    
    await state.set_state(DeliveryOrderStates.entering_comment)

async def ask_for_registration_before_order_type(user_id: int, bot, state: FSMContext, cart_summary: Dict):
    """Запрос регистрации перед выбором типа заказа"""
    
    text = """📝 <b>Необходима регистрация</b>

Для оформления заказа нам нужны ваши данные:
• Телефон для связи
• Имя для обращения

Это займет всего минуту!"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📞 Зарегистрироваться", callback_data="register_before_order_type")],
        [types.InlineKeyboardButton(text="🛒 Вернуться в корзину", callback_data="view_cart")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
    
    await state.update_data({
        'context': 'before_order_type',
        'cart_summary': cart_summary
    })

@router.callback_query(F.data == "register_before_order_type")
async def register_before_order_type_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    state_data = await state.get_data()
    cart_summary = state_data.get('cart_summary', {})
    
    # Используем ВАШУ функцию запроса телефона
    await ask_for_registration_phone(user_id, callback.bot, context="before_order_type")
    
    await state.update_data({
        'context': 'before_order_type',
        'cart_summary': cart_summary
    })
    
    # Используем ВАШЕ состояние ожидания телефона
    await state.set_state(RegistrationStates.waiting_for_phone)

async def show_order_type_selection_from_cart(user_id: int, bot, state: FSMContext):
    """Показ выбора типа заказа с проверкой регистрации"""
    
    # ПРОВЕРЯЕМ РЕГИСТРАЦИЮ ПЕРЕД ВЫБОРОМ ТИПА ЗАКАЗА
    registration_status = check_user_registration_fast(user_id)
    
    if registration_status != 'completed':
        state_data = await state.get_data()
        cart_summary = state_data.get('cart_summary', {})
        
        await ask_for_registration_before_order_type(user_id, bot, state, cart_summary)
        return
    
    # Если регистрация пройдена - показываем выбор типа заказа
    state_data = await state.get_data()
    cart_summary = state_data.get('cart_summary', {})
    
    total = cart_summary.get('total', 0)
    
    text = f"""🛒 <b>Оформление заказа</b>

<b>Ваш заказ ({cart_summary['item_count']} позиций):</b>
"""
    
    for item in cart_summary['items'][:3]:
        text += f"• {item['name']} - {item['quantity']} × {item['price']}₽\n"
    
    if cart_summary['item_count'] > 3:
        text += f"• ...и ещё {cart_summary['item_count'] - 3} позиций\n"
    
    text += f"\n<b>Сумма заказа:</b> {total}₽"
    text += f"\n\n<b>Выберите способ получения:</b>"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="🚚 Доставка", callback_data="order_delivery_from_cart"),
            types.InlineKeyboardButton(text="🏃 Самовывоз", callback_data="order_pickup_from_cart")
        ],
        [
            types.InlineKeyboardButton(text="⬅️ Назад в корзину", callback_data="view_cart")
        ]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
    
    await state.set_state(DeliveryOrderStates.choosing_order_type)

@router.callback_query(F.data == "order_delivery_from_cart")
async def order_delivery_from_cart_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    await state.update_data(order_type='delivery')
    await ask_for_address_from_cart(user_id, callback.bot, state)

async def ask_for_address_from_cart(user_id: int, bot, state: FSMContext):
    text = """📍 <b>Введите адрес доставки</b>

Напишите адрес доставки:
<i>Пример: Москва, ул. Ленина, д. 10, кв. 5</i>

Или отправьте геопозицию:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📍 Отправить местоположение", callback_data="share_location")],
        [
            types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_order_type_from_cart"),
            types.InlineKeyboardButton(text="🛒 В корзину", callback_data="view_cart")
        ]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
    
    await state.set_state(DeliveryOrderStates.entering_address)

async def show_address_selection_from_cart(user_id: int, bot, state: FSMContext):
    user_addresses = database.get_user_addresses(user_id)
    
    text = """📍 <b>Выберите адрес доставки</b>

<i>Сохраненные адреса:</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    for address in user_addresses[:5]:
        address_text = address['address'][:40]
        if len(address['address']) > 40:
            address_text += "..."
        
        button_text = f"🏠 {address_text}"
        if address.get('is_default'):
            button_text = f"⭐ {address_text}"
        
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=button_text,
                callback_data=f"use_saved_address_{address['id']}_from_cart"
            )
        ])
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="➕ Новый адрес", callback_data="enter_new_address_from_cart"),
        types.InlineKeyboardButton(text="📍 Отправить местоположение", callback_data="share_location_from_cart")
    ])
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_order_type_from_cart")
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)

@router.callback_query(F.data == "register_for_order_from_cart")
async def register_for_order_from_cart_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    state_data = await state.get_data()
    cart_summary = state_data.get('cart_summary', {})
    
    await ask_for_registration_phone(user_id, callback.bot, context="order_from_cart")
    
    await state.update_data({
        'context': 'order_from_cart',
        'cart_summary': cart_summary
    })
    
    await state.set_state(RegistrationStates.waiting_for_phone)

@router.callback_query(F.data.startswith("use_saved_address_"))
async def use_saved_address_from_cart_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    address_id = int(callback.data.replace("use_saved_address_", "").replace("_from_cart", ""))
    
    user_addresses = database.get_user_addresses(user_id)
    selected_address = None
    
    for address in user_addresses:
        if address['id'] == address_id:
            selected_address = address
            break
    
    if not selected_address:
        await callback.answer("❌ Адрес не найден", show_alert=True)
        return
    
    database.update_address_last_used(address_id)
    
    await state.update_data({
        'address_text': selected_address['address'],
        'latitude': selected_address['latitude'],
        'longitude': selected_address['longitude'],
        'apartment': selected_address['apartment'],
        'entrance': selected_address['entrance'],
        'floor': selected_address['floor'],
        'door_code': selected_address['door_code']
    })
    
    await check_delivery_availability_from_cart(user_id, callback.bot, state)

@router.callback_query(F.data == "enter_new_address_from_cart")
async def enter_new_address_from_cart_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await ask_for_address_from_cart(callback.from_user.id, callback.bot, state)

@router.callback_query(F.data == "share_location_from_cart")
async def share_location_from_cart_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    
    # Сначала удаляем старое сообщение с кнопками
    try:
        if callback.message:
            await callback.message.delete()
    except:
        pass
    
    # Очищаем все предыдущие временные сообщения
    if user_id in temp_messages:
        for msg_id in temp_messages[user_id][:]:
            try:
                await callback.bot.delete_message(user_id, msg_id)
            except:
                pass
        temp_messages[user_id] = []
    
    # Создаем сообщение с кнопкой отправки геолокации
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="📍 Отправить местоположение", request_location=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    temp_msg = await callback.bot.send_message(
        chat_id=user_id,
        text="📍 <b>Нажмите кнопку ниже, чтобы отправить местоположение</b>\n\n<i>Или напишите адрес текстом</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    # Сохраняем ID временного сообщения для удаления
    if user_id not in temp_messages:
        temp_messages[user_id] = []
    temp_messages[user_id].append(temp_msg.message_id)
    
    # Не переходим в состояние - ждем сообщение с location или текстом

async def check_delivery_availability_from_cart(user_id: int, bot, state: FSMContext):
    state_data = await state.get_data()
    address_text = state_data.get('address_text', '')
    latitude = state_data.get('latitude', 55.7558)
    longitude = state_data.get('longitude', 37.6176)
    cart_summary = state_data.get('cart_summary', {})
    applied_promocode = state_data.get('applied_promocode')
    
    # Получаем суммы
    cart_total = cart_summary.get('total', 0)  # Со скидкой
    original_cart_total = cart_summary.get('original_total', cart_total)  # Без скидки
    
    # ВАЖНО: Проверяем, чтобы сумма после скидки была не меньше 1000₽
    MIN_ORDER_SUM = 1000.0
    
    if cart_total < MIN_ORDER_SUM:
        text = f"""❌ <b>Минимальная сумма заказа для доставки - {MIN_ORDER_SUM}₽</b>

Ваш заказ: {cart_total}₽
Необходимо добавить товаров на: {MIN_ORDER_SUM - cart_total}₽

<b>Важно:</b> Минимальная сумма проверяется ПОСЛЕ применения скидки.
Если вы применили промокод, убедитесь что итоговая сумма не меньше {MIN_ORDER_SUM}₽."""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🍽️ Добавить товары", callback_data="menu_delivery")],
            [types.InlineKeyboardButton(text="✏️ Удалить промокод", callback_data="remove_promocode")],
            [types.InlineKeyboardButton(text="🏃 Самовывоз", callback_data="order_pickup_from_cart")],
            [types.InlineKeyboardButton(text="🛒 Корзина", callback_data="view_cart")]
        ])
        
        await update_main_message(user_id, text,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                bot=bot)
        return
    
    text = f"""📍 <b>Проверяем возможность доставки...</b>

<b>Адрес:</b> {address_text}
<b>Сумма заказа:</b> {cart_total}₽ (после скидки)
<b>Минимальная сумма:</b> {MIN_ORDER_SUM}₽ ✅

<i>Проверяем район и рассчитываем стоимость доставки...</i>"""
    
    await update_main_message(user_id, text,
                            parse_mode="HTML",
                            bot=bot)
    
    try:
        district_info = await get_district_for_address(address_text, latitude, longitude)
        
        # КРИТИЧЕСКАЯ ПРОВЕРКА: Если district_info имеет флаг 'unavailable'
        if district_info and district_info.get('unavailable'):
            # Адрес ВНЕ зоны доставки
            closest_district = district_info.get('closest_district')
            distance_km = district_info.get('distance_km', 0)
            closest_name = district_info.get('closest_district_name', 'не определен')
            
            text = f"""❌ <b>ДОСТАВКА НЕВОЗМОЖНА</b>

<b>Адрес:</b> {address_text}

⚠️ <b>Ваш адрес находится ВНЕ зоны доставки!</b>

📍 <b>Ближайшая зона доставки:</b> 
• Район: {closest_name}
• Расстояние: {distance_km:.1f} км от вас

🚫 <b>Причины недоступности доставки:</b>
1. Адрес за пределами обслуживаемых районов
2. Отсутствует доставка в ваш район
3. Слишком большое расстояние от ресторана

<b>Доступные варианты:</b>
• Самовывоз из ресторана
• Выберите другой адрес в зоне доставки
• Уточните возможность доставки по телефону: +7 (903) 748-80-80"""
            
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🏃 Самовывоз", callback_data="order_pickup_from_cart")],
                [types.InlineKeyboardButton(text="✏️ Изменить адрес", callback_data="enter_new_address_from_cart")],
                [types.InlineKeyboardButton(text="📞 Связаться", callback_data="contact_us")],
                [types.InlineKeyboardButton(text="🛒 В корзину", callback_data="view_cart")]
            ])
            
            await update_main_message(user_id, text,
                                    reply_markup=keyboard,
                                    parse_mode="HTML",
                                    bot=bot)
            return
        
        # Если district_info None (ошибка)
        if not district_info:
            await show_delivery_unavailable_from_cart(user_id, bot, state, address_text)
            return
        
        # Получаем минимальную сумму из района
        min_order_sum = float(district_info.get('minOrderSum', MIN_ORDER_SUM))
        
        # ДОПОЛНИТЕЛЬНАЯ проверка с учетом минимальной суммы района
        if cart_total < min_order_sum:
            text = f"""❌ <b>Минимальная сумма заказа для этого района - {min_order_sum}₽</b>

Ваш заказ: {cart_total}₽
Необходимо добавить товаров на: {min_order_sum - cart_total}₽

<b>Район:</b> {district_info.get('name', 'Ваш район')}
<b>Минимальная сумма:</b> {min_order_sum}₽"""
            
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🍽️ Добавить товары", callback_data="menu_delivery")],
                [types.InlineKeyboardButton(text="✏️ Удалить промокод", callback_data="remove_promocode")],
                [types.InlineKeyboardButton(text="🏃 Самовывоз", callback_data="order_pickup_from_cart")],
                [types.InlineKeyboardButton(text="🛒 Корзина", callback_data="view_cart")]
            ])
            
            await update_main_message(user_id, text,
                                    reply_markup=keyboard,
                                    parse_mode="HTML",
                                    bot=bot)
            return
        
        # Расчёт стоимости доставки
        delivery_cost, delivery_explanation = presto_api.calculate_delivery_cost_simple(
            district_info, 
            float(cart_total),                # сумма со скидкой
            float(original_cart_total)        # исходная сумма для проверки порога
        )
        
        await state.update_data({
            'district_info': district_info,
            'delivery_cost': delivery_cost,
            'delivery_explanation': delivery_explanation,
            'district_id': district_info.get('districtId'),
            'address_json': district_info.get('address_json'),
            'min_order_sum': min_order_sum
        })
        
        await show_delivery_available_from_cart(user_id, bot, state, address_text, delivery_cost, delivery_explanation)
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки доставки: {e}", exc_info=True)
        
        text = f"""❌ <b>Ошибка проверки доставки</b>

<b>Адрес:</b> {address_text}

Не удалось проверить возможность доставки.
Пожалуйста, выберите другой способ получения:"""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🏃 Самовывоз", callback_data="order_pickup_from_cart")],
            [types.InlineKeyboardButton(text="✏️ Изменить адрес", callback_data="enter_new_address_from_cart")],
            [types.InlineKeyboardButton(text="📞 Связаться", callback_data="contact_us")],
            [types.InlineKeyboardButton(text="🛒 В корзину", callback_data="view_cart")]
        ])
        
        await update_main_message(user_id, text,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                bot=bot)
@router.callback_query(F.data == "remove_promocode")
async def remove_promocode_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    
    # Очищаем промокод
    cart_manager.clear_promocode_from_cart(user_id)
    
    # Получаем корзину без скидки
    cart_summary = cart_manager.get_cart_summary(user_id)
    
    # Обновляем состояние
    await state.update_data({
        'applied_promocode': None,
        'cart_summary': cart_summary
    })
    
    await callback.answer("✅ Промокод удален")
    
    # Возвращаемся к выбору типа заказа
    await show_order_type_selection_from_cart(user_id, callback.bot, state)

@router.callback_query(F.data == "back_to_order_type_from_cart")
async def back_to_order_type_from_cart_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    await show_order_type_selection_from_cart(user_id, callback.bot, state)

@router.callback_query(F.data == "order_pickup_from_cart")
async def order_pickup_from_cart_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    await state.update_data(order_type='pickup')
    await ask_for_comment_from_cart(user_id, callback.bot, state)

async def ask_for_comment_from_cart(user_id: int, bot, state: FSMContext):
    text = """💬 <b>Комментарий к заказу</b>

Вы можете добавить комментарий к заказу:
• Позвонить перед доставкой
• Оставить у двери
• Указания курьеру
• Другое

Или нажмите "Пропустить", если комментарий не нужен."""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_comment_from_cart")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_order_type_from_cart")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
    
    # Устанавливаем правильное состояние
    await state.set_state(DeliveryOrderStates.entering_comment)

@router.callback_query(F.data == "skip_comment_from_cart")
async def skip_comment_from_cart_handler(callback: types.CallbackQuery, state: FSMContext):
    # Не показываем всплывающее сообщение
    # await callback.answer("✅ Комментарий пропущен")
    
    user_id = callback.from_user.id
    await state.update_data(comment='')
    
    await cleanup_temp_messages(user_id, callback.bot)
    
    # Передаем ID сообщения для редактирования
    await show_order_summary(user_id, callback.bot, state, callback.message.message_id)

@router.callback_query(F.data == "view_cart")
async def view_cart_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    await show_cart(user_id, callback.bot, state)

@router.callback_query(F.data.startswith("cart_decrease_"))
async def cart_decrease_handler(callback: types.CallbackQuery):
    await callback.answer()
    
    try:
        dish_id = int(callback.data.replace("cart_decrease_", ""))
        user_id = callback.from_user.id
        
        success = cart_manager.remove_from_cart(user_id, dish_id, quantity=1)
        
        if success:
            await callback.answer("➖ Уменьшено")
            await show_cart(user_id, callback.bot, None)
        else:
            await callback.answer("❌ Ошибка", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка уменьшения в корзине: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("cart_remove_"))
async def cart_remove_handler(callback: types.CallbackQuery):
    await callback.answer()
    
    try:
        dish_id = int(callback.data.replace("cart_remove_", ""))
        user_id = callback.from_user.id
        
        success = cart_manager.remove_from_cart(user_id, dish_id)
        
        if success:
            await callback.answer("🗑️ Удалено")
            await show_cart(user_id, callback.bot, None)
        else:
            await callback.answer("❌ Товар не найден", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка удаления из корзине: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("cart_increase_"))
async def cart_increase_handler(callback: types.CallbackQuery):
    await callback.answer()
    
    try:
        dish_id = int(callback.data.replace("cart_increase_", ""))
        user_id = callback.from_user.id
        
        cart_summary = cart_manager.get_cart_summary(user_id)
        dish_in_cart = None
        
        for item in cart_summary['items']:
            if item['dish_id'] == dish_id:
                dish_in_cart = item
                break
        
        if not dish_in_cart:
            await callback.answer("❌ Товар не найден", show_alert=True)
            return
        
        success = cart_manager.add_to_cart(
            user_id=user_id,
            dish_id=dish_id,
            dish_name=dish_in_cart['name'],
            price=dish_in_cart['price'],
            quantity=1
        )
        
        if success:
            await callback.answer("➕ Добавлено")
            await show_cart(user_id, callback.bot, None)
        else:
            await callback.answer("❌ Ошибка", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка увеличения в корзине: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("cart_edit_"))
async def cart_edit_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    try:
        dish_id = int(callback.data.replace("cart_edit_", ""))
        user_id = callback.from_user.id
        
        cart_summary = cart_manager.get_cart_summary(user_id)
        dish_in_cart = None
        
        for item in cart_summary['items']:
            if item['dish_id'] == dish_id:
                dish_in_cart = item
                break
        
        if not dish_in_cart:
            await callback.answer("❌ Товар не найдено", show_alert=True)
            return
        
        text = f"✏️ <b>Редактирование количества</b>\n\n"
        text += f"<b>{dish_in_cart['name']}</b>\n"
        text += f"Текущее количество: {dish_in_cart['quantity']}\n\n"
        text += f"Введите новое количество (от 1 до 99):"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="❌ Отмена", callback_data="view_cart")]
        ])
        
        await update_main_message(user_id, text,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                bot=callback.bot)
        
        await state.update_data({
            'editing_dish_id': dish_id,
            'editing_dish_name': dish_in_cart['name']
        })
        await state.set_state(MenuDeliveryStates.viewing_cart)
        
    except Exception as e:
        logger.error(f"Ошибка редактирования корзины: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.message(MenuDeliveryStates.viewing_cart)
async def process_cart_edit(message: types.Message, state: FSMContext):
    try:
        quantity_text = message.text.strip()
        
        if not quantity_text.isdigit():
            await message.answer("⚠️ Пожалуйста, введите число от 1 до 99")
            return
        
        quantity = int(quantity_text)
        
        if quantity < 1 or quantity > 99:
            await message.answer("⚠️ Количество должно быть от 1 до 99")
            return
        
        state_data = await state.get_data()
        dish_id = state_data.get('editing_dish_id')
        
        if not dish_id:
            await message.answer("❌ Ошибка: товар не найден")
            return
        
        success = cart_manager.update_item_quantity(
            user_id=message.from_user.id,
            dish_id=dish_id,
            new_quantity=quantity
        )
        
        if success:
            await message.answer(f"✅ Количество обновлено: {quantity}")
            await show_cart(message.from_user.id, message.bot, None)
        else:
            await message.answer("❌ Ошибка обновления количества")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки редактирования корзины: {e}")
        await message.answer("❌ Ошибка обработки")
        await state.clear()

@router.callback_query(F.data == "cart_clear_confirm")
async def cart_clear_confirm_handler(callback: types.CallbackQuery):
    await callback.answer()
    
    text = "⚠️ <b>Очистить корзину?</b>\n\nВсе товары будут удалены без возможности восстановления."
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Да, очистить", callback_data="cart_clear"),
            types.InlineKeyboardButton(text="❌ Нет, отмена", callback_data="view_cart")
        ]
    ])
    
    await update_main_message(callback.from_user.id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)

@router.callback_query(F.data == "cart_clear")
async def cart_clear_handler(callback: types.CallbackQuery):
    await callback.answer()
    
    user_id = callback.from_user.id
    cart_manager.clear_cart(user_id)
    
    await callback.answer("✅ Корзина очищена")
    await show_cart(user_id, callback.bot, None)

@router.callback_query(F.data.startswith("search_in_menu_"))
async def search_in_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    try:
        menu_id = int(callback.data.replace("search_in_menu_", ""))
        
        await cleanup_photo_messages(callback.from_user.id, callback.bot)
        
        await state.update_data(search_menu_id=menu_id)
        
        text = f"🔍 <b>Поиск в меню</b>\n\nВведите название блюда или его часть:"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"select_menu_{menu_id}")]
        ])
        
        await update_main_message(callback.from_user.id, text,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                bot=callback.bot)
        
        await state.set_state(MenuDeliveryStates.searching_dishes)
        
    except Exception as e:
        logger.error(f"Ошибка поиска в меню: {e}")
        await callback.answer("❌ Ошибка поиска", show_alert=True)

@router.callback_query(F.data == "search_dish")
async def search_dish_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    await cleanup_photo_messages(callback.from_user.id, callback.bot)
    
    text = "🔍 <b>Поиск блюд</b>\n\nВведите название блюда или его часть:"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_delivery")]
    ])
    
    await update_main_message(callback.from_user.id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)
    
    await state.set_state(MenuDeliveryStates.searching_dishes)

@router.message(MenuDeliveryStates.searching_dishes)
async def process_search_query(message: types.Message, state: FSMContext):
    search_text = message.text.strip()
    
    if not search_text or len(search_text) < 2:
        await message.answer("⚠️ Введите хотя бы 2 символа для поиска")
        return
    
    database.log_action(message.from_user.id, "menu_search", search_text)
    
    state_data = await state.get_data()
    menu_id = state_data.get('search_menu_id')
    
    results = menu_cache.search_dishes(search_text, menu_id)
    
    if not results:
        if menu_id:
            menu_name = ""
            available_menus = menu_cache.get_available_menus()
            for menu in available_menus:
                if menu['id'] == menu_id:
                    menu_name = menu['name']
                    break
            
            text = f"🔍 <b>Поиск в меню {menu_name}:</b> {search_text}\n\nНичего не найдено 😔\n\nПопробуйте другой запрос или посмотрите категории меню."
            
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🔍 Новый поиск", callback_data=f"search_in_menu_{menu_id}")],
                [types.InlineKeyboardButton(text="📂 Категории меню", callback_data=f"select_menu_{menu_id}")],
                [types.InlineKeyboardButton(text="🍽️ Все меню", callback_data="menu_delivery")]
            ])
        else:
            text = f"🔍 <b>Поиск:</b> {search_text}\n\nНичего не найдено 😔\n\nПопробуйте другой запрос."
            
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🔍 Новый поиск", callback_data="search_dish")],
                [types.InlineKeyboardButton(text="🍽️ Все меню", callback_data="menu_delivery")]
            ])
    else:
        results_by_menu = {}
        for dish in results:
            m_id = dish.get('menu_id')
            if m_id not in results_by_menu:
                results_by_menu[m_id] = []
            results_by_menu[m_id].append(dish)
        
        text = f"🔍 <b>Результаты поиска:</b> {search_text}\n\n"
        
        if menu_id:
            menu_results = results_by_menu.get(menu_id, [])
            text += f"Найдено блюд: {len(menu_results)}\n\nВыберите блюдо:"
        else:
            total_results = sum(len(r) for r in results_by_menu.values())
            text += f"Найдено блюд: {total_results}\n\n"
            
            for m_id, menu_dishes in results_by_menu.items():
                menu_name = menu_dishes[0].get('menu_name', f'Меню {m_id}')
                text += f"<b>{menu_name}:</b> {len(menu_dishes)} блюд\n"
            
            text += "\nВыберите блюдо:"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
        
        all_results = []
        if menu_id:
            all_results = results_by_menu.get(menu_id, [])
        else:
            for menu_dishes in results_by_menu.values():
                all_results.extend(menu_dishes)
        
        all_results.sort(key=lambda x: x.get('name', ''))
        
        for dish in all_results[:10]:
            menu_prefix = ""
            if not menu_id:
                menu_name_short = dish.get('menu_name', '?')[:3]
                menu_prefix = f"[{menu_name_short}] "
            
            dish_name = dish['name'][:25]
            price_text = f" - {dish['price']}₽" if dish.get('price', 0) > 0 else ""
            button_text = f"{menu_prefix}{dish_name}{price_text}"
            
            keyboard.inline_keyboard.append([
                types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"view_dish_search_{dish.get('menu_id')}_{dish.get('category_id', 0)}_{dish['id']}"
                )
            ])
        
        if len(all_results) > 10:
            keyboard.inline_keyboard.append([
                types.InlineKeyboardButton(
                    text=f"📄 Показать ещё ({len(all_results) - 10})",
                    callback_data=f"show_more_search_{search_text}_{menu_id if menu_id else 'all'}"
                )
            ])
        
        row = []
        if menu_id:
            row.append(types.InlineKeyboardButton(
                text="🔍 Новый поиск", 
                callback_data=f"search_in_menu_{menu_id}"
            ))
            row.append(types.InlineKeyboardButton(
                text="📂 Категории", 
                callback_data=f"select_menu_{menu_id}"
            ))
        else:
            row.append(types.InlineKeyboardButton(
                text="🔍 Новый поиск", 
                callback_data="search_dish"
            ))
        
        keyboard.inline_keyboard.append(row)
        
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text="🍽️ Все меню", callback_data="menu_delivery")
        ])
    
    await update_main_message(message.from_user.id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=message.bot)
    
    await state.clear()

@router.callback_query(F.data.startswith("view_dish_search_"))
async def view_dish_from_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    try:
        parts = callback.data.replace("view_dish_search_", "").split("_")
        if len(parts) != 3:
            return
        
        menu_id = int(parts[0])
        category_id = int(parts[1])
        dish_id = int(parts[2])
        
        dish = menu_cache.get_dish_by_id(menu_id, dish_id)
        if not dish:
            await callback.answer("❌ Блюдо не найдено", show_alert=True)
            return
        
        await cleanup_photo_messages(callback.from_user.id, callback.bot)
        
        text = f"""🔍 <b>Блюдо из поиска:</b>

{await format_full_dish_description(dish)}"""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🛒 Добавить в корзину", callback_data=f"add_to_cart_{menu_id}_{dish_id}")],
            [types.InlineKeyboardButton(text="⬅️ Назад к результатам", callback_data=f"back_to_search")]
        ])
        
        await update_message(callback.from_user.id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)
        
    except Exception as e:
        logger.error(f"Ошибка просмотра блюда из поиска: {e}")
        await callback.answer("❌ Ошибка загрузки блюда", show_alert=True)

@router.callback_query(F.data == "back_main")
async def back_main_callback(callback: types.CallbackQuery):
    await callback.answer()
    
    user_id = callback.from_user.id
    
    if user_id in user_message_history and user_message_history[user_id]:
        for msg_id in user_message_history[user_id][:]:
            try:
                await callback.bot.delete_message(user_id, msg_id)
            except Exception as e:
                logger.debug(f"Не удалось удалить фото {msg_id}: {e}")
        user_message_history[user_id] = []
    
    if user_id in user_document_history and user_document_history[user_id]:
        for doc_id in user_document_history[user_id][:]:
            try:
                await callback.bot.delete_message(user_id, doc_id)
            except Exception as e:
                logger.debug(f"Не удалось удалить документ {doc_id}: {e}")
        user_document_history[user_id] = []
    
    await cleanup_photo_messages(user_id, callback.bot)
    
    # Показываем главное меню вместо show_main_menu (избегаем циклического импорта)
    restaurant_name = database.get_setting('restaurant_name', config.RESTAURANT_NAME)
    start_message = database.get_setting('start_message', config.START_MESSAGE)
    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    restaurant_address = database.get_setting('restaurant_address', config.RESTAURANT_ADDRESS)
    restaurant_hours = database.get_setting('restaurant_hours', config.RESTAURANT_HOURS)
    
    clean_phone = clean_phone_for_link(restaurant_phone)
    
    text = f"""🎉 <b>{restaurant_name}</b>

{start_message}

<b>Контакты:</b>
📍 {restaurant_address}
📞 <a href="tel:{clean_phone}">{restaurant_phone}</a>
🕐 {restaurant_hours}"""
    
    # Используем динамическую клавиатуру с проверкой регистрации
    keyboard = keyboards.main_menu_with_profile(user_id)
    
    await update_message(user_id, text, reply_markup=keyboard, parse_mode="HTML", bot=callback.bot)

@router.callback_query(F.data == "menu_pdf")
async def menu_pdf_callback(callback: types.CallbackQuery, state: FSMContext):
    """Отправка PDF меню без проверки возраста"""
    await callback.answer("📤 Отправляем меню...")
    
    try:
        if os.path.exists(PDF_MENU_PATH):
            with open(PDF_MENU_PATH, 'rb') as file:
                message = await callback.bot.send_document(
                    chat_id=callback.from_user.id,
                    document=BufferedInputFile(
                        file.read(),
                        filename="Menu_Mashkov_Rest.pdf"
                    ),
                    caption="📋 <b>Полное меню ресторана с барной картой</b>\n\nЗдесь вы найдете все блюда и напитки нашего ресторана.",
                    parse_mode="HTML"
                )
            
            user_id = callback.from_user.id
            if user_id not in user_document_history:
                user_document_history[user_id] = []
            user_document_history[user_id].append(message.message_id)
            
            database.log_action(callback.from_user.id, "menu_pdf_downloaded")
            
            await asyncio.sleep(1)
            await menu_food_handler(callback.from_user.id, callback.bot)
            
        else:
            await callback.answer("❌ Файл меню не найден", show_alert=True)
            logger.error(f"Файл меню не найден: {PDF_MENU_PATH}")
            
            text = "❌ <b>Файл меню временно недоступен</b>\n\nПожалуйста, попробуйте позже или свяжитесь с администратором."
            
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="menu_pdf")],
                [types.InlineKeyboardButton(text="📞 Связаться", callback_data="contact_us")],
                [types.InlineKeyboardButton(text="🍽️ К меню ресторана", callback_data="menu_food")]
            ])
            
            await update_message(callback.from_user.id, text,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                bot=callback.bot)
            
    except Exception as e:
        logger.error(f"Ошибка отправки PDF меню: {e}")
        await callback.answer("❌ Ошибка отправки файла", show_alert=True)
        
        text = "❌ <b>Ошибка отправки файла</b>\n\nПожалуйста, попробуйте позже."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="menu_pdf")],
            [types.InlineKeyboardButton(text="🍽️ К меню ресторана", callback_data="menu_food")]
        ])
        
        await update_message(callback.from_user.id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)

@router.callback_query(F.data == "menu_banquet")
async def menu_banquet_callback(callback: types.CallbackQuery, state: FSMContext):
    """Отправка банкетного меню без проверки возраста"""
    await callback.answer("📤 Отправляем банкетное меню...")
    
    try:
        if os.path.exists(BANQUET_MENU_PATH):
            with open(BANQUET_MENU_PATH, 'rb') as file:
                message = await callback.bot.send_document(
                    chat_id=callback.from_user.id,
                    document=BufferedInputFile(
                        file.read(),
                        filename="Menu_Banket_Mashkov_Rest.xlsx"
                    ),
                    caption="🎉 <b>Банкетное меню</b>\n\nСпециальное предложение для мероприятий и праздников.",
                    parse_mode="HTML"
                )
            
            user_id = callback.from_user.id
            if user_id not in user_document_history:
                user_document_history[user_id] = []
            user_document_history[user_id].append(message.message_id)
            
            database.log_action(callback.from_user.id, "menu_banquet_downloaded")
            
            await asyncio.sleep(1)
            await menu_food_handler(callback.from_user.id, callback.bot)
            
        else:
            await callback.answer("❌ Файл банкетного меню не найден", show_alert=True)
            logger.error(f"Файл банкетного меню не найден: {BANQUET_MENU_PATH}")
            
            text = "❌ <b>Файл банкетного меню временно недоступен</b>\n\nПожалуйста, попробуйте позже или свяжитесь с администратором."
            
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="menu_banquet")],
                [types.InlineKeyboardButton(text="📞 Связаться", callback_data="contact_us")],
                [types.InlineKeyboardButton(text="🍽️ К меню ресторана", callback_data="menu_food")]
            ])
            
            await update_message(callback.from_user.id, text,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                bot=callback.bot)
            
    except Exception as e:
        logger.error(f"Ошибка отправки банкетного меню: {e}")
        await callback.answer("❌ Ошибка отправки файла", show_alert=True)
        
        text = "❌ <b>Ошибка отправки файла</b>\n\nПожалуйста, попробуйте позже."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="menu_banquet")],
            [types.InlineKeyboardButton(text="🍽️ К меню ресторана", callback_data="menu_food")]
        ])
        
        await update_message(callback.from_user.id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)

@router.callback_query(F.data == "refresh_menu_all")
async def refresh_menu_all_handler(callback: types.CallbackQuery):
    await callback.answer("🔄 Обновляем все меню...")
    
    try:
        await menu_cache.load_all_menus(force_update=True)
        
        await callback.answer("✅ Меню обновлены")
        await menu_delivery_handler(callback.from_user.id, callback.bot)
        
    except Exception as e:
        logger.error(f"Ошибка обновления меню: {e}")
        await callback.answer("❌ Ошибка обновления меню", show_alert=True)
        
        await show_static_menu(callback.from_user.id, callback.bot)

async def show_static_menu(user_id: int, bot):
    delivery_cost = database.get_setting('delivery_cost', config.DELIVERY_COST)
    free_delivery_min = database.get_setting('free_delivery_min', config.FREE_DELIVERY_MIN)
    delivery_time = database.get_setting('delivery_time', config.DELIVERY_TIME)
    
    text = f"""🚚 <b>Меню доставки (статические данные)</b>

Извините, динамическое меню временно недоступно.

💰 <b>Доставка:</b> {delivery_cost}₽ (бесплатно от {free_delivery_min}₽)
⏱️ <b>Время:</b> {delivery_time}

💡 <i>Для заказа напишите нам в чат или дождитесь восстановления онлайн-меню!</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="menu_delivery")],
        [types.InlineKeyboardButton(text="📞 Заказать по телефону", callback_data="contact_us")],
        [types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_main")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)

async def menu_food_handler(user_id: int, bot):
    database.log_action(user_id, "view_menu")
    
    text = """🍽️ <b>Меню ресторана</b>

Выберите что вас интересует:

<b>Меню доставки</b> — блюда с доставкой на дом
<b>PDF меню с барной картой</b> — полное меню для просмотра
<b>Банкетное меню</b> — для мероприятий и праздников

💡 <i>Если планируете мероприятие, посмотрите банкетное меню заранее!</i>"""
    
    await update_message(user_id, text,
                        reply_markup=keyboards.food_menu(),
                        parse_mode="HTML",
                        bot=bot)

@router.callback_query(F.data == "menu_food")
async def menu_food_callback(callback: types.CallbackQuery):
    await callback.answer()
    await cleanup_photo_messages(callback.from_user.id, callback.bot)
    await menu_food_handler(callback.from_user.id, callback.bot)

@router.callback_query(F.data == "make_order")
async def make_order_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await menu_delivery_handler(callback.from_user.id, callback.bot, state)

@router.callback_query(F.data.startswith("back_from_photos_"))
async def back_from_photos_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    try:
        menu_id = int(callback.data.replace("back_from_photos_", ""))
        
        await cleanup_photo_messages(callback.from_user.id, callback.bot)
        
        await show_menu_categories(callback.from_user.id, menu_id, callback.bot, state)
        
    except Exception as e:
        logger.error(f"Ошибка возврата из фото: {e}")
        await callback.answer("❌ Ошибка возврата", show_alert=True)

@router.callback_query(F.data == "start_order")
async def start_order_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    cart_summary = cart_manager.get_cart_summary(user_id)
    
    if not cart_summary['items']:
        await callback.answer("🛒 Корзина пуста", show_alert=True)
        return
    
    registration_status = check_user_registration_fast(user_id)
    
    if registration_status != 'completed':
        await ask_for_registration_phone(user_id, callback.bot, context="order")
        
        await state.update_data({
            'context': 'order',
            'cart_summary': cart_summary
        })
        
        await state.set_state(RegistrationStates.waiting_for_phone)
        return
    
    await state.update_data(cart_summary=cart_summary)
    await show_order_type_selection(user_id, callback.bot, state)

async def show_order_type_selection(user_id: int, bot, state: FSMContext):
    state_data = await state.get_data()
    cart_summary = state_data.get('cart_summary', {})
    
    total = cart_summary.get('total', 0)
    
    text = f"""🛒 <b>Оформление заказа</b>

<b>Ваш заказ ({cart_summary['item_count']} позиций):</b>
"""
    
    for item in cart_summary['items'][:3]:
        text += f"• {item['name']} - {item['quantity']} × {item['price']}₽\n"
    
    if cart_summary['item_count'] > 3:
        text += f"• ...и ещё {cart_summary['item_count'] - 3} позиций\n"
    
    text += f"\n<b>Сумма заказа:</b> {total}₽"
    text += f"\n\n<b>Выберите способ получения:</b>"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="🚚 Доставка", callback_data="order_delivery"),
            types.InlineKeyboardButton(text="🏃 Самовывоз", callback_data="order_pickup")
        ],
        [
            types.InlineKeyboardButton(text="🛒 Вернуться в корзину", callback_data="view_cart")
        ]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
    
    await state.set_state(DeliveryOrderStates.choosing_order_type)

@router.callback_query(F.data == "order_delivery")
async def order_delivery_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    await state.update_data(order_type='delivery')
    
    user_addresses = database.get_user_addresses(user_id)
    
    if user_addresses:
        await show_address_selection(user_id, callback.bot, state)
    else:
        await ask_for_address(user_id, callback.bot, state)

async def ask_for_address(user_id: int, bot, state: FSMContext):
    text = """📍 <b>Введите адрес доставки</b>

Напишите адрес доставки:
<i>Пример: Москва, бульвар Академика Ландау, 1</i>

Или отправьте геопозицию:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📍 Отправить местоположение", callback_data="share_location")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_order_type")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
    
    await state.set_state(DeliveryOrderStates.entering_address)

async def show_address_selection(user_id: int, bot, state: FSMContext):
    user_addresses = database.get_user_addresses(user_id)
    
    text = """📍 <b>Выберите адрес доставки</b>

<i>Сохраненные адреса:</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    for address in user_addresses[:5]:
        address_text = address['address'][:40]
        if len(address['address']) > 40:
            address_text += "..."
        
        button_text = f"🏠 {address_text}"
        if address.get('is_default'):
            button_text = f"⭐ {address_text}"
        
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=button_text,
                callback_data=f"use_saved_address_{address['id']}"
            )
        ])
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="➕ Новый адрес", callback_data="enter_new_address"),
        types.InlineKeyboardButton(text="📍 Отправить местоположение", callback_data="share_location")
    ])
    
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_order_type")
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)

@router.callback_query(F.data.startswith("use_saved_address_"))
async def use_saved_address_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    address_id = int(callback.data.replace("use_saved_address_", ""))
    
    user_addresses = database.get_user_addresses(user_id)
    selected_address = None
    
    for address in user_addresses:
        if address['id'] == address_id:
            selected_address = address
            break
    
    if not selected_address:
        await callback.answer("❌ Адрес не найден", show_alert=True)
        return
    
    database.update_address_last_used(address_id)
    
    await state.update_data({
        'address_text': selected_address['address'],
        'latitude': selected_address['latitude'],
        'longitude': selected_address['longitude'],
        'apartment': selected_address['apartment'],
        'entrance': selected_address['entrance'],
        'floor': selected_address['floor'],
        'door_code': selected_address['door_code']
    })
    
    await check_delivery_availability(user_id, callback.bot, state)

@router.callback_query(F.data == "enter_new_address")
async def enter_new_address_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await ask_for_address(callback.from_user.id, callback.bot, state)

@router.callback_query(F.data == "share_location")
async def share_location_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="📍 Отправить местоположение", request_location=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    temp_msg = await callback.bot.send_message(
        chat_id=user_id,
        text="📍 <b>Нажмите кнопку ниже, чтобы отправить местоположение</b>\n\n<i>Или напишите адрес текстом</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    await add_temp_message(user_id, temp_msg.message_id)
    await callback.answer("📍 Ожидаем ваше местоположение")

async def reverse_geocode_dadata(latitude: float, longitude: float) -> Optional[str]:
    """Преобразование координат в адрес через DaData"""
    try:
        DADATA_API_KEY = config.DADATA_API_KEY
        DADATA_SECRET_KEY = config.DADATA_SECRET_KEY
        
        if not DADATA_API_KEY or not DADATA_SECRET_KEY:
            logger.warning("⚠️ Нет ключей DaData для обратного геокодирования")
            return None
        
        url = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/geolocate/address"
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {DADATA_API_KEY}",
            "X-Secret": DADATA_SECRET_KEY
        }
        
        data = {
            "lat": latitude,
            "lon": longitude,
            "count": 1,
            "radius_meters": 50  # Более точный поиск
        }
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    
                    if result.get('suggestions') and len(result['suggestions']) > 0:
                        address = result['suggestions'][0].get('value', '')
                        logger.info(f"📍 DaData обратное геокодирование: {latitude}, {longitude} → {address}")
                        return address
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка обратного геокодирования DaData: {e}")
        return None

@router.message(F.content_type.in_({'location', 'text'}), DeliveryOrderStates.entering_address)
async def process_address_input_from_cart(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # УДАЛЯЕМ сообщение пользователя
    try:
        await message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение пользователя: {e}")
    
    # Очищаем временные сообщения
    await cleanup_temp_messages(user_id, message.bot)
    
    # Удаляем клавиатуру с кнопкой отправки местоположения БЕЗ сообщения
    remove_keyboard = types.ReplyKeyboardRemove()
    
    # Отправляем невидимое сообщение для удаления клавиатуры
    try:
        removal_msg = await message.answer(" ", reply_markup=remove_keyboard)
        await asyncio.sleep(0.1)  # Минимальная задержка
        await removal_msg.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить клавиатуру: {e}")
    
    if message.location:
        # ОБРАБОТКА ГЕОЛОКАЦИИ
        latitude = message.location.latitude
        longitude = message.location.longitude
        
        logger.info(f"📍 Получены координаты от пользователя: {latitude:.6f}, {longitude:.6f}")
        
        # Сохраняем координаты
        await state.update_data({
            'latitude': latitude,
            'longitude': longitude
        })
        
        # Пробуем получить адрес через DaData
        text = "📍 <b>Определяем адрес по вашим координатам...</b>"
        processing_msg = await message.bot.send_message(user_id, text, parse_mode="HTML")
        await add_temp_message(user_id, processing_msg.message_id)
        
        address_text = await reverse_geocode_dadata(latitude, longitude)
        
        if address_text:
            await state.update_data({'address_text': address_text})
            logger.info(f"📍 Адрес определен: {address_text}")
        else:
            # Если не удалось получить адрес, используем координаты
            address_text = f"Координаты: {latitude:.6f}, {longitude:.6f}"
            await state.update_data({'address_text': address_text})
        
        # Удаляем сообщение "📍 Определяем адрес..."
        await cleanup_temp_messages(user_id, message.bot)
        
        # Сразу переходим к проверке доставки
        await check_delivery_availability_from_cart(user_id, message.bot, state)
        
    else:
        # ОБРАБОТКА ТЕКСТОВОГО АДРЕСА
        address_text = message.text.strip()
        
        # Проверяем, не являются ли это координатами
        if ',' in address_text:
            parts = [part.strip() for part in address_text.split(',')]
            if len(parts) == 2:
                try:
                    lat = float(parts[0])
                    lon = float(parts[1])
                    if 40 <= lat <= 60 and 30 <= lon <= 40:  # Примерные границы Москвы
                        # Это координаты, обрабатываем как геолокацию
                        await state.update_data({
                            'latitude': lat,
                            'longitude': lon,
                            'address_text': address_text
                        })
                        await check_delivery_availability_from_cart(user_id, message.bot, state)
                        return
                except ValueError:
                    pass  # Не координаты, продолжаем как обычный адрес
        
        if not address_text or len(address_text) < 10:
            # Создаем временное сообщение об ошибке
            error_msg = await message.answer("⚠️ Пожалуйста, укажите полный адрес доставки (минимум 10 символов)")
            await add_temp_message(user_id, error_msg.message_id)
            await asyncio.sleep(2)
            await cleanup_temp_messages(user_id, message.bot)
            return
        
        logger.info(f"🔍 Получен адрес: {address_text}")
        
        # Сохраняем адрес (координаты будут определены позже)
        await state.update_data({
            'address_text': address_text,
            'latitude': None,
            'longitude': None
        })
        
        # Определяем координаты
        text = "📍 <b>Определяем координаты вашего адреса...</b>"
        processing_msg = await message.bot.send_message(user_id, text, parse_mode="HTML")
        await add_temp_message(user_id, processing_msg.message_id)
        
        coords = await geocode_address_local(address_text)
        
        if coords:
            await state.update_data({
                'latitude': coords['lat'],
                'longitude': coords['lon']
            })
            logger.info(f"✅ Координаты для '{address_text}': {coords['lat']}, {coords['lon']}")
        else:
            await state.update_data({
                'latitude': 55.7558,
                'longitude': 37.6176
            })
            logger.warning(f"⚠️ Не удалось определить координаты для '{address_text}'")
        
        # Удаляем сообщение "📍 Определяем координаты..."
        await cleanup_temp_messages(user_id, message.bot)
        
        # Проверяем доставку
        await check_delivery_availability_from_cart(user_id, message.bot, state)



async def show_delivery_unavailable_from_cart(user_id: int, bot, state: FSMContext, address_text: str):
    """Показ сообщения о недоступности доставки"""
    
    text = f"""❌ <b>Доставка невозможна</b>

<b>Адрес:</b> {address_text}

К сожалению, доставка по этому адресу не осуществляется.

<b>Причины:</b>
• Адрес вне зоны обслуживания
• Технические ограничения
• Нет доставки в ваш район

<b>Доступные варианты:</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✏️ Изменить адрес", callback_data="enter_new_address_from_cart")],
        [types.InlineKeyboardButton(text="🏃 Самовывоз", callback_data="order_pickup_from_cart")],
        [types.InlineKeyboardButton(text="📞 Связаться", callback_data="contact_us")],
        [types.InlineKeyboardButton(text="🛒 Корзина", callback_data="view_cart")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)

async def show_delivery_available_from_cart(user_id: int, bot, state: FSMContext, address_text: str, 
                                           delivery_cost: float, delivery_explanation: str):
    state_data = await state.get_data()
    cart_summary = state_data.get('cart_summary', {})
    cart_total = cart_summary.get('total', 0)  # Сумма со скидкой
    original_cart_total = cart_summary.get('original_total', cart_total)  # Исходная сумма без скидки
    min_order_sum = state_data.get('min_order_sum', 1000)  # Минимальная сумма
    
    # Рассчитываем итог
    total_with_delivery = cart_total + delivery_cost
    
    text = f"""✅ <b>Доставка возможна!</b>

<b>Адрес:</b> {address_text}
<b>Стоимость доставки:</b> {delivery_cost:.0f}₽
<b>Минимальная сумма заказа:</b> {min_order_sum}₽ ✅

<b>Сумма заказа:</b> {original_cart_total}₽"""

    # Добавляем информацию о скидке, если она есть
    if cart_total != original_cart_total:
        discount_amount = original_cart_total - cart_total
        text += f"\n<b>Скидка по промокоду:</b> -{discount_amount:.0f}₽"
        text += f"\n<b>Сумма со скидкой:</b> {cart_total}₽"
    
    text += f"""\n<b>Итого к оплате:</b> {total_with_delivery}₽

<b>Теперь заполните детали адреса (необязательно):</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🏠 Квартира/Офис", callback_data="set_apartment")],
        [types.InlineKeyboardButton(text="🚪 Подъезд", callback_data="set_entrance")],
        [types.InlineKeyboardButton(text="📈 Этаж", callback_data="set_floor")],
        [types.InlineKeyboardButton(text="🔑 Код двери", callback_data="set_door_code")],
        [
            types.InlineKeyboardButton(text="✅ Продолжить", callback_data="proceed_to_comment"),
            types.InlineKeyboardButton(text="✏️ Удалить промокод", callback_data="remove_promocode")
        ],
        [
            types.InlineKeyboardButton(text="🏠 Изменить адрес", callback_data="enter_new_address_from_cart"),
            types.InlineKeyboardButton(text="🛒 В корзину", callback_data="view_cart")
        ]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
    
    await state.set_state(DeliveryOrderStates.entering_address_details)

async def check_delivery_availability(user_id: int, bot, state: FSMContext):
    state_data = await state.get_data()
    address_text = state_data.get('address_text', '')
    latitude = state_data.get('latitude', 55.7558)
    longitude = state_data.get('longitude', 37.6176)
    cart_summary = state_data.get('cart_summary', {})
    
    text = f"""📍 <b>Проверяем возможность доставки...</b>

<b>Адрес:</b> {address_text}

<i>Проверяем район и рассчитываем стоимость доставки...</i>"""
    
    await update_main_message(user_id, text,
                            parse_mode="HTML",
                            bot=bot)
    
    try:
        district_info = await get_district_for_address(address_text, latitude, longitude)
        
        if not district_info:
            await show_delivery_unavailable(user_id, bot, state, address_text)
            return
        
        cart_total = cart_summary.get('total', 0)
        delivery_cost, delivery_explanation = presto_api.calculate_delivery_cost_simple(
            district_info, cart_total
        )
        
        await state.update_data({
            'district_info': district_info,
            'delivery_cost': delivery_cost,
            'district_id': district_info.get('districtId'),
            'address_json': district_info.get('address_json')
        })
        
        await show_delivery_available(user_id, bot, state, address_text, delivery_cost, delivery_explanation)
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки доставки: {e}")
        await state.update_data({
            'delivery_cost': 200,
            'district_id': None
        })
        await show_delivery_available(user_id, bot, state, address_text, 200, "200₽")

async def show_delivery_unavailable(user_id: int, bot, state: FSMContext, address_text: str):
    text = f"""❌ <b>Доставка невозможна</b>

К сожалению, доставка по адресу <b>{address_text}</b> не осуществляется.

Пожалуйста, выберите другой адрес или самовывоз."""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✏️ Изменить адрес", callback_data="enter_new_address")],
        [types.InlineKeyboardButton(text="🏃 Самовывоз", callback_data="order_pickup")],
        [types.InlineKeyboardButton(text="🛒 Корзина", callback_data="view_cart")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)

async def show_delivery_available(user_id: int, bot, state: FSMContext, address_text: str, 
                                 delivery_cost: float, delivery_explanation: str):
    state_data = await state.get_data()
    cart_summary = state_data.get('cart_summary', {})
    cart_total = cart_summary.get('total', 0)
    
    total_with_delivery = cart_total + delivery_cost
    
    text = f"""✅ <b>Доставка возможна!</b>

<b>Адрес:</b> {address_text}
<b>Стоимость доставки:</b> {delivery_explanation}
<b>Сумма заказа:</b> {cart_total}₽
<b>Итого к оплате:</b> {total_with_delivery}₽

<b>Теперь заполните детали адреса (необязательно):</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🏠 Квартира/Офис", callback_data="set_apartment")],
        [types.InlineKeyboardButton(text="🚪 Подъезд", callback_data="set_entrance")],
        [types.InlineKeyboardButton(text="📈 Этаж", callback_data="set_floor")],
        [types.InlineKeyboardButton(text="🔑 Код двери", callback_data="set_door_code")],
        [
            types.InlineKeyboardButton(text="✅ Продолжить", callback_data="proceed_to_comment"),
            types.InlineKeyboardButton(text="🏠 Изменить адрес", callback_data="enter_new_address")
        ]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
    
    await state.set_state(DeliveryOrderStates.entering_address_details)

@router.callback_query(F.data == "proceed_to_comment")
async def proceed_to_comment_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    
    state_data = await state.get_data()
    address_text = state_data.get('address_text', '')
    latitude = state_data.get('latitude')
    longitude = state_data.get('longitude')
    apartment = state_data.get('apartment', '')
    entrance = state_data.get('entrance', '')
    floor = state_data.get('floor', '')
    door_code = state_data.get('door_code', '')
    
    if address_text:
        database.save_user_address(
            user_id=user_id,
            address=address_text,
            latitude=latitude,
            longitude=longitude,
            apartment=apartment,
            entrance=entrance,
            floor=floor,
            door_code=door_code,
            is_default=True
        )
    
    # Передаем ID сообщения для редактирования
    await ask_for_comment(user_id, callback.bot, state, callback.message.message_id)

@router.callback_query(F.data == "skip_comment")
async def skip_comment_handler(callback: types.CallbackQuery, state: FSMContext):
    # Не показываем всплывающее сообщение
    # await callback.answer("✅ Комментарий пропущен")
    
    user_id = callback.from_user.id
    await state.update_data(comment='')
    
    await cleanup_temp_messages(user_id, callback.bot)
    
    # Передаем ID сообщения для редактирования
    await show_order_summary(user_id, callback.bot, state, callback.message.message_id)

@router.message(DeliveryOrderStates.entering_comment)
async def process_comment_input(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    comment_text = message.text.strip()
    
    # Удаляем введенное сообщение
    try:
        await message.delete()
    except:
        pass
    
    # Очищаем временные сообщения
    await cleanup_temp_messages(user_id, message.bot)
    
    # Сохраняем комментарий
    await state.update_data(comment=comment_text)
    
    # Показываем сводку заказа, передавая message_id из состояния
    state_data = await state.get_data()
    main_message_id = user_main_message.get(user_id)
    
    await show_order_summary(user_id, message.bot, state, main_message_id)

@router.callback_query(F.data == "order_pickup")
async def order_pickup_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    await state.update_data(order_type='pickup')
    
    # Передаем ID сообщения для редактирования
    await ask_for_comment(user_id, callback.bot, state, callback.message.message_id)

async def show_order_summary(user_id: int, bot, state: FSMContext, message_id: int = None):
    """Показ сводки заказа перед оплатой с правильным расчетом доставки"""
    
    # Очищаем временные сообщения
    await cleanup_temp_messages(user_id, bot)
    
    # Получаем данные из состояния
    state_data = await state.get_data()
    cart_summary = state_data.get('cart_summary', {})
    order_type = state_data.get('order_type', 'delivery')
    address_text = state_data.get('address_text', '')
    comment = state_data.get('comment', '')
    delivery_cost = state_data.get('delivery_cost', 0)
    delivery_explanation = state_data.get('delivery_explanation', '')
    applied_promocode = state_data.get('applied_promocode')
    
    # Получаем данные пользователя
    user_data = database.get_user_data(user_id)
    
    if not user_data:
        logger.error(f"❌ Нет данных пользователя {user_id}")
        await update_main_message(user_id, "❌ Ошибка: данные пользователя не найдены",
                                parse_mode="HTML", bot=bot, message_id=message_id)
        return
    
    # Получаем суммы из корзины
    cart_total = cart_summary.get('total', 0)  # Сумма со скидкой
    original_cart_total = cart_summary.get('original_total', cart_total)  # Исходная сумма без скидки
    discount_amount = 0
    
    # Если промокод применен, показываем скидку
    promocode_text = ""
    if applied_promocode and applied_promocode.get('valid'):
        discount_type = applied_promocode.get('type', 'percent')
        discount_percent = applied_promocode.get('discount_percent', 0)
        
        # Проверяем, применен ли промокод с ограничением по минимальной сумме
        if applied_promocode.get('applied_with_min_sum'):
            # Промокод применен с ограничением до минимальной суммы
            effective_discount = applied_promocode.get('effective_discount_amount', 0)
            original_discount = applied_promocode.get('original_discount_amount', effective_discount)
            min_sum = applied_promocode.get('min_order_sum_applied', 1000)
            
            discount_amount = effective_discount
            cart_total_after_discount = original_cart_total - discount_amount
            
            # Формируем текст с информацией об ограничении
            promocode_text = f"\n<b>Промокод (с ограничением):</b>"
            promocode_text += f"\n<i>Исходная скидка: {original_discount:.0f}₽</i>"
            promocode_text += f"\n<i>Применено: {effective_discount:.0f}₽ (до суммы {min_sum}₽)</i>"
            promocode_text += f"\n<b>Итоговая скидка:</b> -{effective_discount:.0f}₽"
            
            # Гарантируем, что сумма не меньше минимальной
            if cart_total_after_discount < min_sum:
                cart_total_after_discount = min_sum
                logger.warning(f"⚠️ Корректируем сумму до минимальной: {cart_total_after_discount}₽")
        else:
            # Обычный промокод без ограничений
            if discount_type == 'percent':
                # Процентная скидка
                discount_amount = (original_cart_total * discount_percent) / 100
                promocode_value = f"{discount_percent}%"
            else:
                # Фиксированная скидка
                original_discount = applied_promocode.get('original_discount_amount', 0)
                discount_amount = min(original_discount, original_cart_total)
                promocode_value = f"{original_discount}₽"
            
            cart_total_after_discount = original_cart_total - discount_amount
            promocode_text = f"\n<b>Промокод ({promocode_value}):</b> -{discount_amount:.0f}₽"
    else:
        cart_total_after_discount = cart_total
        promocode_text = ""
    
    # Рассчитываем стоимость доставки на основе ИСХОДНОЙ суммы
    if order_type == 'delivery':
        # Получаем district_info из состояния
        district_info = state_data.get('district_info', {})
        if district_info and delivery_cost == 0:
            # Если delivery_cost еще не рассчитан (0), пересчитываем
            delivery_cost, delivery_explanation = presto_api.calculate_delivery_cost_simple(
                district_info, 
                float(cart_total_after_discount),       # сумма со скидкой
                float(original_cart_total)               # исходная сумма для проверки порога
            )
            await state.update_data({
                'delivery_cost': delivery_cost,
                'delivery_explanation': delivery_explanation
            })
        
        # Рассчитываем итоговую сумму
        final_total = cart_total_after_discount + delivery_cost
        
        # Формируем текст доставки
        if delivery_cost == 0:
            delivery_text = "🎉 Бесплатно"
        else:
            delivery_text = f"{delivery_cost:.0f}₽"
    else:
        # Самовывоз - доставка бесплатная
        delivery_cost = 0
        delivery_text = "0₽ (самовывоз)"
        final_total = cart_total_after_discount
    
    # Формируем текст сообщения
    text = f"""✅ <b>Оформление заказа</b>

<b>Тип:</b> {'🚚 Доставка' if order_type == 'delivery' else '🏃 Самовывоз'}
"""
    
    if order_type == 'delivery':
        text += f"<b>Адрес:</b> {address_text}\n"
    else:
        text += f"<b>Самовывоз:</b> бул. Академика Ландау, 1\n"
    
    text += f"\n<b>Ваш заказ ({cart_summary['item_count']} позиций):</b>\n"
    
    # Показываем позиции заказа (первые 3 для краткости)
    for i, item in enumerate(cart_summary['items'][:3], 1):
        item_total = item['quantity'] * item['price']
        text += f"{i}. <b>{item['name']}</b>\n"
        text += f"   {item['quantity']} × {item['price']}₽ = {item_total}₽\n"
    
    if cart_summary['item_count'] > 3:
        other_items_count = cart_summary['item_count'] - 3
        other_items_total = sum(item['quantity'] * item['price'] 
                               for item in cart_summary['items'][3:])
        text += f"   ...и ещё {other_items_count} позиций на {other_items_total}₽\n"
    
    # СУЩЕСТВЕННОЕ ИЗМЕНЕНИЕ: показываем исходную сумму и скидку отдельно
    text += f"\n<b>Сумма заказа:</b> {original_cart_total}₽"
    text += promocode_text
    
    if order_type == 'delivery':
        text += f"\n<b>Доставка:</b> {delivery_text}"
        if delivery_explanation and "добавьте" in delivery_explanation:
            text += f"\n<i>{delivery_explanation}</i>"
    
    text += f"\n<b>Итого к оплате:</b> {final_total:.0f}₽"
    
    # Показываем информацию о минимальной сумме если нужно
    min_order_sum = state_data.get('min_order_sum', 1000)
    if order_type == 'delivery' and cart_total_after_discount < min_order_sum:
        text += f"\n\n⚠️ <i>Минимальная сумма заказа для доставки: {min_order_sum}₽</i>"
    
    if comment:
        text += f"\n\n<b>Комментарий:</b> {comment}"
    
    # Данные пользователя
    text += f"\n\n<b>Ваши данные:</b>"
    text += f"\n👤 {user_data.get('full_name', 'Не указано')}"
    text += f"\n📞 {user_data.get('phone', 'Не указан')}"
    
    # Время и оплата
    text += f"\n\n⏱️ <b>Время {'доставки' if order_type == 'delivery' else 'приготовления'}:</b> 45-60 минут"
    text += "\n💳 <b>Оплата:</b> онлайн"
    
    # Формируем клавиатуру
    keyboard_buttons = []
    
    # Кнопка оплаты
    keyboard_buttons.append([
        types.InlineKeyboardButton(
            text="💳 Оплатить и оформить заказ", 
            callback_data=f"process_payment_{order_type}"
        )
    ])
    
    # Кнопка промокода (если не применен или можно изменить)
    if not applied_promocode or applied_promocode.get('applied_with_min_sum'):
        keyboard_buttons.append([
            types.InlineKeyboardButton(text="🎁 Ввести промокод", callback_data="enter_promocode")
        ])
    
    # Кнопки управления
    keyboard_buttons.append([
        types.InlineKeyboardButton(text="✏️ Изменить данные", callback_data="edit_user_data"),
        types.InlineKeyboardButton(text="🛒 Корзина", callback_data="view_cart")
    ])
    
    # Кнопка "Удалить промокод" если применен
    if applied_promocode and applied_promocode.get('valid'):
        keyboard_buttons.append([
            types.InlineKeyboardButton(text="❌ Удалить промокод", callback_data="remove_promocode_from_summary")
        ])
    
    # Кнопка "Назад"
    keyboard_buttons.append([
        types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_comment")
    ])
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    # Обновляем сообщение
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot,
                            message_id=message_id)
    
    # Обновляем состояние
    await state.set_state(DeliveryOrderStates.final_confirmation)
  
@router.callback_query(F.data == "remove_promocode_from_summary")
async def remove_promocode_from_summary_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    
    # Очищаем промокод из корзины
    cart_manager.clear_promocode_from_cart(user_id)
    
    # Получаем корзину без скидки
    cart_summary = cart_manager.get_cart_summary(user_id)
    
    # Обновляем состояние
    await state.update_data({
        'applied_promocode': None,
        'cart_summary': cart_summary
    })
    
    # Показываем обновленную сводку
    await show_order_summary(user_id, callback.bot, state, callback.message.message_id)  
async def remove_applied_promocode(user_id: int, state: FSMContext):
    """Удаление примененного промокода"""
    state_data = await state.get_data()
    cart_summary = state_data.get('cart_summary', {})
    
    if cart_summary.get('original_total'):
        # Восстанавливаем исходную сумму
        updated_cart_summary = {
            **cart_summary,
            'total': cart_summary['original_total']
        }
        
        await state.update_data({
            'applied_promocode': None,
            'cart_summary': updated_cart_summary
        })
        
        # Очищаем промокод в менеджере корзины
        cart_manager.clear_promocode_from_cart(user_id)

@router.callback_query(F.data == "enter_promocode")
async def enter_promocode_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    
    text = """🎁 <b>Введите промокод</b>

Если у вас есть промокод, введите его ниже:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад к заказу", callback_data="back_to_summary")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)
    
    await state.set_state(DeliveryOrderStates.entering_promocode)
@router.callback_query(F.data == "back_to_summary")
async def back_to_summary_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    
    # Показываем сводку заказа
    await show_order_summary(user_id, callback.bot, state, callback.message.message_id)
@router.message(DeliveryOrderStates.entering_promocode)
async def process_promocode_input(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    promocode_text = message.text.strip().upper()
    
    try:
        await message.delete()
    except:
        pass
    
    state_data = await state.get_data()
    cart_summary = state_data.get('cart_summary', {})
    original_cart_total = cart_summary.get('original_total', cart_summary.get('total', 0))
    
    # Проверяем промокод на основе ИСХОДНОЙ суммы
    validation_result = database.validate_promocode_for_user(promocode_text, user_id, original_cart_total)
    
    if validation_result.get('valid'):
        # Рассчитываем новую сумму с учетом скидки
        discount_type = validation_result.get('type', 'percent')
        discount_percent = validation_result.get('discount_percent', 0)
        discount_amount = validation_result.get('discount_amount', 0)
        
        # Рассчитываем сумму после скидки
        cart_total_after_discount = original_cart_total - discount_amount
        
        # ВАЖНО: Проверяем минимальную сумму 1000₽
        MIN_ORDER_SUM = 1000.0
        
        if cart_total_after_discount < MIN_ORDER_SUM:
            # ПРЕДЛАГАЕМ ВЫБОР
            need_to_add = MIN_ORDER_SUM - cart_total_after_discount
            
            text = f"""⚠️ <b>Внимание: минимальная сумма заказа 1000₽</b>

Ваш заказ: {original_cart_total}₽
Скидка по промокоду: -{discount_amount:.0f}₽
Сумма после скидки: {cart_total_after_discount}₽

<b>После применения промокода сумма станет меньше минимальной (1000₽).</b>

Выберите действие:
1. <b>Применить промокод, но установить минимальную сумму 1000₽</b>
   • Вы заплатите 1000₽ вместо {cart_total_after_discount}₽
   • Экономия составит {original_cart_total - 1000}₽ вместо {discount_amount}₽
   
2. <b>Отказаться от промокода</b>
   • Оплатите полную сумму: {original_cart_total}₽
   • Сохраните промокод для следующего заказа"""

            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text=f"✅ Применить с минимальной суммой 1000₽",
                    callback_data=f"apply_promo_with_min_{promocode_text}_{original_cart_total}_{discount_amount}"
                )],
                [types.InlineKeyboardButton(
                    text="❌ Отказаться от промокода",
                    callback_data="cancel_promocode"
                )],
                [types.InlineKeyboardButton(
                    text="🛒 Добавить товары на {need_to_add:.0f}₽",
                    callback_data="add_more_items_from_promo"
                )]
            ])
            
            # Сохраняем временные данные
            await state.update_data({
                'pending_promocode': {
                    'code': promocode_text,
                    'validation_result': validation_result,
                    'original_total': original_cart_total,
                    'discount_amount': discount_amount,
                    'cart_after_discount': cart_total_after_discount,
                    'min_order_sum': MIN_ORDER_SUM
                }
            })
            
            await update_main_message(user_id, text,
                                    parse_mode="HTML",
                                    bot=message.bot)
            return
        
        # Если сумма после скидки >= 1000₽, применяем промокод как обычно
        await apply_promocode_successfully(user_id, state, cart_summary, 
                                         original_cart_total, discount_amount, 
                                         validation_result, promocode_text, message.bot)
        
    else:
        text = f"""❌ <b>Промокод недействителен</b>

{validation_result.get('message', 'Неверный промокод')}"""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Назад к заказу", callback_data="back_to_summary")]
        ])
        
        await update_main_message(user_id, text,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                bot=message.bot)
        
        await asyncio.sleep(2)
        await show_order_summary(user_id, message.bot, state)

async def apply_promocode_successfully(user_id: int, state: FSMContext, cart_summary: Dict,
                                     original_total: float, discount_amount: float,
                                     validation_result: Dict, promocode_text: str, bot):
    """Применение промокода без проблем с минимальной суммой"""
    
    # Рассчитываем новую сумму
    new_cart_total = original_total - discount_amount
    
    # Обновляем данные в состоянии
    updated_cart_summary = {
        **cart_summary,
        'total': new_cart_total,
        'original_total': original_total
    }
    
    await state.update_data({
        'applied_promocode': validation_result,
        'cart_summary': updated_cart_summary
    })
    
    # Применяем скидку к корзине в менеджере
    discount_type = validation_result.get('type', 'percent')
    discount_value = discount_amount if discount_type == 'amount' else validation_result.get('discount_percent', 0)
    
    cart_manager.apply_promocode_to_cart(user_id, discount_value, discount_type)
    
    discount_display = f"{discount_amount}₽" if discount_type == 'amount' else f"{discount_value}%"
    
    text = f"""✅ <b>Промокод принят!</b>

{validation_result.get('message')}

<b>Скидка:</b> {discount_display}
<b>Сумма скидки:</b> {discount_amount:.0f}₽
<b>Сумма заказа:</b> {original_total}₽ → {new_cart_total}₽"""
    
    database.mark_promocode_used(promocode_text)
    
    await update_main_message(user_id, text,
                            parse_mode="HTML",
                            bot=bot)
    
    await asyncio.sleep(2)
    await show_order_summary(user_id, bot, state)
def check_min_order_sum_with_promocode(original_total: float, discount_amount: float, 
                                      min_order_sum: float = 1000.0) -> Dict:
    """
    Проверяет, не нарушает ли применение промокода минимальную сумму
    
    Returns:
        {
            'valid': bool,
            'cart_after_discount': float,
            'need_to_add': float,
            'effective_discount': float,
            'max_allowed_discount': float
        }
    """
    cart_after_discount = original_total - discount_amount
    
    if cart_after_discount >= min_order_sum:
        return {
            'valid': True,
            'cart_after_discount': cart_after_discount,
            'need_to_add': 0,
            'effective_discount': discount_amount,
            'max_allowed_discount': discount_amount
        }
    else:
        need_to_add = min_order_sum - cart_after_discount
        max_allowed_discount = original_total - min_order_sum
        
        if max_allowed_discount < 0:
            max_allowed_discount = 0
        
        return {
            'valid': False,
            'cart_after_discount': cart_after_discount,
            'need_to_add': need_to_add,
            'effective_discount': max_allowed_discount,
            'max_allowed_discount': max_allowed_discount,
            'min_order_sum': min_order_sum
        }
@router.callback_query(F.data.startswith("apply_promo_with_min_"))
async def apply_promo_with_min_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    try:
        # Парсим данные из callback_data
        parts = callback.data.replace("apply_promo_with_min_", "").split("_")
        promocode_text = parts[0]
        original_total = float(parts[1])
        original_discount_amount = float(parts[2])
        
        MIN_ORDER_SUM = 1000.0
        
        # Рассчитываем новую скидку (до 1000₽)
        max_allowed_discount = original_total - MIN_ORDER_SUM
        if max_allowed_discount < 0:
            max_allowed_discount = 0
        
        # Если исходная скидка больше допустимой, ограничиваем её
        effective_discount = min(original_discount_amount, max_allowed_discount)
        
        # Новая сумма заказа (ровно 1000₽)
        new_cart_total = MIN_ORDER_SUM
        
        # Получаем данные из состояния
        state_data = await state.get_data()
        cart_summary = state_data.get('cart_summary', {})
        pending_promocode = state_data.get('pending_promocode', {})
        
        # Создаем модифицированный validation_result
        validation_result = pending_promocode.get('validation_result', {})
        modified_validation = {
            **validation_result,
            'applied_with_min_sum': True,
            'original_discount_amount': original_discount_amount,
            'effective_discount_amount': effective_discount,
            'min_order_sum_applied': MIN_ORDER_SUM
        }
        
        # Обновляем корзину
        updated_cart_summary = {
            **cart_summary,
            'total': new_cart_total,
            'original_total': original_total,
            'min_sum_applied': True
        }
        
        await state.update_data({
            'applied_promocode': modified_validation,
            'cart_summary': updated_cart_summary,
            'pending_promocode': None
        })
        
        # Применяем скидку к корзине (ограниченную версию)
        cart_manager.apply_promocode_to_cart(callback.from_user.id, effective_discount, 'amount')
        
        database.mark_promocode_used(promocode_text)
        
        text = f"""✅ <b>Промокод применен с ограничением!</b>

⚠️ <b>Из-за минимальной суммы 1000₽ скидка была скорректирована:</b>

<b>Исходная сумма:</b> {original_total}₽
<b>Исходная скидка:</b> {original_discount_amount}₽
<b>Допустимая скидка:</b> {effective_discount}₽ (до суммы 1000₽)
<b>Сумма к оплате:</b> {new_cart_total}₽

<i>Вы экономите {effective_discount}₽ вместо {original_discount_amount}₽</i>"""
        
        await update_main_message(callback.from_user.id, text,
                                parse_mode="HTML",
                                bot=callback.bot)
        
        await asyncio.sleep(3)
        await show_order_summary(callback.from_user.id, callback.bot, state)
        
    except Exception as e:
        logger.error(f"❌ Ошибка применения промокода с минимальной суммой: {e}")
        await callback.answer("❌ Ошибка применения промокода", show_alert=True)

@router.callback_query(F.data == "cancel_promocode")
async def cancel_promocode_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("❌ Промокод отменен")
    
    user_id = callback.from_user.id
    
    # Очищаем pending промокод
    await state.update_data({
        'pending_promocode': None
    })
    
    await show_order_summary(user_id, callback.bot, state)

@router.callback_query(F.data == "add_more_items_from_promo")
async def add_more_items_from_promo_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    
    # Сохраняем данные о промокоде
    state_data = await state.get_data()
    pending_promocode = state_data.get('pending_promocode', {})
    
    # Очищаем pending промокод
    await state.update_data({
        'pending_promocode': None
    })
    
    # Показываем меню
    await menu_delivery_handler(user_id, callback.bot, state)
    
    # Сообщаем пользователю
    need_to_add = 1000 - pending_promocode.get('cart_after_discount', 0)
    text = f"""📝 <b>Добавьте товары на {need_to_add:.0f}₽</b>

После добавления вернитесь в корзину и снова введите промокод."""
    
    temp_msg = await callback.bot.send_message(
        chat_id=user_id,
        text=text,
        parse_mode="HTML"
    )
    
    await asyncio.sleep(3)
    try:
        await callback.bot.delete_message(user_id, temp_msg.message_id)
    except:
        pass

@router.callback_query(F.data.startswith("process_payment_"))
async def process_payment_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    order_type = callback.data.replace("process_payment_", "")
    user_id = callback.from_user.id
    state_data = await state.get_data()
    
    cart_summary = state_data.get('cart_summary', {})
    applied_promocode = state_data.get('applied_promocode')
    address_text = state_data.get('address_text', '')
    comment = state_data.get('comment', '')
    delivery_cost = state_data.get('delivery_cost', 0)
    district_info = state_data.get('district_info', {})
    
    user_data = database.get_user_data(user_id)
    
    if not user_data or not user_data.get('phone'):
        await callback.answer("❌ Необходимо указать телефон", show_alert=True)
        return
    
    text = "⏳ <b>Создаем заказ...</b>"
    await update_main_message(user_id, text,
                            parse_mode="HTML",
                            bot=callback.bot)
    
    customer_data = {
        'user_id': user_id,
        'name': user_data.get('full_name', 'Клиент').split()[0] if user_data.get('full_name') else 'Клиент',
        'lastname': ' '.join(user_data.get('full_name', '').split()[1:]) if user_data.get('full_name') else '',
        'phone': user_data.get('phone'),
        'email': user_data.get('email', '')
    }
    
    delivery_data = {}
    if order_type == 'delivery':
        delivery_data = {
            'address_full': address_text,
            'address_text': address_text,
            'locality': 'Москва',
            'latitude': state_data.get('latitude', 55.7558),
            'longitude': state_data.get('longitude', 37.6176),
            'apartment': state_data.get('apartment', ''),
            'entrance': state_data.get('entrance', ''),
            'floor': state_data.get('floor', ''),
            'door_code': state_data.get('door_code', ''),
            'district_id': state_data.get('district_id'),
            'address_json': state_data.get('address_json')
        }
    
    order_comment = f"Заказ из Telegram бота"
    if comment:
        order_comment += f"\nКомментарий: {comment}"
    
    # Определяем скидку
    discount_amount = 0
    discount_type = 'percent'
    discount_percent = 0
    
    if applied_promocode and applied_promocode.get('valid'):
        discount_amount = applied_promocode.get('discount_amount', 0)
        discount_type = applied_promocode.get('type', 'percent')
        discount_percent = applied_promocode.get('discount_percent', 0)
        
        if discount_type == 'percent':
            order_comment += f"\nПромокод: {applied_promocode.get('code')} ({discount_percent}%)"
        else:
            order_comment += f"\nПромокод: {applied_promocode.get('code')} ({discount_amount:.0f}₽)"
    
    # Подготавливаем позиции для API
    cart_items_for_api = []
    
    for item in cart_summary['items']:
        cart_items_for_api.append({
            'dish_id': item['dish_id'],
            'name': item['name'],
            'price': item['price'],  # Оригинальная цена
            'quantity': item['quantity']
        })
    
    # Рассчитываем общую сумму заказа
    cart_total = cart_summary.get('total', 0)
    final_total = cart_total - discount_amount
    if order_type == 'delivery':
        final_total += delivery_cost
    
    # СОЗДАЕМ ЗАКАЗ С ПЕРЕДАЧЕЙ СКИДКИ
    result = await presto_api.create_delivery_order(
        customer_data=customer_data,
        cart_items=cart_items_for_api,
        delivery_data=delivery_data,
        comment=order_comment,
        is_pickup=(order_type == 'pickup'),
        discount_amount=discount_amount,
        discount_type=discount_type
    )
    
    if 'error' in result:
        error_msg = result.get('error', 'Неизвестная ошибка')
        details = result.get('details', '')
        
        logger.error(f"❌ Ошибка создания заказа для пользователя {user_id}: {error_msg}")
        logger.error(f"❌ Детали ошибки: {details}")
        
        # Упрощенное сообщение об ошибке для пользователя
        if "HTTP 500" in error_msg:
            error_text = "500 - Внутренняя ошибка сервера"
        elif "HTTP 400" in error_msg:
            error_text = "400 - Неверный запрос"
        else:
            error_text = error_msg
        
        text = f"""❌ <b>Ошибка создания заказа</b>

<b>Причина:</b> {error_text}

Пожалуйста, попробуйте снова или свяжитесь с оператором по телефону +7 (903) 748-80-80."""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"process_payment_{order_type}")],
            [types.InlineKeyboardButton(text="📞 Связаться", callback_data="contact_us")],
            [types.InlineKeyboardButton(text="🛒 Вернуться в корзину", callback_data="view_cart")]
        ])
        
        await update_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)
        return
    
    order_number = result.get('orderNumber')
    sale_key = result.get('saleKey')
    
    if not order_number or not sale_key:
        text = """❌ <b>Ошибка создания заказа</b>

Не удалось получить номер заказа.

Пожалуйста, свяжитесь с оператором по телефону +7 (903) 748-80-80."""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📞 Связаться", callback_data="contact_us")],
            [types.InlineKeyboardButton(text="🛒 Вернуться в корзину", callback_data="view_cart")]
        ])
        
        await update_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)
        return
    
    shop_url = "https://t.me/mashkov_rest_bot"
    success_url = f"https://t.me/mashkov_rest_bot?start=payment_success_{sale_key}"
    error_url = f"https://t.me/mashkov_rest_bot?start=payment_error_{sale_key}"
    
    payment_link = await presto_api.get_payment_link(
        sale_key=sale_key,
        shop_url=shop_url,
        success_url=success_url,
        error_url=error_url
    )
    
    if not payment_link:
        text = f"""✅ <b>Заказ №{order_number} создан!</b>

⚠️ <b>Не удалось создать ссылку для оплаты</b>

Пожалуйста, оплатите заказ при получении или свяжитесь с оператором по телефону +7 (903) 748-80-80.

<b>Номер заказа:</b> {order_number}
<b>ID заказа:</b> {sale_key}
        
⏱️ <b>Заказ будет готов через:</b> {'45-60 минут' if order_type == 'delivery' else '30-40 минут'}"""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📞 Связаться", callback_data="contact_us")],
            [types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_main")]
        ])
        
        await update_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)
        return
    
    # Запускаем задачу проверки статуса оплаты
    task = asyncio.create_task(
        check_payment_status(sale_key, user_id, callback.bot, state)
    )
    
    pending_payments[user_id] = {
        'sale_key': sale_key,
        'task': task,
        'timestamp': datetime.now(),
        'order_number': order_number
    }
    
    # Сохраняем информацию о заказе для восстановления корзины
    await state.update_data({
        'pending_order_sale_key': sale_key,
        'pending_order_items': cart_summary['items'],
        'pending_order_discount': discount_amount,
        'pending_order_number': order_number
    })
    
    # Формируем текст заказа для сохранения в БД
    order_items_text = "\n".join([f"{item['name']} - {item['quantity']}шт." 
                                  for item in cart_summary['items']])
    
    promocode_used = None
    if applied_promocode and applied_promocode.get('valid'):
        promocode_used = applied_promocode.get('code')
        if discount_type == 'percent':
            order_items_text += f"\nПромокод: {promocode_used} ({discount_percent}%)"
        else:
            order_items_text += f"\nПромокод: {promocode_used} ({discount_amount:.0f}₽)"
    
    if comment:
        order_items_text += f"\nКомментарий: {comment}"
    
    # Сохраняем заказ в базу (но не очищаем корзину сразу!)
    database.save_order(
        user_id=user_id,
        items=order_items_text,
        total_amount=final_total,
        phone=user_data.get('phone'),
        delivery_address=address_text if order_type == 'delivery' else 'Самовывоз',
        notes=f"Presto ID: {order_number}, Sale Key: {sale_key}, Status: pending",
        promocode=promocode_used,
        discount_amount=discount_amount
    )
    
    # Сохраняем использованный промокод если есть
    if promocode_used:
        database.save_user_promocode(user_id, promocode_used, discount_amount=discount_amount)
    
    text = f"""✅ <b>Заказ №{order_number} создан!</b>

💰 <b>Сумма к оплате:</b> {final_total:.0f}₽
{'🚚 <b>Доставка:</b> ' + ('🎉 Бесплатно' if delivery_cost == 0 else f'{delivery_cost}₽') if order_type == 'delivery' else '🏃 <b>Самовывоз</b>'}
{'📍 <b>Адрес доставки:</b> ' + address_text if order_type == 'delivery' else ''}
⏱️ <b>Время {'доставки' if order_type == 'delivery' else 'приготовления'}:</b> {'45-60 минут' if order_type == 'delivery' else '30-40 минут'}

<b>Для оплаты перейдите по ссылке:</b>

🔗 <a href="{payment_link}">ОПЛАТИТЬ ЗАКАЗ</a>

⚠️ <b>Внимание:</b> Ссылка активна 7 минут. Если не оплатить заказ в течение этого времени, он будет автоматически отменен.

<i>После оплаты вернитесь в бот для получения подтверждения.</i>

<b>Если возникли проблемы с оплатой:</b>
1. Нажмите "✅ Я оплатил" если уже оплатили
2. Нажмите "❌ Отменить заказ" если передумали
3. Свяжитесь с нами по телефону +7 (903) 748-80-80"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💳 Перейти к оплате", url=payment_link)],
        [types.InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_payment_{sale_key}")],
        [types.InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel_order_{sale_key}")]
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)


@router.callback_query(F.data == "back_to_order_type")
async def back_to_order_type_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    await show_order_type_selection(user_id, callback.bot, state)

@router.callback_query(F.data == "back_to_address_details")
async def back_to_address_details_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    state_data = await state.get_data()
    address_text = state_data.get('address_text', '')
    delivery_cost = state_data.get('delivery_cost', 0)
    cart_summary = state_data.get('cart_summary', {})
    cart_total = cart_summary.get('total', 0)
    total_with_delivery = cart_total + delivery_cost
    
    text = f"""✅ <b>Доставка возможна!</b>

<b>Адрес:</b> {address_text}
<b>Стоимость доставки:</b> {delivery_cost}₽
<b>Сумма заказа:</b> {cart_total}₽
<b>Итого к оплате:</b> {total_with_delivery}₽

<b>Теперь заполните детали адреса (необязательно):</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🏠 Квартира/Офис", callback_data="set_apartment")],
        [types.InlineKeyboardButton(text="🚪 Подъезд", callback_data="set_entrance")],
        [types.InlineKeyboardButton(text="📈 Этаж", callback_data="set_floor")],
        [types.InlineKeyboardButton(text="🔑 Код двери", callback_data="set_door_code")],
        [
            types.InlineKeyboardButton(text="✅ Продолжить", callback_data="proceed_to_comment"),
            types.InlineKeyboardButton(text="🏠 Изменить адрес", callback_data="enter_new_address_from_cart")
        ],
        [types.InlineKeyboardButton(text="🛒 Вернуться в корзину", callback_data="view_cart")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)
    
    await state.set_state(DeliveryOrderStates.entering_address_details)

@router.callback_query(F.data == "back_to_comment")
async def back_to_comment_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    state_data = await state.get_data()
    order_type = state_data.get('order_type', 'delivery')
    
    if order_type == 'delivery':
        address_text = state_data.get('address_text')
        if address_text:
            await ask_for_comment(user_id, callback.bot, state)
        else:
            await back_to_order_type_handler(callback, state)
    else:
        await ask_for_comment(user_id, callback.bot, state)

@router.callback_query(F.data == "set_apartment")
async def set_apartment_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    state_data = await state.get_data()
    current_apartment = state_data.get('apartment', '')
    
    text = f"🏠 <b>Укажите номер квартиры или офиса:</b>\n\n"
    
    if current_apartment:
        text += f"<i>Текущее значение: {current_apartment}</i>\n\n"
    
    text += "<i>Можно указать несколько через запятую, если заказ в несколько квартир</i>\n"
    text += "<i>Или напишите 'нет', чтобы очистить</i>"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_address_details")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)
    
    await state.update_data(waiting_for_field='apartment')

@router.callback_query(F.data == "set_entrance")
async def set_entrance_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    state_data = await state.get_data()
    current_entrance = state_data.get('entrance', '')
    
    text = f"🚪 <b>Укажите номер подъезда:</b>\n\n"
    
    if current_entrance:
        text += f"<i>Текущее значение: {current_entrance}</i>\n\n"
    
    text += "<i>Или напишите 'нет', чтобы очистить</i>"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_address_details")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)
    
    await state.update_data(waiting_for_field='entrance')

@router.callback_query(F.data == "set_floor")
async def set_floor_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    state_data = await state.get_data()
    current_floor = state_data.get('floor', '')
    
    text = f"📈 <b>Укажите этаж:</b>\n\n"
    
    if current_floor:
        text += f"<i>Текущее значение: {current_floor}</i>\n\n"
    
    text += "<i>Или напишите 'нет', чтобы очистить</i>"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_address_details")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)
    
    await state.update_data(waiting_for_field='floor')

@router.callback_query(F.data == "set_door_code")
async def set_door_code_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    state_data = await state.get_data()
    current_door_code = state_data.get('door_code', '')
    
    text = f"🔑 <b>Укажите код домофона или двери:</b>\n\n"
    
    if current_door_code:
        text += f"<i>Текущее значение: {current_door_code}</i>\n\n"
    
    text += "<i>Например: 25# или 1234*25</i>\n"
    text += "<i>Или напишите 'нет', чтобы очистить</i>"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_address_details")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)
    
    await state.update_data(waiting_for_field='door_code')

@router.message(DeliveryOrderStates.entering_address_details)
async def process_address_detail(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    detail_text = message.text.strip()
    
    state_data = await state.get_data()
    field = state_data.get('waiting_for_field')
    
    if not field:
        temp_msg = await message.answer("⚠️ Пожалуйста, используйте кнопки для ввода деталей")
        await add_temp_message(user_id, temp_msg.message_id)
        await asyncio.sleep(2)
        await cleanup_temp_messages(user_id, message.bot)
        return
    
    try:
        await message.delete()
    except:
        pass
    
    if detail_text.lower() in ['нет', 'no', 'clear', 'удалить']:
        detail_text = ''
    
    await state.update_data({field: detail_text})
    await show_address_details_again(user_id, message.bot, state)

async def show_address_details_again(user_id: int, bot, state: FSMContext):
    state_data = await state.get_data()
    address_text = state_data.get('address_text', '')
    delivery_cost = state_data.get('delivery_cost', 0)
    cart_summary = state_data.get('cart_summary', {})
    cart_total = cart_summary.get('total', 0)
    apartment = state_data.get('apartment', '')
    entrance = state_data.get('entrance', '')
    floor = state_data.get('floor', '')
    door_code = state_data.get('door_code', '')
    
    total_with_delivery = cart_total + delivery_cost
    
    details_text = ""
    if apartment:
        details_text += f"🏠 Квартира/офис: {apartment}\n"
    if entrance:
        details_text += f"🚪 Подъезд: {entrance}\n"
    if floor:
        details_text += f"📈 Этаж: {floor}\n"
    if door_code:
        details_text += f"🔑 Код двери: {door_code}\n"
    
    text = f"""✅ <b>Доставка возможна!</b>

<b>Адрес:</b> {address_text}
<b>Стоимость доставки:</b> {delivery_cost}₽
<b>Сумма заказа:</b> {cart_total}₽
<b>Итого к оплате:</b> {total_with_delivery}₽

<b>Заполненные детали:</b>
{details_text if details_text else '❌ Нет'}

<b>Выберите что изменить или продолжите:</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🏠 Квартира/Офис", callback_data="set_apartment")],
        [types.InlineKeyboardButton(text="🚪 Подъезд", callback_data="set_entrance")],
        [types.InlineKeyboardButton(text="📈 Этаж", callback_data="set_floor")],
        [types.InlineKeyboardButton(text="🔑 Код двери", callback_data="set_door_code")],
        [
            types.InlineKeyboardButton(text="✅ Продолжить", callback_data="proceed_to_comment"),
            types.InlineKeyboardButton(text="🏠 Изменить адрес", callback_data="enter_new_address")
        ],
        [types.InlineKeyboardButton(text="🛒 Вернуться в корзину", callback_data="view_cart")]
    ])
    
    await update_main_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
    
    await state.set_state(DeliveryOrderStates.entering_address_details)

async def cancel_pending_payment(user_id: int):
    if user_id in pending_payments:
        payment_data = pending_payments[user_id]
        sale_key = payment_data.get('sale_key')
        
        if sale_key:
            try:
                await presto_api.cancel_order(sale_key)
            except:
                pass
        
        task = payment_data.get('task')
        if task and not task.done():
            task.cancel()
        
        del pending_payments[user_id]

async def check_payment_status(sale_key: str, user_id: int, bot, state: FSMContext):
    try:
        for i in range(42):  # 42 * 10 секунд = 7 минут
            await asyncio.sleep(10)
            
            status_result = await presto_api.get_order_status(sale_key)
            
            if 'error' in status_result:
                continue
            
            payments = status_result.get('payments', [])
            is_paid = False
            
            for payment in payments:
                if payment.get('isClosed', False) and payment.get('paymentType') == 'online':
                    is_paid = True
                    break
            
            if is_paid:
                if user_id in pending_payments:
                    del pending_payments[user_id]
                
                await complete_order_after_payment(user_id, bot, state, sale_key)
                return
        
        # Если не оплачено за 7 минут
        await cancel_pending_payment(user_id)
        
        text = """❌ <b>Время оплаты истекло</b>

Вы не оплатили заказ в течение 7 минут.

Заказ был автоматически отменен.

Вы можете создать новый заказ."""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🍽️ Создать новый заказ", callback_data="menu_delivery")],
            [types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_main")]
        ])
        
        await update_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"❌ Ошибка проверки статуса оплаты: {e}")
        await cancel_pending_payment(user_id)

async def complete_order_after_payment(user_id: int, bot, state: FSMContext, sale_key: str):
    state_data = await state.get_data()
    cart_summary = state_data.get('cart_summary', {})
    order_type = state_data.get('order_type', 'delivery')
    address_text = state_data.get('address_text', '')
    applied_promocode = state_data.get('applied_promocode')
    comment = state_data.get('comment', '')
    
    order_info = await presto_api.get_order_status(sale_key)
    order_number = order_info.get('orderNumber', 'N/A')
    
    # ТОЛЬКО ТЕПЕРЬ ОЧИЩАЕМ КОРЗИНУ
    cart_manager.clear_cart(user_id)
    
    order_text = "\n".join([f"{item['name']} - {item['quantity']}шт." 
                          for item in cart_summary['items']])
    
    discount_percent = applied_promocode.get('discount_percent', 0) if applied_promocode else 0
    
    if applied_promocode and applied_promocode.get('valid'):
        order_text += f"\nПромокод: {applied_promocode.get('code')} ({discount_percent}%)"
    if comment:
        order_text += f"\nКомментарий: {comment}"
    
    if order_type == 'pickup':
        text = f"""✅ <b>Заказ №{order_number} оплачен и принят!</b>

<b>Самовывоз</b>
📍 <b>Адрес:</b> бул. Академика Ландау, 1, Москва
⏱️ <b>Будет готов через:</b> 30-40 минут

<b>Ваш заказ:</b>
{order_text}

<b>Статус:</b> В работе
📱 <b>Мы свяжемся с вами, если потребуется</b>"""
    else:
        text = f"""✅ <b>Заказ №{order_number} оплачен и принят!</b>

<b>Доставка</b>
📍 <b>Адрес:</b> {address_text}
⏱️ <b>Время доставки:</b> 45-60 минут

<b>Ваш заказ:</b>
{order_text}

<b>Статус:</b> В работе
📱 <b>Мы свяжемся с вами, если потребуется</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🍽️ Новый заказ", callback_data="menu_delivery")],
        [types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_main")]
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=bot)
    
    await state.clear()

@router.callback_query(F.data == "cancel_address_detail")
async def cancel_address_detail_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    await state.update_data(waiting_for_field=None)
    await show_address_details_again(user_id, callback.bot, state)

@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment_status_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    sale_key = callback.data.replace("check_payment_", "")
    user_id = callback.from_user.id
    
    text = "🔍 <b>Проверяем статус оплаты...</b>"
    await update_main_message(user_id, text, parse_mode="HTML", bot=callback.bot)
    
    status_result = await presto_api.get_order_status(sale_key)
    
    if 'error' in status_result:
        text = f"""❌ <b>Не удалось проверить статус оплаты</b>

Пожалуйста, свяжитесь с оператором для подтверждения оплаты.

<b>ID заказа:</b> {sale_key}"""
    else:
        payments = status_result.get('payments', [])
        is_paid = False
        
        for payment in payments:
            if payment.get('isClosed', False) and payment.get('paymentType') == 'online':
                is_paid = True
                break
        
        if is_paid:
            await complete_order_after_payment(user_id, callback.bot, state, sale_key)
            return
        else:
            text = f"""⏳ <b>Оплата еще не поступила</b>

Если вы уже оплатили заказ, пожалуйста, подождите несколько минут.

<b>ID заказа:</b> {sale_key}"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔄 Проверить еще раз", callback_data=f"check_payment_{sale_key}")],
        [types.InlineKeyboardButton(text="📞 Связаться", callback_data="contact_us")],
        [types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_main")]
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    sale_key = callback.data.replace("cancel_order_", "")
    user_id = callback.from_user.id
    
    # Получаем сохраненные позиции из состояния
    state_data = await state.get_data()
    pending_items = state_data.get('pending_order_items', [])
    
    # ВОССТАНАВЛИВАЕМ КОРЗИНУ
    if pending_items:
        # Очищаем текущую корзину
        cart_manager.clear_cart(user_id)
        
        # Восстанавливаем позиции
        for item in pending_items:
            cart_manager.add_to_cart(
                user_id=user_id,
                dish_id=item['dish_id'],
                dish_name=item['name'],
                price=item['price'],
                quantity=item['quantity'],
                image_url=item.get('image_url')
            )
    
    await cancel_pending_payment(user_id)
    
    text = """✅ <b>Заказ отменен</b>

Корзина восстановлена. Вы можете изменить заказ или попробовать снова."""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 Корзина", callback_data="view_cart")],
        [types.InlineKeyboardButton(text="🍽️ Меню", callback_data="menu_delivery")]
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    # Очищаем данные о pending заказе
    await state.update_data({
        'pending_order_sale_key': None,
        'pending_order_items': None,
        'pending_order_id': None
    })

print("✅ handlers_delivery.py загружен!")