from aiogram import types
from aiogram.dispatcher import FSMContext

import keyboards as kb

from app import dp, bot
from bot_exceptions import CallbackException
from handlers.helpers import UserStates, handle_throttled_query, find_user_by
from s95 import records, clubs
from s95.collations import CollationMaker
from s95.personal import PersonalResults
from utils import content


@dp.callback_query_handler(lambda c: c.data == 'most_records_parkruns')
@dp.throttled(handle_throttled_query, rate=6)
async def process_most_records_parkruns(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, 'Подождите, идёт построение диаграммы...')
    pic = await records.top_records_count('gen_png/records.png')
    await bot.send_photo(callback_query.from_user.id, pic)
    pic.close()


@dp.callback_query_handler(lambda c: c.data == 'top_active_clubs')
@dp.throttled(handle_throttled_query, rate=6)
async def process_top_active_clubs(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, 'Подождите, идёт построение диаграммы...')
    pic = clubs.top_active_clubs_diagram('gen_png/top_clubs.png')
    await bot.send_photo(callback_query.from_user.id, pic)
    pic.close()


@dp.callback_query_handler(lambda c: c.data == 'compare_results')
@dp.throttled(rate=2)
async def process_compare_results(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        '*Сравнение персональных результатов.*\n'
        'Здесь можно сравнить свои результаты с результатами другого '
        'участника на тех паркранах, на которых вы когда-либо бежали вместе.\n'
        'Предварительно необходимо установить свой паркран ID (через меню настройки) '
        'и паркран ID участника для сравнения (кнопка Ввести ID участника)',
        reply_markup=kb.inline_compare, parse_mode='Markdown')


@dp.callback_query_handler(lambda c: c.data == 'personal_results')
@dp.throttled(rate=2)
async def process_personal_results(callback_query: types.CallbackQuery):
    await bot.delete_message(callback_query.from_user.id, callback_query.message.message_id)
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        '*Представление ваших результатов.*\n'
        'Здесь можно сделать визуализацию ваших результатов за всю историю участия в забегах S95.',
        reply_markup=kb.inline_personal, 
        parse_mode='Markdown'
    )


async def get_compared_pages(user_id):
    settings = None # await redis.get_value(user_id)
    athlete_id_1 = settings.get('id', None)
    athlete_id_2 = settings.get('compare_id', None)
    if not athlete_id_1:
        raise CallbackException('Вы не ввели свой parkrun ID.\n'
                                'Перейдите в настройки и нажмите кнопку Выбрать участника')
    if not athlete_id_2:
        raise CallbackException('Вы не ввели parkrun ID участника для сравнения.\n'
                                'Нажмите кнопку Ввести ID участника.')
    if athlete_id_1 == athlete_id_2:
        raise CallbackException('Ваш parkrun ID не должен совпадать с parkrun ID, выбранного участника.')
    athlete_name_1 = await find_user_by('id', athlete_id_1)
    athlete_name_2 = await find_user_by('id', athlete_id_2)
    # with Vedis(DB_FILE) as db:
    #     try:
    #         h = db.Hash(f'A{athlete_id_1}')
    #         athlete_page_1 = h['athlete_page'].decode()
    #         h = db.Hash(f'A{athlete_id_2}')
    #         athlete_page_2 = h['athlete_page'].decode()
    #     except Exception as e:
    #         logger.error(e)
    #         raise CallbackException('Что-то пошло не так. Проверьте настройки или попробуйте ввести ID-шники снова.')
    return athlete_name_1, athlete_name_2


async def get_personal_page(user_id):
    settings = None # await redis.get_value(user_id)
    athlete_id = settings.get('id', None)
    if not athlete_id:
        raise CallbackException('Вы не ввели свой parkrun ID.\n'
                                'Перейдите в настройки и нажмите кнопку Выбрать участника')
    athlete = await find_user_by('id', athlete_id)
    return athlete
    # with Vedis(DB_FILE) as db:
    #     try:
    #         h = db.Hash(f'A{athlete_id}')
    #         athlete_page = h['athlete_page'].decode()
    #     except Exception as e:
    #         logger.error(e)
    #         raise CallbackException('Что-то пошло не так. Проверьте настройки или попробуйте ввести ID-шники снова.')
    # return athlete_name, athlete_page


@dp.callback_query_handler(lambda c: c.data == 'battle_diagram')
@dp.throttled(handle_throttled_query, rate=10)
async def process_battle_diagram(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, 'Строю диаграмму. Подождите...')
    user_id = callback_query.from_user.id
    pages = await get_compared_pages(user_id)
    pic = CollationMaker(*pages).bars('gen_png/battle.png')
    await bot.send_photo(user_id, pic, caption='Трактовка: чем меньше по высоте столбцы, тем ближе ваши результаты.')
    pic.close()


@dp.callback_query_handler(lambda c: c.data == 'battle_scatter')
@dp.throttled(handle_throttled_query, rate=10)
async def process_battle_scatter(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, 'Строю график. Подождите...')
    user_id = callback_query.from_user.id
    pages = await get_compared_pages(user_id)
    pic = CollationMaker(*pages).scatter('gen_png/scatter.png')
    await bot.send_photo(user_id, pic, caption='Трактовка: каждая точка - совместный забег, чем ближе точки к '
                                               'левому нижнему углу и красной линией, тем  больше соперничество.')
    pic.close()


