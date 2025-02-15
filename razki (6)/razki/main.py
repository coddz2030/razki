import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import BadRequest

# توكن البوت
TOKEN = "8007444939:AAEaVSIp-iiuo5QXOeh93pB8IYgksdqSatw"

# تهيئة قاعدة البيانات
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()

    # إنشاء جدول المستخدمين
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            spent INTEGER DEFAULT 0,
            level TEXT DEFAULT 'برونزي',
            referrals TEXT DEFAULT '[]'
        )
    """)

    # إنشاء جدول التعاملات
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service TEXT,
            cost INTEGER,
            timestamp DATETIME,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    conn.commit()
    conn.close()

# تحميل بيانات المستخدم
def get_user_data(user_id):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()

    if user_data:
        level = user_data[3]
        # حساب الخصم بناءً على المستوى
        discounts = {
            "برونزي": 0,
            "فضي": 5,
            "ذهبي": 7,
            "بلاتنيوم": 10,
            "الماسي": 15,
        }
        discount = discounts.get(level, 0)

        return {
            "user_id": user_data[0],
            "balance": user_data[1],
            "spent": user_data[2],
            "level": level,
            "referrals": eval(user_data[4]) if user_data[4] else [],
            "discount": discount,  # إضافة الخصم
        }
    return None

# حفظ بيانات المستخدم
def save_user_data(user_id, balance=None, spent=None, level=None, referrals=None, **kwargs):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()

    user_data = get_user_data(user_id)
    if not user_data:
        cursor.execute("""
            INSERT INTO users (user_id, balance, spent, level, referrals)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, balance or 0, spent or 0, level or "برونزي", str(referrals or [])))
    else:
        cursor.execute("""
            UPDATE users
            SET balance = ?, spent = ?, level = ?, referrals = ?
            WHERE user_id = ?
        """, (
            balance if balance is not None else user_data["balance"],
            spent if spent is not None else user_data["spent"],
            level if level is not None else user_data["level"],
            str(referrals) if referrals is not None else str(user_data["referrals"]),
            user_id,
        ))

    conn.commit()
    conn.close()

