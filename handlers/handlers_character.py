from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import character_parser
from keyboards import get_character_keyboard

router = Router()

class CharacterStates(StatesGroup):
    waiting_for_character_name = State()
    waiting_for_character_desc = State()
    processing = State()

@router.message(Command("character"))
async def cmd_character(message: Message, state: FSMContext):
    """Начало создания персонажа"""
    await message.answer(
        "🎨 Давайте создадим персонажа!\n"
        "Введи имя или описание персонажа:",
        reply_markup=get_character_keyboard()
    )
    await state.set_state(CharacterStates.waiting_for_character_name)

@router.message(CharacterStates.waiting_for_character_name)
async def process_character_name(message: Message, state: FSMContext):
    """Обработка имени персонажа"""
    character_name = message.text.strip()
    
    if len(character_name) < 2:
        await message.answer("❌ Имя персонажа слишком короткое. Попробуй еще раз:")
        return
    
    await state.update_data(character_name=character_name)
    await message.answer(
        f"👤 Персонаж: {character_name}\n"
        "Теперь опиши его внешность, характер или особенности:"
    )
    await state.set_state(CharacterStates.waiting_for_character_desc)

@router.message(CharacterStates.waiting_for_character_desc)
async def process_character_desc(message: Message, state: FSMContext):
    """Обработка описания и начало парсинга"""
    character_desc = message.text.strip()
    data = await state.get_data()
    character_name = data.get('character_name')
    
    await message.answer("🔍 Ищу референсы в интернете...")
    
    async with character_parser.character_parser as parser:
        # Парсим референсы
        refs_result = await parser.parse_and_save_character_refs(character_name, message.from_user.id)
        
        if refs_result['ref_count'] > 0:
            await message.answer(
                f"✅ Найдено {refs_result['ref_count']} референсов для {character_name}\n"
                "🎨 Генерирую изображение..."
            )
            
            # Генерируем промт
            prompt = await character_parser.generate_character_prompt(
                character_desc, refs_result['ref_images']
            )
            
            # Здесь будет вызов AI генерации
            ai_result = await generate_character_image(prompt, refs_result['ref_images'])
            
            if ai_result:
                # Сохраняем результат
                result_path = await character_parser.save_ai_result(
                    character_name, message.from_user.id, ai_result, prompt
                )
                
                # Отправляем результат
                with open(result_path, 'rb') as photo:
                    await message.answer_photo(
                        photo,
                        caption=f"🎨 Ваш персонаж {character_name} готов!\n"
                                f"Prompt: {prompt}"
                    )
            else:
                await message.answer("❌ Не удалось сгенерировать изображение")
        else:
            await message.answer(
                "❌ Не найдено референсов для персонажа\n"
                "Попробуй другое имя или описание"
            )
    
    await state.clear()

async def generate_character_image(prompt: str, ref_images: List[str]) -> str:
    """Заглушка для AI генерации изображения"""
    # Здесь будет интеграция с AI API
    # Пока возвращаем путь к заглушке
    return "temp/ai_result.jpg"

@router.callback_query(F.data == "cancel_character")
async def cancel_character(callback: CallbackQuery, state: FSMContext):
    """Отмена создания персонажа"""
    await callback.message.answer("❌ Создание персонажа отменено")
    await state.clear()
    await callback.answer()