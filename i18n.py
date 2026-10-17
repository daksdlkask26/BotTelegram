"""
Internationalization (i18n) module for the Telegram bot.
Manages language settings and text translations.
"""
from typing import Optional
from commands.dbconfig import db_connect, logger
from locales import translations

# Supported languages
SUPPORTED_LANGUAGES = ['en', 'vi']
DEFAULT_LANGUAGE = 'en'


def get_user_language(user_id: int) -> str:
    """
    Get user's preferred language from database.
    Returns default language if user not found or language not set.
    """
    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT language FROM users WHERE id_user = ?", (user_id,))
        row = cursor.fetchone()
        if row and row[0]:
            lang = row[0].strip().lower()
            if lang in SUPPORTED_LANGUAGES:
                return lang
    except Exception as e:
        logger.error(f"Error getting user language for {user_id}: {e}")
    finally:
        cursor.close()
        conn.close()
    return DEFAULT_LANGUAGE


def set_user_language(user_id: int, language: str) -> bool:
    """
    Set user's preferred language in database.
    Returns True if successful, False otherwise.
    """
    if language not in SUPPORTED_LANGUAGES:
        return False
    
    conn = db_connect()
    cursor = conn.cursor()
    try:
        # Check if user exists
        cursor.execute("SELECT id_user FROM users WHERE id_user = ?", (user_id,))
        if cursor.fetchone():
            # Update existing user
            cursor.execute("UPDATE users SET language = ? WHERE id_user = ?", (language, user_id))
        else:
            # User doesn't exist, will be created on /start
            pass
        conn.commit()
        logger.info(f"Set language for user {user_id} to {language}")
        return True
    except Exception as e:
        logger.error(f"Error setting user language for {user_id}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_text(user_id: int, key: str, **kwargs) -> str:
    """
    Get translated text for a given key and user's language.
    
    Args:
        user_id: User's Telegram ID
        key: Translation key (e.g., 'start.welcome', 'help.title')
        **kwargs: Variables to format into the text
    
    Returns:
        Translated text string
    """
    language = get_user_language(user_id)
    
    # Get translations dict for the language (fallback to default)
    lang_dict = translations.get(language, translations[DEFAULT_LANGUAGE])
    
    # Try to get the text directly using the key
    text = lang_dict.get(key)
    
    # If not found in current language, try default language
    if text is None:
        default_dict = translations.get(DEFAULT_LANGUAGE, {})
        text = default_dict.get(key)
    
    # If still not found, return key in brackets
    if text is None:
        logger.warning(f"Translation key '{key}' not found for language '{language}'")
        return f"[{key}]"
    
    # If text is a dict (shouldn't happen with flat keys), return key not found
    if isinstance(text, dict):
        logger.warning(f"Translation key '{key}' points to a dict, not a string")
        return f"[{key}]"
    
    # Format text with kwargs if provided
    if kwargs and isinstance(text, str):
        try:
            return text.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing format key {e} in translation key '{key}'")
            return text
    
    return text
