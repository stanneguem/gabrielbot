import sqlite3
import logging
from typing import Optional, Tuple
from telegram import Chat, ChatMember, ChatMemberUpdated, Update, InlineKeyboardMarkup, InlineKeyboardButton, \
    KeyboardButton, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters, CallbackContext, ConversationHandler
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

#nom de la base de donnee
DATABASE_FILE = 'non.db'
CHOOSE_TYPE, LINK_OR_FILE, FUNCTIONALITY, CONFIRM = range(4)
DESCRIBE_PROBLEM, LANGUAGE, SCREENSHOT, ERROR_MESSAGE, CONFIRMATION = range(5)
#creation des tables
def create_database():
    """Crée la base de données et la table si elles n'existent pas."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Créer la table des utilisateurs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            usernom TEXT,           
            rank INTEGER DEFAULT 0, -- Rang initialisé à 0
            nbaide INTEGER,
            nbpb INTEGER,
            isowner BOOLEAN DEFAULT FALSE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY,
            title TEXT
        )
    ''')

    conn.commit()
    conn.close()

async def increment_nbpb(user_id: int) -> bool:
  """Ajoute +1 au nbpb d'un utilisateur dans la base de données.

  Args:
      user_id: L'ID de l'utilisateur.

  Returns:
      True si l'opération a réussi, False sinon.
  """
  try:
    # Se connecter à la base de données
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Mettre à jour le nbpb de l'utilisateur
    cursor.execute("UPDATE users SET nbpb = nbpb + 1 WHERE id = ?", (user_id,))

    # Valider les changements
    conn.commit()

    # Fermer la connexion
    conn.close()

    return True
  except Exception as e:
    print(f"Erreur lors de la mise à jour du nbpb: {e}")
    return False


def ajouter_utilisateur(userid, username, rank, nbaide, nbpb, isowner=False):
    """Ajoute un nouvel utilisateur à la base de données.

    Si la table 'users' n'existe pas, elle sera créée.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    try:
        # Vérifiez si la table 'users' existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        table_exists = cursor.fetchone() is not None

        # Si la table n'existe pas, créez-la
        if not table_exists:
            cursor.execute('''
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    usernom TEXT,
                    rank INTEGER,
                    nbaide INTEGER,
                    nbpb INTEGER,
                    isowner BOOLEAN
                )
            ''')

        # Insérez l'utilisateur dans la table
        cursor.execute('''
            INSERT INTO users (id, usernom, rank, nbaide, nbpb, isowner)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (userid, username, rank, nbaide, nbpb, isowner))

        conn.commit()
        print(f"L'utilisateur {username} (ID: {userid}) a été ajouté avec succès.")

    except sqlite3.IntegrityError:
        print(f"L'utilisateur {username} (ID: {userid}) existe déjà dans la base de données.")
    finally:
        conn.close()

def ajouter_groupe(group_id, title):
    # Connexion à la base de données
    conn = sqlite3.connect('DevZhub.db')
    cursor = conn.cursor()

    # Exécution de la requête d'insertion
    try:
        cursor.execute('''
            INSERT INTO groups (id, title)
            VALUES (?, ?)
        ''', (group_id, title))
        conn.commit()
        print(f"Le groupe {title} (ID: {group_id}) a été ajouté avec succès.")
    except sqlite3.IntegrityError:
        print(f"Le groupe {title} (ID: {group_id}) existe déjà dans la base de données.")
    finally:
        conn.close()

def supprimer_utilisateur(userid):
    # Connexion à la base de données
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Exécution de la requête de suppression
    try:
        cursor.execute('''
            DELETE FROM users WHERE id = ?
        ''', (userid,))
        conn.commit()
        print(f"L'utilisateur avec l'ID {userid} a été supprimé avec succès.")
    except sqlite3.OperationalError:
        print(f"L'utilisateur avec l'ID {userid} n'existe pas dans la base de données.")
    finally:
        conn.close()

def extract_status_change(chat_member_update: ChatMemberUpdated) -> Optional[Tuple[bool, bool]]:
    """Takes a ChatMemberUpdated instance and extracts whether the 'old_chat_member' was a member
    of the chat and whether the 'new_chat_member' is a member of the chat. Returns None, if
    the status didn't change.
    """
    status_change = chat_member_update.difference().get("status")
    old_is_member, new_is_member = chat_member_update.difference().get("is_member", (None, None))

    if status_change is None:
        return None

    old_status, new_status = status_change
    was_member = old_status in [
        ChatMember.MEMBER,
        ChatMember.OWNER,
        ChatMember.ADMINISTRATOR,
    ] or (old_status == ChatMember.RESTRICTED and old_is_member is True)
    is_member = new_status in [
        ChatMember.MEMBER,
        ChatMember.OWNER,
        ChatMember.ADMINISTRATOR,
    ] or (new_status == ChatMember.RESTRICTED and new_is_member is True)

    return was_member, is_member

async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tracks the chats the bot is in."""
    result = extract_status_change(update.my_chat_member)
    if result is None:
        return
    was_member, is_member = result

    # Let's check who is responsible for the change
    cause_name = update.effective_user.full_name

    # Handle chat types differently:
    chat = update.effective_chat
    if chat.type == Chat.PRIVATE:
        if not was_member and is_member:
            # This may not be really needed in practice because most clients will automatically
            # send a /start command after the user unblocks the bot, and start_private_chat()
            # will add the user to "user_ids".
            # We're including this here for the sake of the example.
            logger.info("%s unblocked the bot", cause_name)
            context.bot_data.setdefault("user_ids", set()).add(chat.id)
        elif was_member and not is_member:
            logger.info("%s blocked the bot", cause_name)
            context.bot_data.setdefault("user_ids", set()).discard(chat.id)
    elif chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        if not was_member and is_member:
            logger.info("%s added the bot to the group %s", cause_name, chat.id)
            context.bot_data.setdefault("group_ids", set()).add(chat.id)
        elif was_member and not is_member:
            logger.info("%s removed the bot from the group %s", cause_name, chat.id)
            context.bot_data.setdefault("group_ids", set()).discard(chat.id)
    elif not was_member and is_member:
        logger.info("%s added the bot to the channel %s", cause_name, chat.title)
        context.bot_data.setdefault("channel_ids", set()).add(chat.id)
    elif was_member and not is_member:
        logger.info("%s removed the bot from the channel %s", cause_name, chat.title)
        context.bot_data.setdefault("channel_ids", set()).discard(chat.id)

async def greet_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Greets new users in chats and announces when someone leaves"""
    result = extract_status_change(update.chat_member)
    if result is None:
        return

    was_member, is_member = result
    cause_name = update.chat_member.from_user.mention_html()
    member_name = update.chat_member.new_chat_member.user.mention_html()
    member_id = update.chat_member.new_chat_member.user.id
    meber_name = update.chat_member.new_chat_member.user.full_name

    if not was_member and is_member:
        ajouter_utilisateur(member_id, meber_name, 0, 0, 0)
        await update.effective_chat.send_message(
            f"{member_name} 👋 Bienvenue dans notre communauté d'informaticiens ! 🎉"
            f"Nous sommes ravis de t'accueillir parmi nous. Si tu as des questions sur "
            f"le fonctionnement de la communauté ou si tu souhaites en savoir plus sur "
            f"les fonctionnalités de ce bot, n'hésite pas à m'écrire en privé. Je suis là pour t'aider !"
            f"Profite bien de ton séjour et à très bientôt ! 🚀"
            f"voici les liens vers les groupe de discution par theme"
            f" \n\n POUR LE WEB: https://t.me/+ZZw6tGLcjKxlNzI0 \n "
            f"POUR LE MOBILE : https://t.me/+_7qb_9IKVlo4ZmY8 \n"
            ,
            parse_mode=ParseMode.HTML,
        )
    elif was_member and not is_member:
        supprimer_utilisateur(member_id)
        await update.effective_chat.send_message(
            f"{member_name} is no longer with us. Thanks a lot, {cause_name} ...",
            parse_mode=ParseMode.HTML,
        )

async def start(update: Update, context: CallbackContext) -> None:

    user_id = update.effective_user.id

    # Connexion à la base de données
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Vérification si l'utilisateur est enregistré
    cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
    user_exists = cursor.fetchone() is not None

    # Fermeture de la connexion
    conn.close()

    if user_exists:
        messages = ("Bonjour à tous ! Bienvenue dans ce groupe !"
                    " ,Le bot est encore en développement, mais il y aura de "
                    "nouvelles fonctionnalités à venir. J'ai malheureusement "
                    "été pris par d'autres projets et je n'ai pas eu le temps de tout terminer. "
                    "😅,Vous avez remarqué que vous ne pouvez pas écrire dans le groupe ? C'est normal ! "
                    "Ce groupe servira de canal de diffusion pour les problèmes et les applications en test. "
                    "Vous pouvez rejoindre les autres groupes de test via les liens suivants :"
                    " \n\n POUR LE WEB: https://t.me/+ZZw6tGLcjKxlNzI0 \n "
                    "POUR LE MOBILE : https://t.me/+_7qb_9IKVlo4ZmY8 \n"
                    "Note que plus vous participer plus vous aurrez de chance de participer avec la communaute a des "
                    "projets open source")

        # Envoyer un message de bienvenue à l'utilisateur
        await update.message.reply_text(f"Ravi de te revoir ! "
                                        f"Voici la liste des commandes disponibles. Chaque commande te permettra"
                                        f" d'effectuer une action différente, {update.effective_user.first_name}! ")
        await update.message.reply_text(messages)
    else:
        # Envoyer un message indiquant que le bot n'est pas accessible à tout le monde
        await update.message.reply_text(
            "Désolé, ce bot n'est pas accessible à tout le monde. "
            "Contactez l'administrateur @Administrator pour plus d'informations."
        )

async def help_command(update: Update, context: CallbackContext) -> None:

    user_id = update.effective_user.id

    # Connexion à la base de données
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Vérification si l'utilisateur est enregistré
    cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
    user_exists = cursor.fetchone() is not None

    # Fermeture de la connexion
    conn.close()

    if user_exists:
        # Envoyer un message de bienvenue à l'utilisateur
        await update.message.reply_text(f"Desolee, {update.effective_user.first_name}! "
                                        f"mais Contactez l'administrateur pour plus d'informations.")
    else:
        # Envoyer un message indiquant que le bot n'est pas accessible à tout le monde
        await update.message.reply_text(
            "Désolé, ce bot n'est pas accessible à tout le monde. "
            "Contactez l'administrateur pour plus d'informations."
        )

async def get_user_info(update: Update, context: CallbackContext) -> None:
    """Fonction appelée lors de la commande /get_info.

    Récupère et affiche les informations d'un utilisateur.
    """
    user_id = update.effective_user.id

    # Connexion à la base de données
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Récupération des informations de l'utilisateur
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user_data = cursor.fetchone()

    # Fermeture de la connexion
    conn.close()

    if user_data:
        # Affichage des informations de l'utilisateur
        username = user_data[1] # Supposons que la colonne 'usernom' est à l'index 1
        rank = user_data[2]
        nbaide = user_data[3]
        nbpb = user_data[4]
        isowner = user_data[5]

        await update.message.reply_text(
            f"Informations de l'utilisateur {username} (ID: {user_id}):\n"
            f"Rang: {rank}\n"
            f"Nombre d'aides: {nbaide}\n"
            f"Nombre de points bonus: {nbpb}\n"
            f"Propriétaire: {'Oui' if isowner else 'Non'}"
        )
    else:
        # L'utilisateur n'est pas enregistré
        await update.message.reply_text("Vous n'etes pas membre de la communaute")

async def setting(update: Update, context: CallbackContext) -> None:
    """Fonction appelée lors de la commande /get_info.

    Récupère et affiche les informations d'un utilisateur.
    """
    user_id = update.effective_user.id

    # Connexion à la base de données
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Récupération des informations de l'utilisateur
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user_data = cursor.fetchone()

    # Fermeture de la connexion
    conn.close()

    if user_data:
        # Affichage des informations de l'utilisateur
        username = user_data[1] # Supposons que la colonne 'usernom' est à l'index 1
        rank = user_data[2]
        nbaide = user_data[3]
        nbpb = user_data[4]
        isowner = user_data[5]

        if isowner:
            await update.message.reply_text(f"Bienvenue a toi Admin {username} voila les commandes "
                                            f"pour la gestion du groupe"
                                            f"/list, /grads, /degrad ")
        else:
            await update.message.reply_text("Cet Partie est seulement pour les Admins")
    else:
        # L'utilisateur n'est pas enregistré
        await update.message.reply_text("Cet utilisateur n'est pas enregistré dans la base de données.")

async def test(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id

    # Connexion à la base de données
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Récupération des informations de l'utilisateur
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user_data = cursor.fetchone()

    # Fermeture de la connexion
    conn.close()

    if user_data:
        keyboard = [
            [KeyboardButton("site web"), KeyboardButton("mobile")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "S'agit-il d'une application mobile ou d'un site web ?"
            "Veuillez répondre par 'mobile' ou 'site web'.", reply_markup=reply_markup
        )
        return CHOOSE_TYPE
    else:
        # L'utilisateur n'est pas enregistré
        await update.message.reply_text(f"Cet utilisateur n'est pas enregistré dans la base de données. {user_id}")

async def me(update: Update, context: CallbackContext) -> None:
    """Fonction appelée lors de la commande /get_info.

    Récupère et affiche les informations d'un utilisateur.
    """
    user_id = update.effective_user.id

    # Connexion à la base de données
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Récupération des informations de l'utilisateur
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user_data = cursor.fetchone()

    # Fermeture de la connexion
    conn.close()

    if user_data:
        # Affichage des informations de l'utilisateur
        username = user_data[1] # Supposons que la colonne 'usernom' est à l'index 1
        rank = user_data[2]
        nbaide = user_data[3]
        nbpb = user_data[4]
        isowner = user_data[5]
        await update.message.reply_text(f"NOM: {username} \n"
                                        f"RANG: {rank} \n"
                                        f"Nombre de participassion: {nbpb}")
    else:
        # L'utilisateur n'est pas enregistré
        await update.message.reply_text("Cet utilisateur n'est pas enregistré dans la base de données.")

async def handle_type(update: Update, context: CallbackContext) -> int:
    """Handles the application type input."""
    app_type = update.message.text.lower()
    context.user_data["app_type"] = app_type
    if app_type == "site web":
        await update.message.reply_text("Veuillez me fournir le lien du site web.")
        return LINK_OR_FILE
    elif app_type == "mobile":
        await update.message.reply_text(
            "Veuillez me fournir le fichier exécutable de l'application mobile."
        )
        return LINK_OR_FILE
    else:
        await update.message.reply_text(
            "Réponse invalide. Veuillez répondre par 'mobile' ou 'site web'."
        )
        return CHOOSE_TYPE

async def handle_link_or_file(update: Update, context: CallbackContext) -> int:
    """Handles the link or file input."""
    app_type = context.user_data["app_type"]
    if app_type == "site web":
        context.user_data["link"] = update.message.text
    elif app_type == "mobile":
        context.user_data["file"] = update.message.document.file_id
    await update.message.reply_text("Veuillez me dire quelle fonctionnalité vous voulez tester en priorité.")
    return FUNCTIONALITY

async def handle_functionality(update: Update, context: CallbackContext) -> int:
    """Handles the functionality input."""
    context.user_data["functionality"] = update.message.text
    keyboard = [
        [KeyboardButton("oui"), KeyboardButton("non")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Veuillez confirmer que les liens ou le fichier que vous avez envoyé ne causeront pas de tort aux personnes qui vont faire le test. \n "
        "Cliquez sur oui pour confirmer ou non pour annuler.", reply_markup=reply_markup
    )
    return CONFIRM

async def confirm(update: Update, context: CallbackContext) -> int:
    """Handles the confirmation input."""
    grooupid = -1002488000748
    if update.message.text == "oui":
        # Send the information to the group
        if context.user_data['app_type'] == "site web":
            message = (
                f"Nouvelle demande de test de {update.effective_user.full_name} \n"
                f"\n"
                f"Type d'application: {context.user_data['app_type']} \n "
                f"\n"
                f"Lien/Fichier: {context.user_data.get('link')} \n"
                f"Fonctionnalité prioritaire: {context.user_data['functionality']}"
            )
            await context.bot.send_message(chat_id=grooupid, text=message)
        elif context.user_data['app_type'] == "mobile":
            message = (
                f"Nouvelle demande de test de {update.effective_user.full_name} \n"
                f"\n"
                f"Type d'application: {context.user_data['app_type']} \n "
                f"\n"
                f"Lien/Fichier: le ficchier est en dessous \n"
                f"Fonctionnalité prioritaire: {context.user_data['functionality']}"
            )
            await context.bot.send_message(chat_id=grooupid, text=message)
            await context.bot.send_document(chat_id=grooupid, document=context.user_data.get('file'),
                                            caption=f"{update.effective_user.full_name}")
        await increment_nbpb(update.effective_user.id)
        await update.message.reply_text("Merci! La demande de test a été envoyée au groupe.")
        return ConversationHandler.END

    elif update.message.text == "non":
        await update.message.reply_text("Processus annulé.")
        return ConversationHandler.END
    else:
        await update.message.reply_text("Veuillez répondre par /oui ou /non.")
        return CONFIRM




async def probleme(update: Update, context: CallbackContext) -> int:

    user_id = update.effective_user.id

    # Connexion à la base de données
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Récupération des informations de l'utilisateur
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user_data = cursor.fetchone()

    # Fermeture de la connexion
    conn.close()

    if user_data:
        await update.message.reply_text("Veuillez décrire votre problème.")
        return DESCRIBE_PROBLEM
    else:
        # L'utilisateur n'est pas enregistré
        await update.message.reply_text("Cet utilisateur n'est pas enregistré dans la base de données.")
    """Démarre la conversation."""

async def handle_problem_description(update: Update, context: CallbackContext) -> int:
    """Traite la description du problème."""
    context.user_data["problem_description"] = update.message.text
    await update.message.reply_text("Quel est le langage de programmation concerné ?")
    return LANGUAGE

async def handle_language(update: Update, context: CallbackContext) -> int:
    """Traite le langage de programmation."""
    context.user_data["language"] = update.message.text
    keyboard = [
        [ KeyboardButton("Non")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    await update.message.reply_text("Avez-vous une capture d'écran du problème ? ", reply_markup=reply_markup)
    return SCREENSHOT

async def handle_screenshot(update: Update, context: CallbackContext) -> int:
    """Traite la réponse à la question de la capture d'écran."""
    if update.message.text == "oui":
        await update.message.reply_text("Veuillez envoyer la capture d'écran.")
        return SCREENSHOT
    else:
        await update.message.reply_text("Quel est le message d'erreur qui s'affiche dans votre IDE ?")
        return ERROR_MESSAGE

async def handle_error_message(update: Update, context: CallbackContext) -> int:
    """Traite le message d'erreur."""
    context.user_data["error_message"] = update.message.text
    await update.message.reply_text("entre oui pour envoyer votre probleme ?")
    return CONFIRMATION

async def handle_confirmation(update: Update, context: CallbackContext) -> int:
    """Affiche les informations pour confirmation."""
    problem_description = context.user_data.get("problem_description", "")
    language = context.user_data.get("language", "")
    screenshot = context.user_data.get("screenshot", "")
    error_message = context.user_data.get("error_message", "")
    confirmation_message = (
        f"Voici les informations que vous avez fournies:\n\n"
        f"Description du problème: {problem_description}\n"
        f"Langage de programmation: {language}\n"
        f"Capture d'écran: {screenshot}\n"
        f"Message d'erreur: {error_message}\n\n"
        f"Veuillez confirmer ces informations. \n"
        f"Cliquez sur oui pour confirmer ou non pour recommencer."
    )
    keyboard = [
        [KeyboardButton("oui"), KeyboardButton("non")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(confirmation_message, reply_markup=reply_markup)
    return CONFIRMATION

async def confirme(update: Update, context: CallbackContext) -> int:
    """Confirme les informations."""
    grooupid = -1002488000748
    if update.message.text == "oui":
        # Envoyer les informations au groupe
        problem_description = context.user_data.get("problem_description", "")
        language = context.user_data.get("language", "")
        screenshot = context.user_data.get("screenshot", "")
        error_message = context.user_data.get("error_message", "")
        message = (
            f"Nouvelle demande d'aide:\n\n"
            f"Description du problème: {problem_description}\n"
            f"Langage de programmation: {language}\n"
            f"Capture d'écran: {screenshot}\n"
            f"Message d'erreur: {error_message}\n"
        )
        await context.bot.send_message(chat_id=grooupid, text=message)
        await update.message.reply_text("Merci! Votre demande d'aide a été envoyée au groupe.")
        await increment_nbpb(update.effective_user.id)
        return ConversationHandler.END
    elif update.message.text == "non":
        await update.message.reply_text("Veuillez recommencer en envoyant la commande /probleme.")
        return DESCRIBE_PROBLEM
    else:
        await update.message.reply_text("Veuillez répondre par oui ou non.")
        return CONFIRMATION

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token("7247373724:AAFiROYGTTWC5qvda-AOanefpMCfLP3rJCc").build()

    # Keep track of which chats the bot is in
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))


    # Handle members joining/leaving chats.
    application.add_handler(ChatMemberHandler(greet_chat_members, ChatMemberHandler.CHAT_MEMBER))

    # Add ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("test", test)],
        states={
            CHOOSE_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_type)],
            LINK_OR_FILE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link_or_file),
                MessageHandler(filters.Document.ALL, handle_link_or_file),
            ],
            FUNCTIONALITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_functionality),
            ],
            CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confirm),
            ],
        },
        fallbacks=[CommandHandler("de", test)],
    )

    # Add ConversationHandler
    conv_handlerpb = ConversationHandler(
        entry_points=[CommandHandler("probleme", probleme)],
        states={
            DESCRIBE_PROBLEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_problem_description)],
            LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_language)],
            SCREENSHOT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_screenshot),
                MessageHandler(filters.PHOTO, handle_screenshot)
            ],
            ERROR_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_error_message)],
            CONFIRMATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confirme),
            ],
        },
        fallbacks=[CommandHandler("probleme", probleme)],
    )
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('me', me))
    application.add_handler(conv_handler)
    application.add_handler(conv_handlerpb)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()