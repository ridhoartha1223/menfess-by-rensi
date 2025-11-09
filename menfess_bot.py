import json
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

logging.basicConfig(level=logging.INFO)

# ========== KONFIGURASI (ubah manual di sini) ==========
API_TOKEN = "ISI_TOKEN_BOT_KAMU_DI_SINI"   # <-- isi token dari @BotFather
OWNER_ID = 123456789                       # <-- isi dengan numeric Telegram ID owner
CREDIT_PRICE = 10000                       # harga tampil (opsional)
# ======================================================

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# ======= FILE STORAGE =======
USERS_FILE = "users.json"
TARGETS_FILE = "targets.json"

def load_json_file(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        logging.exception("Gagal load %s: %s", path, e)
        return default

def save_json_file(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.exception("Gagal save %s: %s", path, e)

# users structure: { "<uid>": {"username": "name", "credits": 0, "menfess_sent": 0} }
users = load_json_file(USERS_FILE, {})
# targets structure:
# { "groups": [{"name":"...", "id":-100..., "username":"@..."}], "channel_id": -100... or None }
targets = load_json_file(TARGETS_FILE, {"groups": [], "channel_id": None})

def save_users():
    save_json_file(USERS_FILE, users)

def save_targets():
    save_json_file(TARGETS_FILE, targets)

# ======= STATE TRACKERS =======
waiting_caption = {}         # {user_id_str: {"type":"photo"/"video", "file_id": "..."}}
waiting_broadcast = {}       # {owner_id: True}
waiting_gift_amount = {}     # {owner_id: amount_int}
# New: owner flows for manage groups / channel
waiting_add_target = {}      # {owner_id: "group" / "channel"}
waiting_remove_choice = {}   # {owner_id: True} (when owner in delete flow, we use inline buttons)
waiting_channel_update = {}  # {owner_id: True} waiting for new channel id input

# ======= UTILS =======
def ensure_user_entry(user: types.User):
    uid = str(user.id)
    if uid not in users:
        users[uid] = {"username": user.username or "", "credits": 0, "menfess_sent": 0}
        save_users()
    else:
        # update username if changed
        cur = user.username or ""
        if users[uid].get("username") != cur:
            users[uid]["username"] = cur
            save_users()

def find_user_by_username(username: str):
    uname = username.replace("@", "").lower()
    for uid, d in users.items():
        if (d.get("username") or "").lower() == uname:
            return uid, d
    return None, None

# ======= KEYBOARDS & UI =======
def owner_panel_kb(owner_username: str):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📢 Broadcast", callback_data="owner_broadcast"),
        types.InlineKeyboardButton("📊 Statistik", callback_data="owner_stats"),
        types.InlineKeyboardButton("👥 Daftar User", callback_data="owner_list_users"),
        types.InlineKeyboardButton("💰 Gift Credit", callback_data="owner_gift"),
        types.InlineKeyboardButton("➕ Kelola Grup", callback_data="owner_manage_groups"),
        types.InlineKeyboardButton("📦 Channel Arsip", callback_data="owner_channel_archive")
    )
    text = f"👑 Owner Panel\n━━━━━━━━━━━━━━\nOwner: @{owner_username}\n\nPilih aksi:"
    return text, kb

def gift_amount_kb():
    kb = types.InlineKeyboardMarkup(row_width=5)
    kb.add(
        types.InlineKeyboardButton("1️⃣", callback_data="gift_amount_1"),
        types.InlineKeyboardButton("2️⃣", callback_data="gift_amount_2"),
        types.InlineKeyboardButton("3️⃣", callback_data="gift_amount_3"),
        types.InlineKeyboardButton("4️⃣", callback_data="gift_amount_4"),
        types.InlineKeyboardButton("5️⃣", callback_data="gift_amount_5")
    )
    return kb

def manage_groups_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ Tambah Grup", callback_data="manage_add_group"),
        types.InlineKeyboardButton("❌ Hapus Grup", callback_data="manage_remove_group"),
        types.InlineKeyboardButton("🔁 Refresh List", callback_data="manage_refresh_list"),
        types.InlineKeyboardButton("◀️ Kembali", callback_data="owner_back")
    )
    return kb

def list_groups_kb():
    # build inline buttons for each group (for deletion)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for idx, g in enumerate(targets.get("groups", [])):
        label = f"{g.get('name') or '(no name)'} — {g.get('username') or g.get('id')}"
        kb.add(types.InlineKeyboardButton(label, callback_data=f"remove_group_{idx}"))
    kb.add(types.InlineKeyboardButton("◀️ Kembali", callback_data="owner_back"))
    return kb

