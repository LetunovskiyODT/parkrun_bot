import re

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import Normalize, PowerNorm
from lxml.html import fromstring
from matplotlib.ticker import MaxNLocator

from bot_exceptions import ParsingException
from parkrun.helpers import ParkrunSite, min_to_mmss


async def parse_latest_results(parkrun: str):
    pr = re.sub('[- ]', '', parkrun)
    url = f'https://www.parkrun.ru/{pr}/results/latestresults/'
    parkrun_site = ParkrunSite(f'latestresults_{pr}')
    html = await parkrun_site.get_html(url)
    tree = fromstring(html)
    parkrun_date = tree.xpath('//span[@class="format-date"]/text()')[0]
    parkrun_iso_date = '-'.join(parkrun_date.split('/')[::-1])
    await parkrun_site.update_info(parkrun_iso_date)
    try:
        df = pd.read_html(html)[0]
    except Exception:
        raise ParsingException(f'Parsing latest results page for {parkrun} if failed.')
    return df, parkrun_date


async def make_latest_results_diagram(parkrun: str, pic: str, name=None, turn=0):
    parsed_results = await parse_latest_results(parkrun)
    df = parsed_results[0].copy()
    number_runners = len(df)
    df = df.dropna(thresh=3)
    df['Время'] = df['Время'].dropna() \
        .transform(lambda s: re.search(r'^(\d:)?\d\d:\d\d', s)[0]) \
        .transform(lambda mmss: sum(x * int(t) for x, t in zip([1 / 60, 1, 60], mmss.split(':')[::-1])))

    plt.figure(figsize=(5.5, 4), dpi=300)
    ax = df['Время'].hist(bins=32)
    ptchs = ax.patches
    med = df['Время'].median()
    m_height = 0
    personal_y_mark = 0

    norm = Normalize(0, med)

    if name:
        personal_res = df[df['Участник'].str.contains(name.upper())].reset_index(drop=True)
        if personal_res.empty:
            raise AttributeError
        personal_name = re.search(r'([^\d]+)\d.*', personal_res["Участник"][0])[1]
        personal_name = ' '.join(n.capitalize() for n in personal_name.split())
        personal_time = personal_res['Время'][0]
    else:
        personal_time = 0
        personal_name = ''

    for ptch in ptchs:
        ptch_x = ptch.get_x()
        color = plt.cm.viridis(norm(med - abs(med - ptch_x)))
        ptch.set_facecolor(color)
        if ptch_x <= med:
            m_height = ptch.get_height() + 0.3
        if ptch_x <= personal_time:
            personal_y_mark = ptch.get_height() + 0.3

    med_message = f'Медиана {int(med)}:{(med - int(med)) * 60:02.0f}'
    ax.annotate(med_message, (med - 0.5, m_height + 0.1), rotation=turn)
    plt.plot([med, med], [0, m_height], 'b')

    ldr_time = ptchs[0].get_x()
    ldr_y_mark = ptchs[0].get_height() + 0.3
    ldr_message = f'Лидер {int(ldr_time)}:{(ldr_time - int(ldr_time)) * 60:02.0f}'
    ax.annotate(ldr_message, (ldr_time - 0.5, ldr_y_mark + 0.2), rotation=90)
    plt.plot([ldr_time, ldr_time], [0, ldr_y_mark], 'r')

    lst_time = ptchs[-1].get_x() + ptchs[-1].get_width()
    lst_y_mark = ptchs[-1].get_height() + 0.3
    ax.annotate(f'Всего\nучастников {number_runners}', (lst_time - 0.6, lst_y_mark + 0.1), rotation=90)
    plt.plot([lst_time, lst_time], [0, lst_y_mark], 'r')

    if name and personal_time:
        ax.annotate(f'{personal_name}\n{int(personal_time)}:{(personal_time - int(personal_time)) * 60:02.0f}',
                    (personal_time - 0.5, personal_y_mark + 0.2),
                    rotation=turn, color='red', size=12, fontweight='bold')
        plt.plot([personal_time, personal_time], [0, personal_y_mark], 'r')

    ax.xaxis.set_major_locator(MaxNLocator(steps=[2, 4, 5], integer=True))
    ax.yaxis.set_major_locator(MaxNLocator(steps=[1, 2], integer=True))
    ax.set_xlabel("Результаты участников (минуты)")
    ax.set_ylabel("Результатов в диапазоне")
    plt.title(f'Результаты паркрана {parkrun} {parsed_results[1]}', size=10, fontweight='bold')
    plt.tight_layout()
    plt.savefig(pic)
    return open(pic, 'rb')


