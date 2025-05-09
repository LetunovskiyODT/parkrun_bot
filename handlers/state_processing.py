import aiohttp
import re
import time
import logging
from datetime import datetime

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.exceptions import MessageToDeleteNotFound
from config import INTERNAL_API_URL
from random import randint

import keyboards as kb

from app import dp, language_code, db
from handlers import helpers
from s95.athlete_code import AthleteCode
from utils import mailer
from utils.content import t, home_event_notice
from utils.mailer import EmailConfirmation
from handlers.helpers import PROCEED_CREATION_REGEXP, LINK_ATHLETE_REGEXP, GENDERS_LIST, MALE_LIST, Form

logger = logging.getLogger(__name__)

@dp.message_handler(state=Form.athlete_code)
async def process_athlete_code(message: types.Message, state: FSMContext):
    try:
        await helpers.delete_message(message)
        athlete_code = message.text.strip()
        if not re.match(r'^[A-Z]?\d+$', athlete_code):
            return await message.answer(t(language_code(message), 'wrong_athlete_code'))
        
        athlete = await db.execute('SELECT * FROM athletes WHERE code = $1', athlete_code)
        if not athlete:
            return await message.answer(t(language_code(message), 'athlete_not_found'))
        
        user = await db.execute('SELECT * FROM users WHERE athlete_id = $1', athlete['id'])
        if user:
            return await message.answer(t(language_code(message), 'athlete_already_registered').format(athlete['id']))
        
        await state.update_data(athlete_code=athlete_code)
        await Form.email.set()
        await message.answer(t(language_code(message), 'request_email'))
    except Exception as e:
        logger.error(f"Error in process_athlete_code: {e}")
        await message.answer(t(language_code(message), 'error_occurred'))

@dp.message_handler(state=Form.email)
async def process_email(message: types.Message, state: FSMContext):
    try:
        await helpers.delete_message(message)
        email = message.text.strip().lower()
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return await message.answer(t(language_code(message), 'wrong_email'))
        
        data = await state.get_data()
        athlete_code = data.get('athlete_code')
        athlete = await db.execute('SELECT * FROM athletes WHERE code = $1', athlete_code)
        if not athlete:
            return await message.answer(t(language_code(message), 'athlete_not_found'))
        
        pin_code = AthleteCode.generate_pin()
        await state.update_data(email=email, pin_code=pin_code)
        
        email_confirmation = EmailConfirmation(pin_code, language_code(message))
        email_confirmation.send(email, athlete['name'])
        
        await Form.pin_code.set()
        await message.answer(t(language_code(message), 'pin_code_sent'))
    except Exception as e:
        logger.error(f"Error in process_email: {e}")
        await message.answer(t(language_code(message), 'error_occurred'))

@dp.message_handler(state=Form.pin_code)
async def process_pin_code(message: types.Message, state: FSMContext):
    try:
        await helpers.delete_message(message)
        pin_code = message.text.strip()
        data = await state.get_data()
        if pin_code != str(data.get('pin_code')):
            return await message.answer(t(language_code(message), 'wrong_pin_code'))
        
        athlete_code = data.get('athlete_code')
        email = data.get('email')
        athlete = await db.execute('SELECT * FROM athletes WHERE code = $1', athlete_code)
        if not athlete:
            return await message.answer(t(language_code(message), 'athlete_not_found'))
        
        user_data = {
            'telegram_id': message.from_user.id,
            'athlete_id': athlete['id'],
            'email': email,
            'created_at': datetime.now()
        }
        await db.execute(
            'INSERT INTO users (telegram_id, athlete_id, email, created_at) VALUES ($1, $2, $3, $4)',
            user_data['telegram_id'], user_data['athlete_id'], user_data['email'], user_data['created_at']
        )
        
        await state.finish()
        await message.answer(
            t(language_code(message), 'registration_complete'),
            reply_markup=await kb.main(message)
        )
    except Exception as e:
        logger.error(f"Error in process_pin_code: {e}")
        await message.answer(t(language_code(message), 'error_occurred'))


# Просим Почту сразу
@dp.message_handler(state=helpers.UserStates.SAVE_WITH_PARKRUN_CODE, regexp=LINK_ATHLETE_REGEXP)
async def process_save_with_parkrun_code(message: types.Message):
    await helpers.UserStates.EMAIL.set()
    await message.reply(t(language_code(message), 'ask_email'), reply_markup=types.ReplyKeyboardRemove())


# Запрашиваем Фамилию
@dp.message_handler(state=helpers.UserStates.SAVE_WITH_PARKRUN_CODE, regexp=PROCEED_CREATION_REGEXP)
async def process_ask_athlete_last_name(message: types.Message):
    await helpers.UserStates.next()
    await message.answer(t(language_code(message), 'input_lastname'), reply_markup=types.ReplyKeyboardRemove())


@dp.message_handler(state=helpers.UserStates.SAVE_WITH_PARKRUN_CODE)
async def process_cancel_parkrun_code(message: types.Message, state: FSMContext):
    await state.finish()
    kbd = await kb.main(message)
    await message.reply(t(language_code(message), 'request_cancelled'), reply_markup=kbd)