def channel_archive_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("✏️ Ubah Channel Arsip", callback_data="change_channel_archive"),
        types.InlineKeyboardButton("◀️ Kembali", callback_data="owner_back")
    )
    return kb

# ======= BASIC COMMANDS =======
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    ensure_user_entry(message.from_user)
    uid = str(message.from_user.id)
    credits = users[uid]['credits']
    text = (
        "👋 *Selamat datang di Menfess Premium Bot!*\n\n"
        "💌 Kirim menfess (teks, foto, video) secara anonim ke grup.\n\n"
        "📦 1 Menfess = 1 Credit\n"
        f"💰 Harga: Rp{CREDIT_PRICE:,} / Credit\n\n"
        f"Saldo kamu saat ini: *{credits} Credit*\n\n"
        "Perintah cepat:\n"
        "`/mycredit` → Cek saldo\n"
        "`/topupinfo` → Info pembelian credit\n\n"
        "Owner panel hanya untuk owner bot."
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Hubungi Owner", url=f"tg://user?id={OWNER_ID}"))
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

@dp.message_handler(commands=['mycredit'])
async def cmd_mycredit(message: types.Message):
    ensure_user_entry(message.from_user)
    uid = str(message.from_user.id)
    await message.answer(f"💳 Saldo kamu saat ini: *{users[uid]['credits']} Credit*", parse_mode="Markdown")

@dp.message_handler(commands=['topupinfo'])
async def cmd_topupinfo(message: types.Message):
    text = (
        "💰 *Cara Top Up Credit Menfess*\n\n"
        f"1️⃣ Harga: Rp{CREDIT_PRICE:,} / 1 Credit\n"
        "2️⃣ Kirim pembayaran ke owner bot.\n"
        "3️⃣ Setelah bayar, kirim bukti ke owner.\n"
        "4️⃣ Owner akan menambahkan credit kamu manual.\n\n"
        "Gunakan perintah `/mycredit` untuk cek saldo."
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💬 Chat Owner", url=f"tg://user?id={OWNER_ID}"))
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

# ======= OWNER PANEL =======
@dp.message_handler(commands=['owner'])
async def cmd_owner(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Kamu bukan owner bot ini.")
        return
    owner_username = message.from_user.username or str(message.from_user.id)
    text, kb = owner_panel_kb(owner_username)
    await message.answer(text, reply_markup=kb)

# ======= CALLBACKS owner panel =======
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("owner_"))
async def owner_panel_callbacks(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Hanya owner yang dapat menggunakan ini.", show_alert=True)
        return
    data = callback.data

    if data == "owner_broadcast":
        waiting_broadcast[callback.from_user.id] = True
        await callback.message.answer("🗣️ Kirimkan teks broadcast yang ingin dikirim ke semua user. (Ketik /cancel untuk batal)")
        await callback.answer()
        return

    if data == "owner_stats":
        total_users = len(users)
        total_menfess = sum(u.get("menfess_sent", 0) for u in users.values())
        total_groups = len(targets.get("groups", []))
        channel_info = targets.get("channel_id")
        text = (
            "📊 Statistik Bot\n\n"
            f"👥 Total user: {total_users}\n"
            f"✉️ Total menfess terkirim: {total_menfess}\n"
            f"🔗 Total grup tujuan: {total_groups}\n"
            f"📦 Channel arsip: {channel_info if channel_info else 'Belum diset'}\n"
        )
        await callback.message.answer(text)
        await callback.answer()
        return

    if data == "owner_list_users":
        if not users:
            await callback.message.answer("👥 Tidak ada user di database.")
            await callback.answer()
            return
        lines = []
        for uid, d in users.items():
            uname = "@" + d.get("username") if d.get("username") else "(no username)"
            lines.append(f"{uname} — {uid} — {d.get('credits',0)} credit — sent:{d.get('menfess_sent',0)}")
        CHUNK = 25
        for i in range(0, len(lines), CHUNK):
            await callback.message.answer("👥 Daftar User:\n\n" + "\n".join(lines[i:i+CHUNK]))
        await callback.answer()
        return

    if data == "owner_gift":
        kb = gift_amount_kb()
        await callback.message.answer("🎁 Pilih jumlah credit yang ingin diberikan:", reply_markup=kb)
        await callback.answer()
        return

    if data == "owner_manage_groups":
        kb = manage_groups_kb()
        # show current groups list in message too
        lines = []
        for g in targets.get("groups", []):
            lines.append(f"• {g.get('name') or '(no name)'} — {g.get('username') or g.get('id')}")
        list_text = "\n".join(lines) if lines else "(Belum ada grup terdaftar)"
        await callback.message.answer(f"📋 Daftar Grup Terdaftar:\n{list_text}", reply_markup=kb)
        await callback.answer()
        return

    if data == "owner_channel_archive":
        ch = targets.get("channel_id")
        ch_text = str(ch) if ch else "Belum diset"
        await callback.message.answer(f"📦 Channel Arsip saat ini: {ch_text}", reply_markup=channel_archive_kb())
        await callback.answer()
        return

    if data == "owner_back":
        owner_username = callback.from_user.username or str(callback.from_user.id)
        text, kb = owner_panel_kb(owner_username)
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()
        return

# ======= CALLBACKS gift amounts =======
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("gift_amount_"))
async def gift_amount_callback(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Hanya owner yang dapat menggunakan ini.", show_alert=True)
        return
    try:
        amount = int(callback.data.split("_")[-1])
    except:
        await callback.answer("Format jumlah tidak valid.")
        return
    waiting_gift_amount[callback.from_user.id] = amount
    await callback.message.answer(f"🎁 Kamu memilih memberi *{amount} credit*.\nSekarang kirim username penerima (contoh: @username).", parse_mode="Markdown")
    await callback.answer()

# ======= CALLBACKS manage groups =======
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("manage_"))
async def manage_groups_callbacks(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Hanya owner.", show_alert=True)
        return
    data = callback.data

    if data == "manage_add_group":
        waiting_add_target[callback.from_user.id] = "group"
        await callback.message.answer("➕ Kirimkan @username grup atau ID grup (contoh: @mygroup atau -1001234567890). Bot akan memeriksa apakah bot sudah admin & bisa pin.")
        await callback.answer()
        return

    if data == "manage_remove_group":
        if not targets.get("groups"):
            await callback.message.answer("❌ Belum ada grup untuk dihapus.")
            await callback.answer()
            return
        kb = list_groups_kb()
        await callback.message.answer("❌ Pilih grup yang ingin dihapus:", reply_markup=kb)
        await callback.answer()
        return

    if data == "manage_refresh_list":
        # simply re-display group list
        lines = []
        for g in targets.get("groups", []):
            lines.append(f"• {g.get('name') or '(no name)'} — {g.get('username') or g.get('id')}")
        list_text = "\n".join(lines) if lines else "(Belum ada grup terdaftar)"
        await callback.message.answer(f"📋 Daftar Grup Terdaftar:\n{list_text}")
        await callback.answer()
        return

# ======= CALLBACK remove specific group =======
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("remove_group_"))
async def remove_group_callback(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Hanya owner.", show_alert=True)
        return
    try:
        idx = int(callback.data.split("_")[-1])
        if idx < 0 or idx >= len(targets.get("groups", [])):
            await callback.answer("Index grup tidak valid.")
            return
        removed = targets["groups"].pop(idx)
        save_targets()
        await callback.message.answer(f"✅ Grup dihapus: {removed.get('name') or removed.get('username') or removed.get('id')}")
        await callback.answer()
    except Exception as e:
        logging.exception("error remove group: %s", e)
        await callback.answer("Terjadi kesalahan saat menghapus grup.", show_alert=True)

# ======= CALLBACK channel archive management =======
@dp.callback_query_handler(lambda c: c.data and c.data == "change_channel_archive")
async def change_channel_archive_callback(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Hanya owner.", show_alert=True)
        return
    waiting_channel_update[callback.from_user.id] = True
    await callback.message.answer("✏️ Kirimkan ID channel baru (contoh: -1001234567890) atau @username channel.")
    await callback.answer()

# ======= CANCEL command =======
@dp.message_handler(commands=['cancel'])
async def cmd_cancel(message: types.Message):
    uid = message.from_user.id
    removed = False
    if uid in waiting_broadcast:
        waiting_broadcast.pop(uid, None)
        await message.reply("✅ Proses broadcast dibatalkan.")
        removed = True
    if uid in waiting_gift_amount:
        waiting_gift_amount.pop(uid, None)
        await message.reply("✅ Proses gift dibatalkan.")
        removed = True
    if uid in waiting_add_target:
        waiting_add_target.pop(uid, None)
        await message.reply("✅ Proses tambah grup/channel dibatalkan.")
        removed = True
    if uid in waiting_channel_update:
        waiting_channel_update.pop(uid, None)
        await message.reply("✅ Proses ubah channel arsip dibatalkan.")
        removed = True
    if not removed:
        await message.reply("Tidak ada proses aktif yang perlu dibatalkan.")

# ======= TEXT HANDLER (central) =======
@dp.message_handler(content_types=['text'])
async def handle_text(message: types.Message):
    uid = message.from_user.id
    uid_str = str(uid)

    # Owner broadcast flow
    if uid in waiting_broadcast:
        text_to_send = message.text
        success = 0
        fail = 0
        for user_id_str in list(users.keys()):
            try:
                await bot.send_message(int(user_id_str), f"📢 *Broadcast dari Owner:*\n\n{text_to_send}", parse_mode="Markdown")
                success += 1
            except Exception:
                fail += 1
        waiting_broadcast.pop(uid, None)
        await message.reply(f"✅ Broadcast selesai. Terkirim ke {success} user. Gagal: {fail}.")
        return

    # Owner gift flow: waiting for username after choosing amount
    if uid in waiting_gift_amount:
        amount = waiting_gift_amount.pop(uid)
        username_text = message.text.strip()
        username = username_text.replace("@", "").strip()
        found_uid, found_data = find_user_by_username(username)
        if not found_uid:
            await message.reply("❌ Username tidak ditemukan di database. Pastikan user sudah /start dan username benar.")
            return
        users[found_uid]['credits'] = users[found_uid].get('credits', 0) + amount
        save_users()
        await message.reply(f"✅ @{username} telah menerima {amount} credit.")
        try:
            await bot.send_message(int(found_uid), f"🎁 Kamu menerima {amount} credit dari owner!\nSaldo sekarang: {users[found_uid]['credits']}")
        except Exception:
            pass
        return

    # Owner add group/channel flow: waiting for @username or id
    if uid in waiting_add_target:
        kind = waiting_add_target.pop(uid)
        identifier = message.text.strip()
        # normalize: if looks like -100... treat as int, else keep string username
        chat_id_or_username = None
        try:
            if identifier.startswith("-"):
                chat_id_or_username = int(identifier)
            else:
                chat_id_or_username = identifier  # could be @username or plain username
        except:
            chat_id_or_username = identifier

        # try to get chat info
        try:
            chat = await bot.get_chat(chat_id_or_username)
        except Exception as e:
            await message.reply(f"❌ Gagal mendapatkan info chat: {e}\nPastikan format benar dan bot sudah ada di grup/channel.")
            return

        # check if bot is admin and can pin (for groups)
        try:
            me = await bot.get_me()
            bot_user_id = me.id
            member = await bot.get_chat_member(chat.id, bot_user_id)
            # for channels, chat.type == "channel", bot must be admin (creator/administrator)
            can_pin = False
            if member.status in ("creator", "administrator"):
                # admin: check can_pin_messages if attribute exists (channels often allow)
                can_pin = getattr(member, "can_pin_messages", None)
                # if attribute is None (some channel types), assume True if admin
                if can_pin is None:
                    can_pin = True
            else:
                can_pin = False
        except Exception as e:
            await message.reply(f"❌ Gagal memeriksa status bot di chat: {e}")
            return

        if not can_pin:
            await message.reply("❌ Bot bukan admin atau tidak punya izin untuk pin message di chat ini. Silakan add bot sebagai admin dengan izin 'Pin messages'.")
            return

        # OK add to targets
        entry = {
            "name": chat.title or "",
            "id": chat.id,
            "username": ("@" + chat.username) if getattr(chat, "username", None) else None
        }
        # ensure no duplicates
        for g in targets.get("groups", []):
            if g.get("id") == entry["id"]:
                await message.reply("⚠️ Grup/channel sudah terdaftar sebelumnya.")
                return
        targets.setdefault("groups", []).append(entry)
        save_targets()
        await message.reply(f"✅ Berhasil menambahkan target:\n• {entry['name']} — {entry['username'] or entry['id']}")
        return

    # Owner channel update flow
    if uid in waiting_channel_update:
        waiting_channel_update.pop(uid, None)
        identifier = message.text.strip()
        try:
            if identifier.startswith("-"):
                ch_id = int(identifier)
            else:
                ch_id = identifier  # username
        except:
            ch_id = identifier
        try:
            chat = await bot.get_chat(ch_id)
        except Exception as e:
            await message.reply(f"❌ Gagal mendapatkan info channel: {e}\nPastikan bot sudah menjadi admin di channel.")
            return
        # verify bot admin in channel
        try:
            me = await bot.get_me()
            member = await bot.get_chat_member(chat.id, me.id)
            if member.status not in ("creator", "administrator"):
                await message.reply("❌ Bot bukan admin di channel tersebut. Tambahkan bot sebagai admin di channel.")
                return
        except Exception as e:
            await message.reply(f"❌ Gagal memeriksa status bot di channel: {e}")
            return
        targets["channel_id"] = chat.id
        save_targets()
        await message.reply(f"✅ Channel arsip berhasil diubah: {chat.id}")
        return

    # User waiting caption (photo/video previously)
    if uid_str in waiting_caption:
        data = waiting_caption.pop(uid_str)
        caption = message.text if message.text != "-" else None
        await kirim_menfess(uid_str, data["type"], data["file_id"], caption)
        return

    # Normal user text menfess
    ensure_user_entry(message.from_user)
    if users[uid_str]["credits"] <= 0:
        await message.answer("❌ Kamu tidak punya credit.\nKetik /topupinfo untuk info pembelian 💳")
        return
    await kirim_menfess(uid_str, "text", None, message.text)

# ======= MEDIA HANDLERS (photo/video) =======
@dp.message_handler(content_types=['photo', 'video'])
async def handle_media(message: types.Message):
    user = message.from_user
    ensure_user_entry(user)
    uid_str = str(user.id)
    if users[uid_str]["credits"] <= 0:
        await message.answer("❌ Kamu tidak punya credit.\nKetik /topupinfo untuk info pembelian 💳")
        return
    # if no caption, ask for caption
    if not message.caption:
        if message.photo:
            file_id = message.photo[-1].file_id
            media_type = "photo"
        else:
            file_id = message.video.file_id
            media_type = "video"
        waiting_caption[uid_str] = {"type": media_type, "file_id": file_id}
        await message.answer("🖊️ Kamu mau tambahkan teks untuk menfess ini?\nKetik teks-nya, atau kirim `-` kalau mau kirim tanpa teks.", parse_mode="Markdown")
    else:
        if message.photo:
            file_id = message.photo[-1].file_id
            media_type = "photo"
        else:
            file_id = message.video.file_id
            media_type = "video"
        await kirim_menfess(str(user.id), media_type, file_id, message.caption)

# ======= kirim menfess (ke semua grup + arsip channel) =======
async def kirim_menfess(user_id_str, media_type, file_id, caption):
    try:
        # debit and increment
        users[user_id_str]["credits"] = users[user_id_str].get("credits", 0) - 1
        users[user_id_str]["menfess_sent"] = users[user_id_str].get("menfess_sent", 0) + 1
        save_users()

        # send to each group in targets
        groups = targets.get("groups", [])
        success_groups = 0
        failed_groups = 0
        sent_reference = None
        for g in groups:
            gid = g.get("id")
            try:
                if media_type == "text":
                    sent = await bot.send_message(gid, f"💌 *Menfess baru:*\n\n{caption}", parse_mode="Markdown")
                elif media_type == "photo":
                    sent = await bot.send_photo(gid, file_id, caption=caption or "💌 Menfess tanpa teks")
                elif media_type == "video":
                    sent = await bot.send_video(gid, file_id, caption=caption or "🎥 Menfess video")
                else:
                    continue
                # try pin
                try:
                    await bot.pin_chat_message(gid, sent.message_id)
                except Exception:
                    # no permission or can't pin in that chat
                    logging.warning("Tidak bisa pin di grup %s (cek izin).", gid)
                success_groups += 1
                sent_reference = sent
            except Exception as e:
                logging.exception("Gagal kirim ke grup %s: %s", gid, e)
                failed_groups += 1

        # send archive to channel specified
        ch_id = targets.get("channel_id")
        if ch_id:
            try:
                if media_type == "text":
                    await bot.send_message(ch_id, f"🗂 *Arsip Menfess:*\n\n{caption}", parse_mode="Markdown")
                elif media_type == "photo":
                    await bot.send_photo(ch_id, file_id, caption=caption or "🗂 Arsip Menfess (foto)")
                elif media_type == "video":
                    await bot.send_video(ch_id, file_id, caption=caption or "🗂 Arsip Menfess (video)")
            except Exception as e:
                logging.exception("Gagal kirim arsip ke channel %s: %s", ch_id, e)

        # confirmation to user
        try:
            await bot.send_message(int(user_id_str), f"✅ Menfess berhasil dikirim ke {success_groups} grup. Gagal: {failed_groups}. Sisa credit: {users[user_id_str]['credits']}")
        except Exception:
            pass

    except Exception as e:
        logging.exception("Gagal proses menfess: %s", e)
        try:
            await bot.send_message(int(user_id_str), f"❌ Gagal mengirim menfess: {e}")
        except:
            pass

# ======= RUN =======
if __name__ == "__main__":
    logging.info("🤖 Menfess Bot (multi-group + single channel archive) aktif...")
    executor.start_polling(dp, skip_updates=True)
