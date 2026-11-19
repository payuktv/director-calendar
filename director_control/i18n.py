"""Interface language. Persisted calendar values always keep their original form."""
from .english import MESSAGES

LANGUAGE_CHOICES = ('auto', 'ru', 'en')
_language = 'ru'


def system_language():
    from PySide6.QtCore import QLocale
    locale = QLocale.system()
    languages = locale.uiLanguages()
    return languages[0] if languages else locale.name()


def select_language(choice):
    """Resolve the primary OS display language, independently of the app's Qt locale."""
    global _language
    if choice not in ('en', 'ru'):
        primary = system_language().replace('_', '-').partition('-')[0].lower()
        choice = 'ru' if primary == 'ru' else 'en'
    _language = choice
    return choice


def current_language():
    return _language


def tr(source):
    return MESSAGES.get(source, source) if _language == 'en' else source


def decimal_text(number):
    return number.replace('.', ',') if _language == 'ru' else number


def ui_locale():
    from PySide6.QtCore import QLocale
    return QLocale('ru_RU' if _language == 'ru' else 'en_GB')


def configure_widgets(choice):
    """Set the language before constructing widgets, including Qt's standard dialogs."""
    from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator
    language = select_language(choice)
    QLocale.setDefault(ui_locale())
    app = QCoreApplication.instance()
    if app is None or getattr(app, '_director_language', None) == language:
        return
    translator = getattr(app, '_director_translator', None)
    if translator is not None:
        app.removeTranslator(translator)
        translator.deleteLater()
    translator = None
    if language == 'ru':
        translator = QTranslator(app)
        folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if translator.load('qtbase_ru', folder):
            app.installTranslator(translator)
    app._director_translator = translator
    app._director_language = language