# Получаем Фамилию
# Запрашиваем Имя
@dp.message_handler(state=helpers.UserStates.ATHLETE_LAST_NAME, regexp=r'\A[^\W\d_]+([-\'][^\W\d_]{2,})?\Z')
async def process_get_athlete_last_name(message: types.Message, state: FSMContext):
    await helpers.UserStates.next()
    await state.update_data(last_name=message.text.upper())
    await message.answer(t(language_code(message), 'input_firstname'))


@dp.message_handler(state=helpers.UserStates.ATHLETE_LAST_NAME)
async def process_repeat_last_name(message: types.Message):
    await message.answer(t(language_code(message), 'input_lastname_again'), reply_markup=types.ReplyKeyboardRemove())


# Сохраняем Имя
# Запрашиваем Пол
@dp.message_handler(state=helpers.UserStates.ATHLETE_FIRST_NAME, regexp=r'\A[^\W\d_]+(?:-[^\W\d_]{2,})?\Z')
async def process_get_athlete_first_name(message: types.Message, state: FSMContext):
    await helpers.UserStates.next()
    await state.update_data(first_name=message.text)
    gender_kbd = await kb.select_gender(message)
    await message.answer(t(language_code(message), 'input_gender'), reply_markup=gender_kbd)


# Повторно запрашиваем имя, если не сработала регулярка
@dp.message_handler(state=helpers.UserStates.ATHLETE_FIRST_NAME)
async def process_repeat_first_name(message: types.Message):
    await message.answer(t(language_code(message), 'input_firstname_again'))


# Запрашиваем Пол ещё раз
@dp.message_handler(lambda m: m.text.strip().lower() not in GENDERS_LIST, state=helpers.UserStates.GENDER)
async def process_gender_invalid(message: types.Message):
    gender_kbd = await kb.select_gender(message)
    await message.reply(t(language_code(message), 'define_your_gender'), reply_markup=gender_kbd)


# Сохраняем Пол
# Просим Почту
@dp.message_handler(state=helpers.UserStates.GENDER)
async def process_gender(message: types.Message, state: FSMContext):
    await state.update_data(male=(message.text.strip().lower() in MALE_LIST))
    await helpers.UserStates.next()
    await message.answer(t(language_code(message), 'ask_email'), reply_markup=types.ReplyKeyboardRemove())


# Почту для подтверждения
@dp.message_handler(
    state=helpers.UserStates.EMAIL,
    regexp=r'\A[a-zA-Z0-9.!#$%&*+/=?^_{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\Z'
)
async def process_get_email(message: types.Message, state: FSMContext):
    email = message.text.lower()
    user = await helpers.find_user_by_email(email)
    if user:
        # проверить, что у юзера с этой почтой не привязан участник
        if await helpers.find_athlete_by('user_id', user['id']):
            await state.finish()
            # TODO: Залогировать эту ситуацию
            return await message.reply(t(language_code(message), 'athlete_already_linked'))
        # Если участник не привязан, то делаем привязку
        await state.update_data(user_id=user['id'])
        await message.answer(t(language_code(message), 'user_exists_needs_linking'))
    await helpers.UserStates.next()
    async with state.proxy() as data:
        data['email'] = email
        data['attempt'] = 0
        data['sent_at'] = int(time.time())
        data['pin'] = randint(100, 999)
        lang = message.from_user.language_code
        confirmation_mailer = mailer.EmailConfirmation(data['pin'], lang)
        confirmation_mailer.send(email, f'{data["first_name"]} {data["last_name"]}')
    await message.reply(t(language_code(message), 'input_pin_code'))


@dp.message_handler(state=helpers.UserStates.EMAIL)
async def process_repeat_email(message: types.Message):
    await message.reply(t(language_code(message), 'incorrect_pin_code'))


