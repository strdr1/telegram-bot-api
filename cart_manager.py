#!/usr/bin/env python3
"""
cart_manager.py - Менеджер корзины покупок
Обновленная версия с поддержкой исходной суммы для расчета доставки
"""

import json
import os
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import hashlib

import config

logger = logging.getLogger(__name__)

class CartManager:
    """Класс для управления корзинами пользователей с поддержкой промокодов"""
    
    def __init__(self):
        self.cache_file = config.CART_CACHE_FILE
        self.carts = {}  # {user_id: {'items': [], 'updated_at': timestamp, 'applied_discount': 0, 'original_total': 0}}
        
        # Создаем директорию если нужно
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        
        # Загружаем кэш
        self._load_cache()
    
    def _load_cache(self):
        """Загрузка кэша корзин из файла"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.carts = json.load(f)
                logger.info(f"✅ Корзины загружены из кэша ({len(self.carts)} пользователей)")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки кэша корзин: {e}")
            self.carts = {}
    
    def _save_cache(self):
        """Сохранение кэша корзин в файл"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.carts, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения кэша корзин: {e}")
            return False
    
    def get_cart_summary(self, user_id: int) -> Dict[str, Any]:
        """
        Получение сводки по корзине пользователя
        
        Теперь возвращает ДВЕ суммы:
        - 'total': текущая сумма (после скидки если применена)
        - 'original_total': исходная сумма (без учета скидки) для расчета доставки
        
        Args:
            user_id: ID пользователя Telegram
            
        Returns:
            Словарь с информацией о корзине:
            {
                'items': список товаров,
                'item_count': общее количество товаров,
                'total': общая сумма после скидки,
                'original_total': исходная сумма без скидки,
                'applied_discount': примененная скидка,
                'updated_at': время обновления
            }
        """
        user_id_str = str(user_id)
        user_cart = self.carts.get(user_id_str, {})
        items = user_cart.get('items', [])
        
        # Рассчитываем исходную сумму (без учета скидок)
        item_count = 0
        original_total = 0
        
        for item in items:
            quantity = item.get('quantity', 0)
            price = item.get('price', 0)
            item_count += quantity
            original_total += quantity * price
        
        # Получаем сохраненную исходную сумму или рассчитываем заново
        saved_original_total = user_cart.get('original_total')
        if saved_original_total is not None:
            original_total = saved_original_total
        
        # Получаем примененную скидку
        applied_discount = user_cart.get('applied_discount', 0)
        
        # Рассчитываем текущую сумму с учетом скидки
        current_total = original_total - applied_discount
        if current_total < 0:
            current_total = 0
        
        return {
            'items': items,
            'item_count': item_count,
            'total': current_total,
            'original_total': original_total,
            'applied_discount': applied_discount,
            'updated_at': user_cart.get('updated_at', '')
        }
    
    def add_to_cart(self, user_id: int, dish_id: int, dish_name: str, 
                   price: float, quantity: int = 1, image_url: Optional[str] = None) -> bool:
        """
        Добавление товара в корзину
        
        Args:
            user_id: ID пользователя
            dish_id: ID блюда
            dish_name: название блюда
            price: цена за единицу
            quantity: количество
            image_url: URL изображения
            
        Returns:
            True если успешно, False если ошибка
        """
        try:
            user_id_str = str(user_id)
            
            # Получаем или создаем корзину пользователя
            if user_id_str not in self.carts:
                self.carts[user_id_str] = {
                    'items': [],
                    'applied_discount': 0,
                    'original_total': 0,
                    'updated_at': datetime.now().isoformat()
                }
            
            # Проверяем, есть ли уже такой товар в корзине
            items = self.carts[user_id_str]['items']
            item_found = False
            
            for item in items:
                if item.get('dish_id') == dish_id:
                    # Увеличиваем количество существующего товара
                    old_quantity = item['quantity']
                    item['quantity'] += quantity
                    item['total_price'] = item['quantity'] * item['price']
                    item_found = True
                    
                    # Обновляем исходную сумму
                    quantity_difference = quantity
                    price_difference = quantity_difference * price
                    if 'original_total' in self.carts[user_id_str]:
                        self.carts[user_id_str]['original_total'] += price_difference
                    else:
                        # Рассчитываем исходную сумму с нуля
                        self.carts[user_id_str]['original_total'] = sum(
                            item['quantity'] * item['price'] for item in items
                        )
                    break
            
            if not item_found:
                # Добавляем новый товар
                new_item = {
                    'dish_id': dish_id,
                    'name': dish_name,
                    'price': price,
                    'quantity': quantity,
                    'total_price': price * quantity,
                    'image_url': image_url,
                    'added_at': datetime.now().isoformat()
                }
                items.append(new_item)
                
                # Обновляем исходную сумму
                if 'original_total' in self.carts[user_id_str]:
                    self.carts[user_id_str]['original_total'] += price * quantity
                else:
                    # Рассчитываем исходную сумму с нуля
                    self.carts[user_id_str]['original_total'] = sum(
                        item['quantity'] * item['price'] for item in items
                    )
            
            # Пересчитываем текущую сумму с учетом скидки
            applied_discount = self.carts[user_id_str].get('applied_discount', 0)
            original_total = self.carts[user_id_str].get('original_total', 0)
            current_total = original_total - applied_discount
            if current_total < 0:
                current_total = 0
            
            # Обновляем время изменения
            self.carts[user_id_str]['updated_at'] = datetime.now().isoformat()
            
            # Сохраняем кэш
            self._save_cache()
            
            logger.info(f"✅ Товар добавлен в корзину: user={user_id}, dish={dish_id}, qty={quantity}")
            logger.debug(f"   Исходная сумма: {self.carts[user_id_str].get('original_total')}₽, Скидка: {applied_discount}₽, Итог: {current_total}₽")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления в корзину: {e}")
            return False
    
    def remove_from_cart(self, user_id: int, dish_id: int, quantity: Optional[int] = None) -> bool:
        """
        Удаление товара из корзины или уменьшение количества
        
        Args:
            user_id: ID пользователя
            dish_id: ID блюда
            quantity: количество для удаления (None - удалить полностью)
            
        Returns:
            True если успешно, False если ошибка
        """
        try:
            user_id_str = str(user_id)
            
            if user_id_str not in self.carts:
                return False
            
            items = self.carts[user_id_str]['items']
            
            for i, item in enumerate(items):
                if item.get('dish_id') == dish_id:
                    price = item.get('price', 0)
                    old_quantity = item.get('quantity', 0)
                    
                    if quantity is None or old_quantity <= quantity:
                        # Удаляем товар полностью
                        items.pop(i)
                        removed_quantity = old_quantity
                    else:
                        # Уменьшаем количество
                        item['quantity'] -= quantity
                        item['total_price'] = item['quantity'] * price
                        removed_quantity = quantity
                    
                    # Обновляем исходную сумму
                    if 'original_total' in self.carts[user_id_str]:
                        self.carts[user_id_str]['original_total'] -= removed_quantity * price
                        if self.carts[user_id_str]['original_total'] < 0:
                            self.carts[user_id_str]['original_total'] = 0
                    
                    # Обновляем время изменения
                    self.carts[user_id_str]['updated_at'] = datetime.now().isoformat()
                    
                    # Если корзина пустая, удаляем её
                    if not items:
                        del self.carts[user_id_str]
                    
                    # Сохраняем кэш
                    self._save_cache()
                    
                    logger.info(f"✅ Товар удален из корзины: user={user_id}, dish={dish_id}, removed_qty={removed_quantity}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка удаления из корзины: {e}")
            return False
    
    def update_item_quantity(self, user_id: int, dish_id: int, new_quantity: int) -> bool:
        """
        Обновление количества товара в корзине
        
        Args:
            user_id: ID пользователя
            dish_id: ID блюда
            new_quantity: новое количество
            
        Returns:
            True если успешно, False если ошибка
        """
        try:
            user_id_str = str(user_id)
            
            if user_id_str not in self.carts:
                return False
            
            items = self.carts[user_id_str]['items']
            
            for item in items:
                if item.get('dish_id') == dish_id:
                    old_quantity = item.get('quantity', 0)
                    price = item.get('price', 0)
                    
                    if new_quantity <= 0:
                        # Удаляем товар если количество 0 или меньше
                        return self.remove_from_cart(user_id, dish_id)
                    
                    # Обновляем количество
                    item['quantity'] = new_quantity
                    item['total_price'] = item['quantity'] * price
                    
                    # Обновляем исходную сумму
                    quantity_difference = new_quantity - old_quantity
                    if 'original_total' in self.carts[user_id_str]:
                        self.carts[user_id_str]['original_total'] += quantity_difference * price
                    
                    # Обновляем время изменения
                    self.carts[user_id_str]['updated_at'] = datetime.now().isoformat()
                    
                    # Сохраняем кэш
                    self._save_cache()
                    
                    logger.info(f"✅ Количество обновлено: user={user_id}, dish={dish_id}, old_qty={old_quantity}, new_qty={new_quantity}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления количества: {e}")
            return False
    
    def clear_cart(self, user_id: int) -> bool:
        """
        Очистка корзины пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            True если успешно, False если ошибка
        """
        try:
            user_id_str = str(user_id)
            
            if user_id_str in self.carts:
                del self.carts[user_id_str]
                self._save_cache()
                logger.info(f"✅ Корзина очищена: user={user_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки корзины: {e}")
            return False
    
    def apply_promocode_to_cart(self, user_id: int, discount_amount: float, 
                               discount_type: str = 'amount') -> bool:
        """
        Применение промокода к корзине
        
        Args:
            user_id: ID пользователя
            discount_amount: сумма скидки
            discount_type: тип скидки ('amount' или 'percent')
            
        Returns:
            True если успешно, False если ошибка
        """
        try:
            user_id_str = str(user_id)
            
            if user_id_str not in self.carts:
                return False
            
            # Получаем текущую исходную сумму
            cart_summary = self.get_cart_summary(user_id)
            original_total = cart_summary.get('original_total', 0)
            
            # Рассчитываем скидку в зависимости от типа
            final_discount = discount_amount
            if discount_type == 'percent':
                # Процентная скидка от исходной суммы
                final_discount = (original_total * discount_amount) / 100
            
            # Не даем скидку превышать сумму заказа
            if final_discount > original_total:
                final_discount = original_total
            
            # Применяем скидку
            self.carts[user_id_str]['applied_discount'] = final_discount
            self.carts[user_id_str]['discount_type'] = discount_type
            self.carts[user_id_str]['discount_value'] = discount_amount
            
            # Обновляем время изменения
            self.carts[user_id_str]['updated_at'] = datetime.now().isoformat()
            
            # Сохраняем кэш
            self._save_cache()
            
            logger.info(f"✅ Промокод применен к корзине: user={user_id}, "
                       f"discount={final_discount}₽, original_total={original_total}₽")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка применения промокода к корзине: {e}")
            return False
    
    def clear_promocode_from_cart(self, user_id: int) -> bool:
        """
        Удаление промокода из корзины
        
        Args:
            user_id: ID пользователя
            
        Returns:
            True если успешно, False если ошибка
        """
        try:
            user_id_str = str(user_id)
            
            if user_id_str in self.carts:
                # Очищаем данные о скидке
                self.carts[user_id_str].pop('applied_discount', None)
                self.carts[user_id_str].pop('discount_type', None)
                self.carts[user_id_str].pop('discount_value', None)
                
                # Обновляем время изменения
                self.carts[user_id_str]['updated_at'] = datetime.now().isoformat()
                
                # Сохраняем кэш
                self._save_cache()
                
                logger.info(f"✅ Промокод удален из корзины: user={user_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка удаления промокода из корзины: {e}")
            return False
    
    def get_cart_with_delivery_info(self, user_id: int, district_info: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Получение корзины с информацией о доставке
        
        Args:
            user_id: ID пользователя
            district_info: информация о районе для расчета доставки
            
        Returns:
            Словарь с полной информацией о корзине и доставке
        """
        cart_summary = self.get_cart_summary(user_id)
        original_total = cart_summary.get('original_total', 0)
        current_total = cart_summary.get('total', 0)
        applied_discount = cart_summary.get('applied_discount', 0)
        
        result = {
            **cart_summary,
            'delivery_cost': 0,
            'delivery_explanation': '',
            'final_total': current_total,
            'delivery_calculated': False
        }
        
        # Если есть информация о районе, можно рассчитать доставку
        if district_info:
            from presto_api import presto_api  # Импортируем здесь чтобы избежать циклических импортов
            try:
                delivery_cost, delivery_explanation = presto_api.calculate_delivery_cost_simple(
                    district_info,
                    float(current_total),      # сумма со скидкой
                    float(original_total)      # исходная сумма для проверки порога
                )
                
                result.update({
                    'delivery_cost': delivery_cost,
                    'delivery_explanation': delivery_explanation,
                    'final_total': current_total + delivery_cost,
                    'delivery_calculated': True
                })
            except Exception as e:
                logger.error(f"❌ Ошибка расчета доставки: {e}")
        
        return result
    
    def get_cart_details(self, user_id: int) -> Dict[str, Any]:
        """
        Получение детальной информации о корзине для Presto API
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Словарь с товарами в формате для API
        """
        cart_summary = self.get_cart_summary(user_id)
        
        # Формируем данные для Presto API
        presto_items = []
        
        for item in cart_summary['items']:
            presto_items.append({
                'dish_id': item['dish_id'],
                'name': item['name'],
                'quantity': item['quantity'],
                'price': item['price']
            })
        
        return {
            'items': presto_items,
            'total': cart_summary['total'],
            'original_total': cart_summary['original_total'],
            'discount': cart_summary['applied_discount'],
            'item_count': cart_summary['item_count']
        }
    
    def get_user_cart_count(self, user_id: int) -> int:
        """
        Быстрый метод для получения количества товаров в корзине
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Количество товаров в корзине
        """
        return self.get_cart_summary(user_id)['item_count']
    
    def recalculate_cart_totals(self, user_id: int) -> bool:
        """
        Пересчет сумм в корзине (например, после изменения цен)
        
        Args:
            user_id: ID пользователя
            
        Returns:
            True если успешно, False если ошибка
        """
        try:
            user_id_str = str(user_id)
            
            if user_id_str not in self.carts:
                return False
            
            items = self.carts[user_id_str]['items']
            
            # Пересчитываем исходную сумму
            original_total = sum(item.get('quantity', 0) * item.get('price', 0) for item in items)
            
            # Обновляем суммы
            self.carts[user_id_str]['original_total'] = original_total
            
            # Пересчитываем текущую сумму с учетом скидки
            applied_discount = self.carts[user_id_str].get('applied_discount', 0)
            
            # Обновляем время изменения
            self.carts[user_id_str]['updated_at'] = datetime.now().isoformat()
            
            # Сохраняем кэш
            self._save_cache()
            
            logger.info(f"✅ Суммы корзины пересчитаны: user={user_id}, "
                       f"original_total={original_total}₽, discount={applied_discount}₽")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка пересчета сумм корзины: {e}")
            return False
    
    def get_all_carts(self) -> Dict[str, Dict]:
        """
        Получение всех корзин (для администратора)
        
        Returns:
            Словарь всех корзин
        """
        return self.carts.copy()

# Глобальный экземпляр менеджера корзины
cart_manager = CartManager()

# Экспортируем функции для удобного использования
get_cart_summary = cart_manager.get_cart_summary
add_to_cart = cart_manager.add_to_cart
remove_from_cart = cart_manager.remove_from_cart
update_item_quantity = cart_manager.update_item_quantity
clear_cart = cart_manager.clear_cart
get_cart_details = cart_manager.get_cart_details
apply_promocode_to_cart = cart_manager.apply_promocode_to_cart
clear_promocode_from_cart = cart_manager.clear_promocode_from_cart
get_cart_with_delivery_info = cart_manager.get_cart_with_delivery_info

print("CartManager: Менеджер корзины загружен!")