# إضافة تعاملة جديدة
def add_transaction(user_id, service, cost):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO transactions (user_id, service, cost, timestamp)
        VALUES (?, ?, ?, ?)
    """, (user_id, service, cost, datetime.now()))
    conn.commit()
    conn.close()

# إشعار صاحب البوت
async def notify_owner(context: ContextTypes.DEFAULT_TYPE, user_id: int, service: str, cost: int):
    owner_id = 6601006479  # ايدي صاحب البوت
    message = (
        f"تمت عملية شراء جديدة!\n\n"
        f"👤 المستخدم: {user_id}\n"
        f"🛒 الخدمة: {service}\n"
        f"💸 التكلفة: {cost} نقطة"
    )
    await context.bot.send_message(chat_id=owner_id, text=message)

# دالة لإضافة رصيد
async def add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != 6601006479:  # التحقق من أن الأمر من صاحب البوت
        await update.message.reply_text("عذرًا، هذا الأمر متاح فقط لصاحب البوت.")
        return

    try:
        # الحصول على معرف المستخدم والمبلغ من الرسالة
        args = context.args
        if len(args) != 2:
            await update.message.reply_text("استخدام خاطئ! يرجى استخدام الأمر كالتالي:\n/addbalance <user_id> <المبلغ>")
            return

        target_user_id = int(args[0])
        amount = int(args[1])

        # إضافة الرصيد
        user_data = get_user_data(target_user_id)
        if not user_data:
            user_data = {"balance": 0, "spent": 0, "level": "برونزي", "referrals": []}

        user_data["balance"] += amount

        # إزالة user_id من user_data لتجنب التكرار
        user_data.pop("user_id", None)

        # حفظ البيانات
        save_user_data(target_user_id, **user_data)

        # إرسال تأكيد لصاحب البوت
        await update.message.reply_text(f"تمت إضافة {amount} نقطة إلى المستخدم {target_user_id}.")

        # إرسال إشعار للمستخدم
        await context.bot.send_message(chat_id=target_user_id, text=f"تمت إضافة {amount} نقطة إلى حسابك! 🎉")

    except (ValueError, IndexError):
        await update.message.reply_text("استخدام خاطئ! يرجى استخدام الأمر كالتالي:\n/addbalance <user_id> <المبلغ>")

# دالة لمعالجة أمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    referral_id = None

    # التحقق من وجود رابط إحالة
    if context.args:
        referral_id = int(context.args[0])

    # إضافة المستخدم الجديد إذا لم يكن موجودًا
    user_data = get_user_data(user_id)
    if not user_data:
        save_user_data(user_id, balance=0, referrals=[])

        # إضافة 50 نقطة للمستخدم الذي قام بالإحالة
        if referral_id and get_user_data(referral_id):
            referrer_data = get_user_data(referral_id)
            referrer_data["balance"] += 50
            referrer_data["referrals"].append(user_id)
            save_user_data(referral_id, **referrer_data)
            await context.bot.send_message(chat_id=referral_id, text=f"تمت إضافة 50 نقطة إلى حسابك بسبب إحالة جديدة! 🎉")

    # الرسالة الترحيبية
    welcome_message = (
        "مرحبًا بك عزيزي الزائر! 🙌\n\n"
        "نقدم لك أفضل خدمات السوشيال ميديا بأقل الأسعار في العالم العربي! 🚀\n\n"
        "اختر إحدى الخيارات التالية لتبدأ:"
    )

    # أزرار القائمة الرئيسية (ثلاثة أعمدة)
    keyboard = [
        [
            InlineKeyboardButton("تيكتوك 📱", callback_data="tiktok"),
            InlineKeyboardButton("يوتيوب 🎥", callback_data="youtube"),
            InlineKeyboardButton("انستغرام 📸", callback_data="instagram"),
        ],
        [
            InlineKeyboardButton("فيسبوك 🌐", callback_data="facebook"),
            InlineKeyboardButton("بروفيل 👤", callback_data="profile"),
            InlineKeyboardButton("هدايا 🎁", callback_data="gifts"),
        ],
        [
            InlineKeyboardButton("شحن الحساب 💳", callback_data="recharge"),
            InlineKeyboardButton("تواصل معنا 📞", callback_data="contact"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(welcome_message, reply_markup=reply_markup)

# دالة لمعالجة زر "شحن الحساب"
async def handle_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # رسالة شحن الحساب
    recharge_message = (
        "💳 **شحن الحساب**\n\n"
        "يمكنك شحن كل خدمة على حدة أو شحن حسابك مرة واحدة والحصول على رصيد إضافي 10%!\n\n"
        "يرجى التواصل مع صاحب البوت عبر المجموعة العالمية لمعرفة التفاصيل."
    )

    keyboard = [
        [InlineKeyboardButton("رجوع ↩️", callback_data="back_to_main")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(recharge_message, reply_markup=reply_markup)

# دالة لمعالجة اختيار المنصة
async def handle_platform_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "tiktok":
        # أزرار خدمات تيكتوك (ثلاثة أعمدة)
        keyboard = [
            [
                InlineKeyboardButton("زيادة مشتركين 👥", callback_data="tiktok_subscribers"),
                InlineKeyboardButton("زيادة مشاهدات فيديو 🎬", callback_data="tiktok_views"),
            ],
            [
                InlineKeyboardButton("لايكات ❤️", callback_data="tiktok_likes"),
                InlineKeyboardButton("حفظ الفيديو 💾", callback_data="tiktok_saves"),
            ],
            [
                InlineKeyboardButton("رجوع ↩️", callback_data="back_to_main"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("اختر خدمة تيكتوك:", reply_markup=reply_markup)

    elif query.data == "tiktok_subscribers":
        # قوائم زيادة مشتركين تيكتوك
        keyboard = [
            [
                InlineKeyboardButton("100 مشترك = 100 دج 🤑", callback_data="confirm_tiktok_100"),
                InlineKeyboardButton("230 مشترك = 200 دج 🤑", callback_data="confirm_tiktok_230"),
            ],
            [
                InlineKeyboardButton("500 مشترك = 280 دج 🤑", callback_data="confirm_tiktok_500"),
                InlineKeyboardButton("1000 مشترك = 630 دج 🤑", callback_data="confirm_tiktok_1000"),
            ],
            [
                InlineKeyboardButton("رجوع ↩️", callback_data="back_to_tiktok"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "يمكنك الحصول على مشتركين لحسابك اجانب 🤤🤤⭐:\n\n"
            "✅ قائمة 100 مشترك = (100 دج عشرالاف فليكسي) بالضمان 20 يوم.\n"
            "✅ قائمة 230 مشترك = (200 دج عشرينلف فليكسي) بالضمان 20 يوم.\n"
            "✅ قائمة 500 مشترك = (280 دج 28الف فليكسي) بالضمان 30 يوم.\n"
            "✅ قائمة 1000 مشترك = (630 دج ثلاثة و سبعين الف) مضمونين ينقصو نعوضلك.\n\n"
            "⭐⭐ اجوتي صحابك و ادي خصم 5% على اي عرض ⭐⭐",
            reply_markup=reply_markup,
        )

    elif query.data == "tiktok_views":
        # قوائم زيادة مشاهدات فيديو تيكتوك
        keyboard = [
            [
                InlineKeyboardButton("1000 مشاهدة = 80 دج 🤑", callback_data="confirm_tiktok_1000_views"),
                InlineKeyboardButton("3000 مشاهدة = 170 دج 🤑", callback_data="confirm_tiktok_3000_views"),
            ],
            [
                InlineKeyboardButton("5000 مشاهدة = 300 دج 🤑", callback_data="confirm_tiktok_5000_views"),
                InlineKeyboardButton("15 ألف مشاهدة = 600 دج 🤑", callback_data="confirm_tiktok_15000_views"),
            ],
            [
                InlineKeyboardButton("رجوع ↩️", callback_data="back_to_tiktok"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "اختر عرض زيادة مشاهدات فيديو لتيكتوك:\n\n"
            "✅ 1000 مشاهدة = (80 دج ثمنالاف فليكسي): يمكن تقسيمها على 4 فيديوهات.\n"
            "✅ 3000 مشاهدة = (170 دج سبعطاش نلف): يمكن تقسيمها على 6 فيديوهات.\n"
            "✅ 5000 مشاهدة = (300 دج ثلاثينلف): يمكن تقسيمها على 7 فيديوهات.\n"
            "✅ 15 ألف مشاهدة = (600 دج بريدي موب): يمكن تقسيمها على +10 فيديوهات + 10 مشتركين مجاناً.\n\n"
            "⭐⭐ اجوتي صحابك و ادي خصم 5% على اي عرض ⭐⭐",
            reply_markup=reply_markup,
        )

    elif query.data == "back_to_main":
        # العودة إلى القائمة الرئيسية
        await start(update, context)

    elif query.data == "back_to_tiktok":
        # العودة إلى قائمة تيكتوك
        await handle_platform_selection(update, context)

    elif query.data == "profile":
        # عرض البروفيل
        user_id = query.from_user.id
        user_data = get_user_data(user_id) or {"balance": 0, "spent": 0, "level": "برونزي", "referrals": [], "discount": 0}
        level = user_data["level"]
        balance = user_data["balance"]
        spent = user_data["spent"]
        referrals = user_data["referrals"]
        discount = user_data["discount"]

        # شعارات المستويات
        level_emojis = {
            "برونزي": "🥉",
            "فضي": "🥈",
            "ذهبي": "🥇",
            "بلاتنيوم": "🏅",
            "الماسي": "💎",
        }

        profile_message = (
            f"👤 **بروفيلك**\n\n"
            f"📊 الرصيد المتبقي: {balance:.2f} نقطة\n"
            f"💸 الرصيد المستهلك: {spent:.2f} نقطة\n"
            f"🏆 المستوى: {level} {level_emojis.get(level, '')}\n"
            f"🎉 الخصم الحالي: {discount}%\n\n"
            f"**المستويات والخصومات:**\n"
            f"🥉 برونزي: أقل من 1000 نقطة (خصم 0%)\n"
            f"🥈 فضي: بين 1000 و 3000 نقطة (خصم 5%)\n"
            f"🥇 ذهبي: بين 3000 و 7000 نقطة (خصم 7%)\n"
            f"🏅 بلاتنيوم: بين 7000 و 13000 نقطة (خصم 10%)\n"
            f"💎 الماسي: أكثر من 13000 نقطة (خصم 15%)\n\n"
            f"👥 عدد الإحالات: {len(referrals)}"
        )

        keyboard = [
            [InlineKeyboardButton("رجوع ↩️", callback_data="back_to_main")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(profile_message, reply_markup=reply_markup, parse_mode="Markdown")

    elif query.data == "gifts":
        # قسم الهدايا
        user_id = query.from_user.id
        referral_link = f"https://t.me/+m4XtfHJdvbdiNDY0?start={user_id}"

        gifts_message = (
            "🎁 قسم الهدايا:\n\n"
            f"رابط الإحالة الخاص بك:\n{referral_link}\n\n"
            "احصل على 50 نقطة لكل شخص يدخل عبر رابطك!"
        )

        keyboard = [
            [InlineKeyboardButton("رجوع ↩️", callback_data="back_to_main")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(gifts_message, reply_markup=reply_markup)

    elif query.data == "contact":
        # زر تواصل معنا
        keyboard = [
            [InlineKeyboardButton("زيارة الموقع 🌐", url="https://www.tiktok.com/zigaboost")],
            [InlineKeyboardButton("رجوع ↩️", callback_data="back_to_main")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("تواصل معنا عبر الموقع التالي:", reply_markup=reply_markup)

    elif query.data == "recharge":
        # معالجة زر "شحن الحساب"
        await handle_recharge(update, context)

    elif query.data.startswith("confirm_"):
        # تأكيد العملية
        service = query.data.replace("confirm_", "")
        user_id = query.from_user.id
        user_data = get_user_data(user_id)

        # تكلفة الخدمة
        costs = {
            "tiktok_100": 100,
            "tiktok_230": 200,
            "tiktok_500": 280,
            "tiktok_1000": 630,
            "tiktok_1000_views": 80,
            "tiktok_3000_views": 170,
            "tiktok_5000_views": 300,
            "tiktok_15000_views": 600,
        }
        cost = costs.get(service, 0)

        # تطبيق الخصم
        discount = user_data.get("discount", 0)
        discounted_cost = cost * (1 - discount / 100)

        if user_data["balance"] >= discounted_cost:
            # خصم الرصيد
            user_data["balance"] -= discounted_cost
            user_data["spent"] += discounted_cost
            # Remove user_id from dictionary before unpacking
            user_data_copy = user_data.copy()
            user_data_copy.pop('user_id', None)
            save_user_data(user_id, **user_data_copy)

            # إضافة التعاملة
            add_transaction(user_id, service, discounted_cost)

            # إرسال إشعار لصاحب البوت
            await notify_owner(context, user_id, service, discounted_cost)

            # رسالة نجاح العملية
            success_message = (
                f"تمت العملية بنجاح! 🎉\n\n"
                f"🛒 الخدمة: {service}\n"
                f"💸 التكلفة: {discounted_cost:.2f} نقطة (بعد خصم {discount}%)\n"
                f"📊 الرصيد المتبقي: {user_data['balance']:.2f} نقطة"
            )
            await query.edit_message_text(success_message)
        else:
            # رسالة عدم كفاية الرصيد
            await query.edit_message_text("عذرًا، رصيدك غير كافي لإكمال هذه العملية. 😢")

# الدالة الرئيسية لتشغيل البوت
def main():
    # تهيئة قاعدة البيانات
    init_db()

    application = Application.builder().token(TOKEN).build()

    # إضافة handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("addbalance", add_balance))
    application.add_handler(CallbackQueryHandler(handle_platform_selection))
    # بدء تشغيل البوت
    application.run_polling()

if __name__ == "__main__":
    main()