@dp.callback_query_handler(lambda c: c.data == 'battle_table')
@dp.throttled(handle_throttled_query, rate=10)
async def process_battle_table(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, 'Рассчитываю таблицу. Подождите...')
    user_id = callback_query.from_user.id
    pages = await get_compared_pages(user_id)
    await bot.send_message(callback_query.from_user.id, CollationMaker(*pages).table(), parse_mode='Markdown')


@dp.callback_query_handler(lambda c: c.data == 'excel_table')
@dp.throttled(handle_throttled_query, rate=10)
async def process_excel_table(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, 'Создаю файл. Подождите...')
    user_id = callback_query.from_user.id
    pages = await get_compared_pages(user_id)
    CollationMaker(*pages).to_excel('compare_parkrun.xlsx').close()
    await bot.send_document(user_id, types.InputFile('compare_parkrun.xlsx'),
                            caption='Сравнительная таблица для анализа в Excel')


@dp.callback_query_handler(lambda c: c.data == 'personal_history')
@dp.throttled(handle_throttled_query, rate=10)
async def process_personal_history_diagram(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, 'Строю диаграмму. Подождите...')
    telegram_id = callback_query.from_user.id
    # page = await get_personal_page(telegram_id)
    pic = await PersonalResults(telegram_id).history('gen_png/participate.png')
    await bot.send_photo(telegram_id, pic, caption='Трактовка: равномерность и интенсивность цвета показывает '
                                               'регулярность участия в паркранах.')
    pic.close()


@dp.callback_query_handler(lambda c: c.data == 'personal_bests')
@dp.throttled(handle_throttled_query, rate=10)
async def process_personal_bests_diagram(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, 'Строю диаграмму. Подождите...')
    telegram_id = callback_query.from_user.id
    pic = await PersonalResults(telegram_id).personal_bests('gen_png/pb.png')
    await bot.send_photo(telegram_id, pic, caption='Трактовка: по цвету можно понять, когда у вас были лучшие результаты.')
    pic.close()


@dp.callback_query_handler(lambda c: c.data == 'personal_tourism')
@dp.throttled(handle_throttled_query, rate=10)
async def process_personal_tourism_diagram(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, 'Строю диаграмму. Подождите...')
    telegram_id = callback_query.from_user.id
    pic = await PersonalResults(telegram_id).tourism('gen_png/tourism.png')
    await bot.send_photo(telegram_id, pic, caption='Трактовка: по цвету можно понять, когда и как часто вы '
                                               'посещали разные паркраны.')
    pic.close()


@dp.callback_query_handler(lambda c: c.data == 'personal_last')
@dp.throttled(handle_throttled_query, rate=10)
async def process_personal_last_parkruns_diagram(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, 'Строю диаграмму. Подождите...')
    telegram_id = callback_query.from_user.id
    pic = await PersonalResults(telegram_id).last_runs('gen_png/last_runs.png')
    await bot.send_photo(telegram_id, pic, caption='Трактовка: оцените прогресс (если он есть).')
    pic.close()


@dp.callback_query_handler(lambda c: c.data == 'personal_wins')
@dp.throttled(handle_throttled_query, rate=10)
async def process_personal_wins_table(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, 'Рассчитываю таблицу. Подождите...')
    telegram_id = callback_query.from_user.id
    table = await PersonalResults(telegram_id).wins_table()
    await bot.send_message(callback_query.from_user.id, table, parse_mode='Markdown')


@dp.callback_query_handler(lambda c: c.data == 'athlete_code_search')
@dp.throttled(rate=5)
async def process_athlete_code_search(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await UserStates.SEARCH_ATHLETE_CODE.set()
    await bot.delete_message(callback_query.message.chat.id, callback_query.message.message_id)
    await bot.send_message(callback_query.from_user.id, content.athlete_code_search, parse_mode='Markdown')


@dp.callback_query_handler(lambda c: c.data == 'help_to_find_id')
async def process_help_to_find_id(callback_query: types.CallbackQuery, state: FSMContext):
    if await state.get_state():
        await state.reset_state()
    await bot.answer_callback_query(callback_query.id)
    await bot.delete_message(callback_query.message.chat.id, callback_query.message.message_id)
    await bot.send_message(callback_query.from_user.id, content.help_to_find_id,
                           parse_mode='Markdown', reply_markup=kb.inline_open_s95)


@dp.callback_query_handler(lambda c: c.data == 'cancel_registration')
async def process_cancel_registration(callback_query: types.CallbackQuery, state: FSMContext):
    if await state.get_state():
        await state.reset_state()
    await bot.answer_callback_query(callback_query.id)
    await bot.delete_message(callback_query.message.chat.id, callback_query.message.message_id)
    kbd = await kb.main(callback_query.from_user.id)
    await bot.send_message(
        callback_query.from_user.id,
        'Наберите /help, чтобы посмотреть доступные команды',
        reply_markup=kbd
    )


@dp.callback_query_handler(lambda c: c.data == 'start_registration')
async def process_start_registration(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.delete_message(callback_query.message.chat.id, callback_query.message.message_id)
    await bot.send_message(
        callback_query.from_user.id,
        content.you_already_have_id,
        reply_markup=kb.inline_find_athlete_by_id
    )


@dp.callback_query_handler(lambda c: c.data == 'create_new_athlete')
async def process_new_athlete_registration(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.delete_message(callback_query.message.chat.id, callback_query.message.message_id)
    await UserStates.ATHLETE_LAST_NAME.set()
    await bot.send_message(
        callback_query.from_user.id,
        'Введите пожалуйста свою *Фамилию*',
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
