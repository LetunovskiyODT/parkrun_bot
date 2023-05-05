import os

from app import dp, bot, logger
from handlers.helpers import handle_throttled_query
from utils import content
from s95 import clubs, latest


@dp.message_handler(regexp='⏳ Получение данных об участии...')
@dp.throttled(handle_throttled_query, rate=12)
async def latestparkruns_club_participation(message):
    await bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    user_settings = None # await redis.get_value(user_id)
    club_id = user_settings.get('cl_id', None)
    if not club_id:
        await message.answer(content.no_club_message)
    else:
        data = await clubs.get_participants(club_id)
        await message.answer(data, parse_mode='Markdown', disable_web_page_preview=True)
    await bot.delete_message(message.chat.id, message.message_id)


@dp.message_handler(regexp='📊 Получение данных')
@dp.throttled(handle_throttled_query, rate=6)
async def post_latestparkrun_diagrams(message):
    await bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    user_settings = None # await redis.get_value(user_id)
    parkrun_name = user_settings.get('pr', None)
    if not parkrun_name:
        return await message.answer(content.no_parkrun_message)

    if 'диаграммы' in message.text:
        pic = await latest.make_latest_results_diagram(parkrun_name, 'results.png')
        if os.path.exists("results.png"):
            await bot.send_photo(message.chat.id, pic)
            pic.close()
        else:
            logger.error('File results.png not found! Or the picture wasn\'t generated.')

    elif 'о клубах...' in message.text:
        pic = await latest.make_clubs_bar(parkrun_name, 'gen_png/clubs.png')
        if os.path.exists("gen_png/clubs.png"):
            await bot.send_photo(message.chat.id, pic)
            pic.close()
        else:
            logger.error('File clubs.png not found! Or the picture wasn\'t generated.')
    elif 'с общей инфой.' in message.text:
        report = await latest.review_table(parkrun_name)
        await message.answer(report, parse_mode='Markdown')
    await bot.delete_message(message.chat.id, message.message_id)


@dp.message_handler(regexp='⏳ Получение данных о ')
@dp.throttled(handle_throttled_query, rate=12)
async def post_teammate_table(message):
    await bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    user_settings = None # await redis.get_value(user_id)
    parkrun_name = user_settings.get('pr', None)
    club_id = user_settings.get('cl_id', None)
    if not club_id:
        await message.answer(content.no_club_message)
    if not parkrun_name:
        await message.answer(content.no_parkrun_message)
    if not (club_id and parkrun_name):
        return

    if 'количестве локальных стартов' in message.text:
        data = await clubs.get_club_fans(parkrun_name, club_id)
        await message.answer(data, parse_mode='Markdown')

    elif 'количестве всех стартов' in message.text:
        data = await clubs.get_club_parkruners(parkrun_name, club_id)
        await message.answer(data, parse_mode='Markdown')

    elif 'рекордах' in message.text:
        data = await clubs.get_parkrun_club_top_results(parkrun_name, club_id)
        await message.answer(data, parse_mode='Markdown')

    elif 'выбранном клубе' in message.text:
        club = []
        if club:
            info = f"""*Выбранный клуб*: {club['name']}.
            *Зарегистрированных участников*: {club['participants']}.
            *Ссылка на клуб в интернете*: {club['link']}.
            *Ссылка на клуб на сайте s95.ru*: https://s95.ru/clubs/{club['id']}
            Перейдите по последней ссылке и нажмите кнопку _Присоединиться_,
            чтобы установить клуб (вы должны быть залогинены)."""
            await message.answer(info, parse_mode='Markdown')
        else:
            await message.answer('Информация о вашем клубе не найдена. Проверьте настройки.')
    await bot.delete_message(message.chat.id, message.message_id)