@dp.message_handler(state=helpers.UserStates.VALIDATE_EMAIL)
async def process_email_validation(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        if not data.get('sent_at') or data['sent_at'] + 30 * 60 < time.time() or data.get('attempt', 3) >= 3:
            await helpers.UserStates.previous()
            return await message.reply(t(language_code(message), 'pin_code_expired'))
        data['attempt'] += 1
        if not message.text.isdecimal() or data['pin'] != int(message.text.strip()):
            return await message.reply(
                t(language_code(message), 'pincode_input_attempts').format(attempt=data["attempt"])
            )
        if 'user_id' not in data:
            await helpers.UserStates.next()
            return await message.answer(
                t(language_code(message), 'input_password') + t(language_code(message), 'password_requirements')
            )
        payload = {
            'user_id': data['user_id'],
            'user': {
                'telegram_id': message.from_user.id,
                'telegram_user': message.from_user.username
            }
        }
        # привязать участника к юзеру либо создать нового
        if 'athlete_id' in data:
            payload['athlete_id'] = data['athlete_id']
        else:
            payload['athlete'] = {
                'name': f'{data["first_name"]} {data["last_name"]}',
                'male': data['male'],
                'parkrun_code': data['parkrun_code'] if 'parkrun_code' in data else None,
                'fiveverst_code': data['fiveverst_code'] if 'fiveverst_code' in data else None,
                'runpark_code': data['runpark_code'] if 'runpark_code' in data else None
            }
        try:
            async with aiohttp.ClientSession(headers={'Accept': 'application/json'}) as session:
                async with session.put(f'{INTERNAL_API_URL}/user', json=payload) as response:
                    resp = await response.json()
                    if resp.ok:
                        await state.finish()
                        kbd = await kb.main(message)
                        await message.answer(
                            t(language_code(message), 'user_linked_successfully'),
                            reply_markup=kbd
                        )
                        await message.answer(
                            t(language_code(message), 'subscription_suggestion'),
                            parse_mode='Markdown',
                            disable_web_page_preview=True
                        )
                    else:
                        if 'user' in resp['errors']:
                            await message.answer('Ошибки в данных пользователя: ' + ', '.join(resp['errors']['user']))
                        if 'athlete' in resp['errors']:
                            await message.answer('Ошибки в данных участника: ' + ', '.join(resp['errors']['athlete']))
                        await message.answer(t(language_code(message), 'try_pin_code'))
        except Exception:
            await message.answer(t(language_code(message), 'try_pin_code'))
        finally:
            await message.delete()


@dp.message_handler(state=helpers.UserStates.PASSWORD, regexp=r'\A(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{6,}\Z')
async def process_password_validation(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        payload = {
            'user': {
                'email': data['email'],
                'password': message.text,
                'first_name': data['first_name'],
                'last_name': data['last_name'],
                'telegram_id': message.from_user.id,
                'telegram_user': message.from_user.username
            }
        }
        if 'athlete_id' in data:
            payload['athlete_id'] = data['athlete_id']
        else:
            payload['athlete'] = {
                'name': f'{data["first_name"]} {data["last_name"]}',
                'male': data['male'],
                'parkrun_code': data['parkrun_code'] if 'parkrun_code' in data else None,
                'fiveverst_code': data['fiveverst_code'] if 'fiveverst_code' in data else None,
                'runpark_code': data['runpark_code'] if 'runpark_code' in data else None
            }
    try:
        async with aiohttp.ClientSession(headers={'Accept': 'application/json'}) as session:
            async with session.post(f'{INTERNAL_API_URL}/user', json=payload) as response:
                resp = await response.json()
                if response.ok:
                    await state.finish()
                    kbd = await kb.main(message)
                    await message.answer(t(language_code(message), 'successful_registration'), reply_markup=kbd)
                    await message.answer(
                        t(language_code(message), 'subscription_suggestion'),
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                else:
                    if 'user' in resp['errors']:
                        await message.answer('Ошибки в данных пользователя: ' + ', '.join(resp['errors']['user']))
                    if 'athlete' in resp['errors']:
                        await message.answer('Ошибки в данных участника: ' + ', '.join(resp['errors']['athlete']))
                    await message.answer(t(language_code(message), 'try_password'))
    except Exception:
        await message.answer(t(language_code(message), 'try_password'))
    finally:
        await message.delete()
        await message.answer(t(language_code(message), 'password_erased'))


@dp.message_handler(state=helpers.UserStates.PASSWORD)
async def process_invalid_password(message: types.Message):
    await message.answer(
        t(language_code(message), 'invalid_password') + t(language_code(message), 'password_requirements')
    )
    await helpers.delete_message(message)
    await message.answer(t(language_code(message), 'password_erased_again'))


@dp.message_handler(state=helpers.HomeEventStates.INPUT_EVENT_ID, regexp=r'\A\d+\Z')
async def process_input_event_id(message: types.Message, state: FSMContext):
    event_id = int(message.text)
    result = await helpers.update_home_event(message.from_user.id, event_id)
    if not result:
        return await message.answer('Введён некорректный номер. Попробуйте ещё раз. Либо /reset для отмены')
    else:
        answer = 'Домашний забег установлен.'
        link = await helpers.tg_channel_of_event(event_id)
        if link:
            answer += ' ' + home_event_notice.format(link)
        await message.answer(answer, parse_mode='Markdown', disable_web_page_preview=True)
        await state.finish()


# Повторный запрос кода локации
@dp.message_handler(state=helpers.HomeEventStates.INPUT_EVENT_ID)
async def process_incorrect_input_club_id(message: types.Message):
    await message.answer('Введите число из приведённого выше списка. Либо /reset для отмены')


@dp.message_handler(state=helpers.ClubStates.INPUT_NAME)
async def process_club_name(message: types.Message, state: FSMContext):
    if len(message.text) < 3:
        return await message.answer('Введите название клуба немного точнее')
    club = await helpers.find_club_by_name(message.text)
    if not club:
        return await message.answer(t(language_code(message), 'club_not_found'))
    await state.update_data(club_id=club['id'], club_name=club['name'])
    await helpers.ClubStates.next()
    await message.answer(
        f'Найден клуб [{club["name"]}](https://s95.ru/clubs/{club["id"]}). Установить?',
        reply_markup=kb.confirm_set_club,
        parse_mode='Markdown'
    )
