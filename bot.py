import asyncio
import logging
import os
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberAdministrator, ChatMemberOwner
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
import re

CHANNELS = [-1001234567890, -1009876543210, -1002480347141]

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "1008312062"))

if not BOT_TOKEN:
    raise ValueError(
        "BOT_TOKEN environment variable is required. Please set it in Secrets."
    )

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
tasks = {}
task_counter = 1


async def notify_owner(text: str):
    try:
        if "Задание #" in text:
            await bot.send_message(OWNER_ID, "📢 " + text)
    except:
        pass


@dp.message(F.message_thread_id == 2, Command(commands=['stats', 'report']))
async def handle_thread_commands(message: Message):
    try:
        member = await bot.get_chat_member(message.chat.id,
                                           message.from_user.id)
        if not isinstance(member, (ChatMemberAdministrator, ChatMemberOwner)):
            return
    except:
        return

    cmd = message.text.split()[0][1:].lower()

    if cmd == 'stats':
        if not tasks:
            await message.reply("Нет заданий")
            return

        stats_text = "📊 СТАТИСТИКА ЗАДАНИЙ:\n\n"
        for task_id, task in tasks.items():

            user_names = []
            for user_id in task['confirmed_users']:
                try:
                    user = await bot.get_chat(user_id)
                    name = f"@{user.username}" if user.username else user.first_name or "NoName"
                    user_names.append(name[:15])
                except:
                    user_names.append(f"ID{user_id}")

            users_str = ", ".join(user_names) if user_names else "пусто"
            stats_text += f"#{task['task_num']} 👥 {task['reaction_count']} | {users_str}\n"

        await message.reply(stats_text)

    elif cmd == 'report':
        if not tasks:
            await message.reply("Нет заданий для отчёта")
            return

        total_tasks = len(tasks)
        report_text = f"📈 ОТЧЕТ ({total_tasks} заданий)\n\n"

        user_stats = {}
        for task_id, task in tasks.items():
            for user_id in task['confirmed_users']:
                if user_id not in user_stats:
                    user_stats[user_id] = {'completed': 0, 'name': None}
                user_stats[user_id]['completed'] += 1

        if not user_stats:
            report_text += "👥 Никто не выполнил задания"
        else:
            sorted_users = sorted(user_stats.items(),
                                  key=lambda x: x[1]['completed'],
                                  reverse=True)

            for i, (user_id, stats) in enumerate(sorted_users):
                if stats['name'] is None:
                    try:
                        user = await bot.get_chat(user_id)
                        stats[
                            'name'] = f"@{user.username}" if user.username else user.first_name or f"ID{user_id}"
                    except:
                        stats['name'] = f"ID{user_id}"

                completed = stats['completed']
                username = stats['name']

                report_text += f"{username}: {completed}/{total_tasks}"

                if total_tasks - completed == 0:
                    report_text += " ⭐"
                else:
                    report_text += " ❌"

                report_text += "\n\n"

                if i >= 15:
                    break

        await message.reply(report_text)


@dp.message(F.message_thread_id == 2)
async def handle_post_link(message: Message):
                urls = re.findall(r'https?://[^\s]+', message.text or "")
                if not urls:
                    return

                global task_counter
                url = urls[0]
                creator = message.from_user
                creator_mention = f"[{creator.first_name}](tg://user?id={creator.id})"

                task_text = message.text.replace(url, "").strip()
                if not task_text:
                    task_text = "Выполни задание"

                task_id = message.message_id

                tasks[task_id] = {
                    'url': url,
                    'chat_id': message.chat.id,
                    'thread_id': 2,
                    'confirmed_users': set(),
                    'reaction_count': 0,
                    'task_num': task_counter,
                    'original_message_id': message.message_id,
                    'creator_id': creator.id,
                    'task_text': task_text
                }
                task_counter += 1

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Засчитать", callback_data=f"confirm_{task_id}")]
                ])

                try:
                    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
                except:
                    pass

                try:
                    bot_message = await bot.send_message(
                        chat_id=message.chat.id,
                        message_thread_id=2,
                        text=f"🔗 Пост #{tasks[task_id]['task_num']} от {creator.first_name}:\n\n{task_text}\n\n{url}\n\n👥 0 выполнили",
                        reply_markup=keyboard
                    )
                    tasks[task_id]['message_id'] = bot_message.message_id
                except:
                    pass  



@dp.callback_query(F.data.startswith('confirm_'))
async def confirm_reaction(callback: CallbackQuery):
    try:
        task_id = int(callback.data.split('_')[1])
    except:
        await callback.answer("Ошибка")
        return

    if task_id not in tasks:
        await callback.answer("Задание завершено")
        return

    task = tasks[task_id]
    user_id = callback.from_user.id

    if user_id in task['confirmed_users']:
        await callback.answer("Уже засчитано!", show_alert=True)
        return

    task['confirmed_users'].add(user_id)
    task['reaction_count'] += 1
    count = task['reaction_count']

    text = f"🔗 Пост #{task['task_num']}:\n{task['url']}\n\n👥 {count} выполнили"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"Засчитано ({count})",
                             callback_data=f"confirm_{task_id}")
    ]])

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer("✅ Засчитано!")


@dp.callback_query(F.data.startswith('stats_'))
async def show_stats(callback: CallbackQuery):
    try:
        task_id = int(callback.data.split('_')[1])
    except:
        await callback.answer("❌ Ошибка")
        return

    if task_id not in tasks:
        await callback.answer("❌ Нет данных")
        return

    task = tasks[task_id]
    await callback.answer(f"Выполнили: {task['reaction_count']}",
                          show_alert=True)


async def main():
    print("БОТ Запущен. Нужные комманды: /stats /report")
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
