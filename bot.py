import os
import logging
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Supabase Initialization
url: str = os.environ.get("SUPABASE_URL", "")
key: str = os.environ.get("SUPABASE_KEY", "")
if not url or not key:
    logger.error("Missing Supabase credentials in .env")

# Patch supabase-py to allow non-JWT 'sb_publishable' keys
import supabase._sync.client
import re
_original_match = re.match
def _mock_match(pattern, string, flags=0):
    if string == key and "sb_" in string:
        return True
    return _original_match(pattern, string, flags)
supabase._sync.client.re.match = _mock_match

supabase: Client = create_client(url, key)

# States for login conversation
AWAITING_EMAIL, AWAITING_PASSWORD = range(2)

# States for ask conversation
AWAITING_TITLE, AWAITING_DESC = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    try:
        response = supabase.table("telegram_users").select("*").eq("chat_id", str(chat_id)).execute()
        if response.data and len(response.data) > 0:
            await update.message.reply_text(
                f"Welcome back to the REC Portal Bot, {user.first_name}! 🎓\n\n"
                "You are already logged in.\n\n"
                "Available commands:\n"
                "/marks - Check your latest marks\n"
                "/announcements - View active announcements\n"
                "/ask - Submit a query to faculty\n"
                "/logout - Unlink your account"
            )
            return
    except Exception as e:
        logger.error(f"Database error on start: {e}")

    await update.message.reply_text(
        f"Hi {user.first_name}! Welcome to the REC Portal Bot. 🎓\n\n"
        "To access your marks, announcements, and queries, you need to link your REC account.\n\n"
        "Please use the command /login to begin."
    )

# --- LOGIN FLOW ---

async def login_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Let's link your account! 🔗\n\n"
        "Please enter your REC Portal Email address (or /cancel to stop):"
    )
    return AWAITING_EMAIL

async def login_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()
    context.user_data['email'] = email
    
    await update.message.reply_text(
        f"Great! Email: {email}\n\n"
        "Now, please enter your password (this will be deleted immediately after verification for security):"
    )
    return AWAITING_PASSWORD

async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    password = update.message.text.strip()
    email = context.user_data.get('email')
    chat_id = str(update.effective_chat.id)
    
    try:
        await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
        await update.message.reply_text("🔒 *Password message deleted for security.*", parse_mode='Markdown')
    except:
        pass

    await update.message.reply_text("Authenticating... ⏳")

    try:
        auth_response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        user_id = auth_response.user.id

        supabase.table("telegram_users").upsert({"chat_id": chat_id, "student_id": user_id}).execute()

        await update.message.reply_text(
            "✅ *Account linked successfully!*\n\n"
            "You can now use all bot features. Try these commands:\n"
            "/marks - Check your latest marks\n"
            "/announcements - View active announcements\n"
            "/ask - Submit a query", parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Login error: {e}")
        await update.message.reply_text(
            f"❌ Login failed. Error: {str(e)}\n\n"
            f"Email received: '{email}'\n"
            f"Pass received: '{password}'\n\n"
            "Please check your email and password and try /login again."
        )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Action cancelled.")
    return ConversationHandler.END


# --- FEATURE COMMANDS ---

async def get_student_id(chat_id: str):
    user_resp = supabase.table("telegram_users").select("student_id").eq("chat_id", chat_id).execute()
    if not user_resp.data:
        return None
    return user_resp.data[0]['student_id']

async def marks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    
    student_id = await get_student_id(chat_id)
    if not student_id:
        await update.message.reply_text("You need to /login first!")
        return
        
    await update.message.reply_text("Fetching your marks... 📊")
    
    try:
        marks_resp = supabase.table("marks").select("*").eq("student_id", student_id).execute()
        if not marks_resp.data:
            await update.message.reply_text("No marks found for your account yet.")
            return
            
        msg = "📝 *Your Marks*\n\n"
        for mark in marks_resp.data:
            msg += f"📖 *{mark.get('subject', 'Subject')}*\n"
            msg += f"Score: {mark.get('marks', 'N/A')}\n"
            msg += f"Total: {mark.get('total_marks', '100')}\n\n"
            
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Sorry, couldn't fetch your marks right now.")

async def announcements_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    if not await get_student_id(chat_id):
        await update.message.reply_text("You need to /login first!")
        return
        
    await update.message.reply_text("Fetching latest announcements... 📢")
    
    try:
        resp = supabase.table("announcements").select("*").order("date_posted", desc=True).limit(5).execute()
        if not resp.data:
            await update.message.reply_text("No announcements right now.")
            return
            
        for ann in resp.data:
            msg = f"📢 *{ann.get('title')}*\n\n"
            msg += f"{ann.get('content')}\n\n"
            msg += f"📅 _{ann.get('date_posted', '')[:10]}_"
            await update.message.reply_text(msg, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Sorry, couldn't fetch announcements right now.")


# --- ASK FLOW ---

async def ask_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = str(update.effective_chat.id)
    student_id = await get_student_id(chat_id)
    if not student_id:
        await update.message.reply_text("You need to /login first!")
        return ConversationHandler.END
        
    context.user_data['student_id'] = student_id
    
    await update.message.reply_text(
        "Let's submit a query to the faculty. 📝\n\n"
        "What is the *subject* or *title* of your query? (Type /cancel to stop)", parse_mode='Markdown'
    )
    return AWAITING_TITLE

async def ask_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['query_title'] = update.message.text
    
    await update.message.reply_text(
        "Got it. Now please type the *detailed description* of your query:", parse_mode='Markdown'
    )
    return AWAITING_DESC

async def ask_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title = context.user_data.get('query_title')
    desc = update.message.text
    student_id = context.user_data.get('student_id')
    
    await update.message.reply_text("Submitting your query... ⏳")
    
    try:
        supabase.table("queries").insert({
            "student_id": student_id,
            "title": title,
            "description": desc,
            "status": "pending"
        }).execute()
        
        await update.message.reply_text(
            "✅ *Query Submitted Successfully!*\n\n"
            "The faculty will review it soon and you will see the status update in the portal.", parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Failed to submit query. Please try again later.")
        
    return ConversationHandler.END


async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    try:
        supabase.table("telegram_users").delete().eq("chat_id", chat_id).execute()
        await update.message.reply_text("✅ You have been successfully logged out. Type /login to reconnect.")
    except:
        await update.message.reply_text("Failed to logout.")

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_bot_token_here":
        logger.error("Please set TELEGRAM_BOT_TOKEN in .env")
        return

    application = Application.builder().token(token).build()

    # Login Conversation Handler
    login_handler = ConversationHandler(
        entry_points=[CommandHandler("login", login_start)],
        states={
            AWAITING_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_email)],
            AWAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Ask Conversation Handler
    ask_handler = ConversationHandler(
        entry_points=[CommandHandler("ask", ask_start)],
        states={
            AWAITING_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_title)],
            AWAITING_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_desc)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("marks", marks_command))
    application.add_handler(CommandHandler("announcements", announcements_command))
    application.add_handler(CommandHandler("logout", logout_command))
    application.add_handler(login_handler)
    application.add_handler(ask_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # Start a dummy web server in a background thread to satisfy Render's free Web Service port requirement
    import threading
    from flask import Flask

    app = Flask(__name__)

    @app.route('/')
    def home():
        return "Telegram Bot is running!"

    def run_server():
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port, use_reloader=False)

    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()

    main()