async def make_clubs_bar(parkrun: str, pic: str):
    parsed_results = await parse_latest_results(parkrun)
    df = parsed_results[0].copy()
    df = df.dropna(thresh=3)

    clubs = df['Клуб'].value_counts()
    norm = PowerNorm(gamma=0.6)
    colors = plt.cm.cool(norm(clubs.values))
    fig = plt.figure(figsize=(6, 6), dpi=200)
    ax = fig.add_subplot()
    ax.grid(False, axis='x')
    ax.grid(True, axis='y')
    ax.yaxis.set_major_locator(MaxNLocator(steps=[1, 2, 4, 8], integer=True))
    plt.xticks(rotation=80, size=8)
    plt.bar(clubs.index, clubs.values, color=colors)
    plt.title(f'Клубы на паркране {parkrun} {parsed_results[1]}', size=10, fontweight='bold')
    plt.ylabel('Количество участников')
    plt.tight_layout()
    plt.savefig(pic)
    return open(pic, 'rb')


async def review_table(parkrun: str):
    df, parkrun_date = await parse_latest_results(parkrun)
    count_total = len(df)
    if count_total == 0:
        return f'Паркран {parkrun} {parkrun_date} не состоялся.'
    df = df.dropna(thresh=3)
    df['Позиция м/ж'] = df[df.columns[2]].dropna()\
        .transform(lambda s: int(re.search(r'(?:Мужской|Женский)[ ]+(\d+)', s)[1]))
    df['Участник'] = df['Участник'].transform(lambda s: re.search(r'([^\d]+)\d.*|Неизвестный', s)[1])
    df['Личник'] = df['Время'].dropna().transform(lambda s: re.search(r'(?<=\d\d:\d\d)(.*)', s)[1])
    df['Время'] = df['Время'].dropna().transform(lambda s: re.search(r'^(\d:)?\d\d:\d\d', s)[0])
    df['result_m'] = df['Время']\
        .transform(lambda time: sum(x * int(t) for x, t in zip([1/60, 1, 60], time.split(':')[::-1])))
    pb = df['Личник'][df['Личник'] == 'Новый ЛР!'].count() * 100.0 / count_total
    median = min_to_mmss(df['result_m'].median())
    q95 = min_to_mmss(df['result_m'].quantile(q=0.95))
    q10 = min_to_mmss(df['result_m'].quantile(q=0.1))
    count_w = df['Пол'][df['Пол'].str.contains('Женский')].count()
    count_m = df['Пол'][df['Пол'].str.contains('Мужской')].count()
    count_unknown = count_total - count_m - count_w
    mean_w = min_to_mmss(df[df['Пол'].str.contains('Женский')]['result_m'].mean())
    mean_m = min_to_mmss(df[df['Пол'].str.contains('Мужской')]['result_m'].mean())
    report = f'*Паркран {parkrun}* состоялся {parkrun_date}.\n' \
             f'Всего приняло участие {count_total} человек, среди них {count_m} мужчин, ' \
             f'{count_w} женщин и {count_unknown} неизвестных.\n' \
             f'_Установили личник_: {pb:.1f}% участников.\n' \
             f'_Средний результат_: у мужчин {mean_m}, у женщин {mean_w}.\n' \
             f'_Медианное время_: {median}.\n' \
             f'_Квантили_: 10% - {q10}, 95% - {q95}.\n' \
             '*Результаты лидеров*\n' \
             f'Место | ===Участник=== | Время\n'
    for _, row in df[df['Позиция м/ж'] < 4].iterrows():
        report += f"  *{row['Позиция м/ж']}*      | {row['Участник']} | {row['Время']}\n"
    return report

if __name__ == '__main__':
    import asyncio

    loop = asyncio.get_event_loop()
    ff = loop.run_until_complete(review_table('Kolomenskoe'))
    print(ff)
