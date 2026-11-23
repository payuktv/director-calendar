"""English interface strings keyed by their Russian originals."""

MESSAGES = {
    "Приложение": "Application",
    "План и категории": "Plan and categories",
    "Путь к журналу": "Log file path",
    "Разделы настроек": "Settings sections",
    "Поиск в истории": "Search history",
    "Фильтры": "Filters",
    "Данные изменены": "Details changed",
    "План зафиксирован": "Plan fixed",
    "Фильтры · {0}": "Filters · {0}",
    "В истории пока нет записей": "No history entries yet",
    "Открыть запись": "Open entry",
    "Записей на странице": "Entries per page",
    "Неизвестный период аналитики": "Unknown analytics period",
    "Строка": "Row",
    "С": "From",
    "По": "To",
    "Категории": "Categories",
    "В плане": "Planned",
    "Выполнено из плана": "Completed from plan",
    "Выполнено по дате факта/плана": "Completed by actual or planned date",
    "Частично": "Partial",
    "Отменено из плана": "Cancelled from plan",
    "Перенесено": "Rescheduled",
    "Не подтверждено": "Unconfirmed",
    "Провалено из плана — ассистент": "Failed from plan — assistant",
    "Провалено из плана — директор": "Failed from plan — director",
    "Отменено всего": "Total cancelled",
    "Провалено всего": "Total failed",
    "Провалено — ассистент": "Failed — assistant",
    "Провалено — директор": "Failed — director",
    "Исполнение, %": "Completion, %",
    "План, мин": "Planned, min",
    "Факт, мин": "Actual, min",
    "Вне плана, мин": "Unplanned, min",
    "План не зафиксирован, мин": "Plan not fixed, min",
    "Доля внепланового, %": "Unplanned share, %",
    "Доля — нижняя граница": "Share is a lower bound",
    "Ожидают фактического времени": "Awaiting actual times",
    "Сравнимых событий": "Comparable events",
    "Среднее абсолютное отклонение начала, мин": "Mean absolute start deviation, min",
    "Среднее абсолютное отклонение длительности, мин": "Mean absolute duration deviation, min",
    "Начало вне допуска": "Start outside tolerance",
    "Длительность вне допуска": "Duration outside tolerance",
    "Повторно учтено при пересечениях, мин": "Minutes counted twice due to overlaps",
    "Дней с зафиксированным планом": "Days with a fixed plan",
    "Дней с полной загрузкой Mail.ru": "Days fully synced with Mail.ru",
    "Дней в периоде": "Days in period",
    "Событий с предупреждением источника": "Events with a source warning",
    "Контролируемые": "Tracked",
    "Все": "All",
    "Да": "Yes",
    "Нет": "No",
    "Итого": "Total",
    "День": "Day",
    "{0} ч": "{0} h",
    "0 мин": "0 min",
    " мин": " min",
    "Нажми, чтобы открыть соответствующий список событий": "Click to open the corresponding events",
    ". Открыть список событий": ". Open event list",
    "Нет заполненных интервалов времени за этот период": "No time intervals recorded for this period",
    " ч": " h",
    "{0:%d.%m.%Y}\nПлан: {1}\nФакт: {2}\nВне плана: {3}\nНажми, чтобы открыть события дня": (
        "{0:%d.%m.%Y}\nPlanned: {1}\nActual: {2}\nUnplanned: {3}\nClick to open the day's events"
    ),
    "Неделя": "Week",
    "Месяц": "Month",
    "Предыдущий период": "Previous period",
    "Следующий период": "Next period",
    "Сегодня": "Today",
    "Экспорт сводки и дней за весь выбранный период": "Export the summary and daily totals for the selected period",
    "Только контролируемые категории": "Tracked categories only",
    "Как считаем": "How metrics are calculated",
    (
        "Исполнение: выполненные события / исходный зафиксированный план; проценты дней не усредняются."
        " Время: только заполненный факт со статусом «Выполнено» или «Частично», обрезанный границами "
        "периода. При выборе «Выполнено» пустой факт заполняется текущим временем события; его можно "
        "исправить. «Частично» без факта ожидает заполнения. Отмены и провалы считаются отдельно, "
        "включая дни без фиксации плана, по исходной дате, иначе текущей. У провала причину выбирает "
        "пользователь: ассистент или директор. Часы провалов не учитываются. Вне плана: локальные "
        "события постфактум и события, добавленные после фиксации их дня. Перенос зафиксированного "
        "события остаётся плановой работой. Если план не зафиксирован, происхождение работы неизвестно,"
        " а доля внепланового показана как нижняя граница (≥). Отклонения: факт минус исходное начало и"
        " длительность; в сводке — средние абсолютные значения по событиям с началом факта в периоде. "
        "Точный допуск включён в норму. Задачи исходного плана относятся к дате его начала; отсутствие "
        "факта — к исходной, иначе текущей дате. События на весь день не создают 24 часа и не требуют "
        "времени. Для зафиксированных событий контроль, категория плана и допуск берутся на момент "
        "фиксации."
    ): (
        "Completion is the number of completed events divided by the original fixed plan for the "
        "period. Actual time counts completed or partial events with recorded times and only includes "
        "time within the period. Marking an event as completed fills missing actual times from its "
        "current schedule. You can edit them afterwards. Partial events without actual times remain "
        "pending. Cancellations and failures are counted separately, even on days without a fixed plan."
        " They use the original date if available, otherwise the current date. For failures, select who"
        " was responsible, the assistant or the director. Failed events contribute no working time. "
        "Unplanned work includes retrospective local entries and events added after their day was "
        "fixed. Moving a planned event keeps it in the plan. Where the plan was never fixed, the origin"
        " of work is unknown and the unplanned share is a lower bound (≥). Start and duration "
        "deviations compare actual times with the original plan. The summary averages absolute "
        "deviations for events whose actual start falls within the period. A deviation exactly at the "
        "tolerance is within range. Planned events count on their original start date. Missing actual "
        "times count on the original date if available, otherwise the current date. All-day events "
        "contribute no hours and need no actual times. Fixed plans retain the category, tracking rules "
        "and tolerance in effect when the plan was fixed."
    ),
    "Исполнение исходного плана": "Original plan completion",
    "Доля внеплановой работы": "Share of unplanned work",
    "Подтверждённое время": "Confirmed time",
    "Отклонение начала · среднее |Δ|": "Mean absolute start deviation",
    "Отклонение длительности · |Δ|": "Mean absolute duration deviation",
    "Отменено": "Cancelled",
    "Провалено": "Failed",
    "Исходный план": "Original plan",
    "Факт": "Actual",
    "Вне плана": "Unplanned",
    "Динамика": "Trend",
    "Выполнено": "Completed",
    "Исполнение": "Completion",
    "План, ч": "Planned, h",
    "Факт, ч": "Actual, h",
    "По дням": "By day",
    "Категория": "Category",
    "Исходный план, мин": "Original plan, min",
    "Подтверждённый факт, мин": "Confirmed actual time, min",
    "Все события": "All events",
    "Провалено — все причины": "Failed — all causes",
    "Провалено · ассистент": "Failed · assistant",
    "Провалено · директор": "Failed · director",
    "Внеплановая работа": "Unplanned work",
    "Отклонения вне допуска": "Deviations outside tolerance",
    "Без зафиксированного плана": "No fixed plan",
    "Весь период": "Entire period",
    "Двойной щелчок или Enter — открыть карточку события": "Double-click or press Enter to open the event",
    "Событие": "Event",
    "Дата": "Date",
    "Статус": "Status",
    "Работа": "Work",
    "План / факт\nмин": "Plan / actual\nmin",
    "Начало\nΔ мин": "Start\nΔ min",
    "Длительность\nΔ мин": "Duration\nΔ min",
    "Допуск\nмин": "Tolerance\nmin",
    "Учёт времени": "Time tracking",
    "События": "Events",
    "Не удалось рассчитать аналитику: ": "Could not calculate analytics: ",
    "Отчёт недоступен": "Report unavailable",
    "{0} из {1} событий\nЧастично: {2} · перенесено: {3}": "{0} of {1} events\nPartial: {2} · rescheduled: {3}",
    "{0} из {1} факта\nДоля по времени": "{0} of {1} actual time\nShare by time",
    "Частично и ранее выполненные без факта\nНажми для заполнения": (
        "Partial and previously completed events without actual times\nClick to enter times"
    ),
    "Из исходного плана: {0}\nНажми, чтобы открыть события": "From original plan: {0}\nClick to open events",
    "Ассистент: {0} · директор: {1}\nИз исходного плана: {2}": "Assistant: {0} · director: {1}\nFrom original plan: {2}",
    "Исходный план: {0}\nТолько выполнено и частично": "Original plan: {0}\nCompleted and partial only",
    "Сравнимых событий: {0}\nВне допуска: {1}": "Comparable events: {0}\nOutside tolerance: {1}",
    "План зафиксирован: {0} из {1} дней": "Plan fixed on {0} of {1} days",
    "Полная загрузка Mail.ru: {0} из {1} дней": "Mail.ru fully synced on {0} of {1} days",
    "Происхождение {0} факта неизвестно: план не зафиксирован. ≥ — нижняя граница доли внепланового": (
        "{0} of actual time has no fixed plan. ≥ marks the lower bound of the unplanned share"
    ),
    "Факт пересекается: {0} мин учтено повторно при суммировании событий": (
        "Actual intervals overlap: {0} min counted twice when adding event times"
    ),
    "Проверить состояние в Mail.ru: {0} событий": "Check in Mail.ru: {0} events",
    "Ассистент: {0} · директор: {1}": "Assistant: {0} · director: {1}",
    "Событий: {0}. Двойной щелчок или Enter — открыть карточку": "{0} events. Double-click or press Enter to open an event",
    "По исходному плану": "In original plan",
    "План не зафиксирован": "Plan not fixed",
    "Не заполнено": "Not entered",
    "Факт подтверждён": "Actual time confirmed",
    "Весь день": "All day",
    "Нет факта в периоде": "No actual time in period",
    "Исходный план: ": "Original plan: ",
    "Актуальный план: ": "Current plan: ",
    "Факт: ": "Actual: ",
    "Категория плана: {0}; текущая: {1}": "Planned category: {0}; current: {1}",
    "Δ начала: плюс — позже, минус — раньше. Δ длительности: плюс — дольше, минус — короче.": (
        "Positive start deviations mean later, negative mean earlier. Positive duration deviations mean"
        " longer, negative mean shorter."
    ),
    "Средние отклонения: ": "Mean deviations: ",
    "участвует": "included",
    "не участвует (нет сравнения или начало факта вне периода)": "excluded (no comparison or actual start outside period)",
    "Минуты в таблице ограничены периодом; отклонения рассчитаны по полным интервалам.": (
        "Minutes in the table are limited to the period. Deviations use the complete intervals."
    ),
    "не заполнено": "not entered",
    "Экспорт аналитики за период": "Export analytics for period",
    "Не удалось сохранить аналитику": "Could not save analytics",
    "Данные и резервные копии": "Data and backups",
    "База данных: ": "Database: ",
    "Создавать копию каждый день при работе приложения": "Create a daily backup while the app is running",
    "Выбрать папку": "Choose folder",
    "Папка копий": "Backup folder",
    "Хранить автоматических копий": "Automatic backups to keep",
    (
        "По умолчанию храним 30 ежедневных копий. Ручные копии и копии перед восстановлением не "
        "удаляются автоматически. Можно выбрать папку на другом диске."
    ): (
        "The default is 30 daily backups. Manual backups and backups made before a restore are kept "
        "until you remove them. You can choose a folder on another drive."
    ),
    "Сохранить настройки копий": "Save backup settings",
    "Создать резервную копию": "Create backup",
    "Восстановить из копии…": "Restore from backup…",
    "Последняя автоматическая копия: ": "Last automatic backup: ",
    "ещё не создана": "none yet",
    "Папка резервных копий": "Backup folder",
    "Настройки копирования сохранены.": "Backup settings saved.",
    "Резервные копии": "Backups",
    "Восстановление базы": "Restore database",
    "Дождись завершения обновления Mail.ru и копирования данных.": "Wait for Mail.ru sync and backup operations to finish.",
    "Выбрать резервную копию": "Select a backup",
    "Базы данных (*.db *.sqlite);;Все файлы (*)": "Databases (*.db *.sqlite);;All files (*)",
    "Восстановить базу данных?": "Restore database?",
    (
        "Текущие события, история и настройки будут заменены данными из выбранной копии. Текущая папка "
        "резервных копий, включение автокопирования и число хранимых копий сохранятся. Перед заменой "
        "сохраним отдельную копию текущей базы. После успешного восстановления приложение закроется; "
        "открой его снова."
    ): (
        "This replaces your events, history and settings with the selected backup. Your current backup "
        "folder, automatic backup setting and retention count are preserved. A separate copy of your "
        "current database will be saved first. After the restore, reopen the application."
    ),
    "Началось обновление Mail.ru. Дождись его завершения.": "Mail.ru sync has started. Wait for it to finish.",
    "Восстанавливаем базу…": "Restoring database…",
    "Проверяем и сохраняем резервную копию…": "Checking and saving backup…",
    "Операция не завершена: ": "Operation incomplete: ",
    "База восстановлена": "Database restored",
    "Данные восстановлены. Открой приложение снова.\nСтраховая копия прежних данных:\n": (
        "Your data has been restored. Reopen the application.\nBackup of your previous data:\n"
    ),
    "Копия создана: ": "Backup created: ",
    "Резервная копия создана": "Backup created",
    "Копия создана более новой версией приложения. Сначала обнови приложение.": (
        "This backup was created by a newer version. Update the application first."
    ),
    "Это не резервная копия Director Calendar: отсутствуют таблицы приложения.": (
        "This is not a Director Calendar backup. Required tables are missing."
    ),
    "В копии обнаружены повреждения или нарушенные связи записей.": "This backup has damaged data or broken record links.",
    "В копии отсутствуют обязательные поля событий.": "Required event fields are missing from the backup.",
    "В копии отсутствует версия записи события.": "The event record version is missing from the backup.",
    "В копии отсутствуют обязательные поля приложения.": "Required application fields are missing from the backup.",
    "В копии есть событие без планового и фактического времени.": (
        "The backup contains an event without planned or actual times."
    ),
    "В копии отсутствуют правила зафиксированного плана.": "Fixed plan rules are missing from the backup.",
    "Не удалось прочитать резервную копию. Проверь, что выбран исправный файл базы данных.": (
        "Could not read the backup. Check that the selected database file is valid."
    ),
    "Размер базы превышает допустимые 512 МиБ.": "The database exceeds the 512 MiB limit.",
    "Не удалось подготовить автономный файл резервной копии.": "Could not prepare a standalone backup file.",
    "Некорректная сохранённая версия приложения. Выбери другую копию или обратись за помощью.": (
        "The saved application version is invalid. Choose another backup or contact support."
    ),
    (
        "База уже открывалась в более новой версии v{0}; установлена v{1}. Сначала обнови приложение "
        "или выбери более старую совместимую копию."
    ): (
        "This database was opened in v{0}. You have v{1}. Update the application or choose an older "
        "compatible backup."
    ),
    "Количество автоматических копий: от 1 до 365.": "Choose between 1 and 365 automatic backups.",
    "Для копий нужно выбрать папку.": "Choose a backup folder.",
    "Резервное копирование": "Backup",
    "Некорректное количество автоматических копий.": "Invalid automatic backup count.",
    "Выбери резервную копию, а не открытую рабочую базу.": "Select a backup file. The active database cannot be used here.",
    "База данных": "Database",
    "База занята другим процессом. Закрой остальные экземпляры приложения.": (
        "Another process is using the database. Close other instances of the app."
    ),
    "База занята другим процессом. Повтори восстановление после его закрытия.": (
        "Another process is using the database. Close it and try restoring again."
    ),
    "январь": "January",
    "февраль": "February",
    "март": "March",
    "апрель": "April",
    "май": "May",
    "июнь": "June",
    "июль": "July",
    "август": "August",
    "сентябрь": "September",
    "октябрь": "October",
    "ноябрь": "November",
    "декабрь": "December",
    "января": "January",
    "февраля": "February",
    "марта": "March",
    "апреля": "April",
    "мая": "May",
    "июня": "June",
    "июля": "July",
    "августа": "August",
    "сентября": "September",
    "октября": "October",
    "ноября": "November",
    "декабря": "December",
    "ПН": "MON",
    "ВТ": "TUE",
    "СР": "WED",
    "ЧТ": "THU",
    "ПТ": "FRI",
    "СБ": "SAT",
    "ВС": "SUN",
    " · Вне плана, факт": " · Unplanned, actual",
    "Вне плана · ": "Unplanned · ",
    " · Локально": " · Local",
    "Ещё {0} · список": "{0} more · show list",
    "+{0} событий": "+{0} events",
    "Лавандовый фон дня означает, что исходный план зафиксирован": "A lavender day background means the original plan is fixed",
    "Не удалось открыть хранилище паролей Windows. Введи пароль заново.": (
        "Could not open Windows Credential Manager. Enter your password again."
    ),
    "Не удалось обновить хранилище паролей Windows. Настройки не сохранены.": (
        "Could not update Windows Credential Manager. Settings were not saved."
    ),
    "Схема копии не соответствует Director Calendar. Выбери исходную копию приложения.": (
        (
        "This backup's database structure does not match Director Calendar. Select an original "
        "application backup."
    )
    ),
    "Проверка или копирование базы превысили допустимое время.": "Checking or copying the database took too long.",
    "Не найден компонент оконного запуска. Повтори установку приложения и создай ярлык снова.": (
        "The windowed launcher is missing. Reinstall the application and create the shortcut again."
    ),
    "Создание ярлыка на рабочем столе доступно в Windows.": "Desktop shortcuts are available on Windows.",
    "Не удалось создать ярлык. Проверь доступ к рабочему столу и повтори.": (
        "Could not create the shortcut. Check access to the desktop and try again."
    ),
    "На рабочем столе создан ярлык «Director Calendar».\n\nОткрывай календарь двойным щелчком по нему.": (
        "A Director Calendar shortcut has been created on the desktop.\n\nDouble-click it to open the calendar."
    ),
    "Ошибка приложения": "Application error",
    (
        "Возникла непредвиденная ошибка. Последнее действие могло не завершиться. Проверь результат и "
        "перезапусти приложение.\n"
        "\n"
    ): "An unexpected error occurred. Check whether your last action finished and restart the application.\n\n",
    "Диагностика сохранена в журнале. Он доступен в Настройках → Диагностика.": (
        "Diagnostic details were saved to the log. Open Settings → Diagnostics to find it."
    ),
    "Не удалось записать диагностику. Проверь доступ и свободное место в папке данных.": (
        "Could not save diagnostic details. Check permissions and free space in the data folder."
    ),
    "Диагностика": "Diagnostics",
    (
        "Журнал хранит тип ошибки и место в коде: без текстов ошибок, паролей и содержимого календаря. "
        "До четырёх файлов по 1 МБ; старые записи заменяются автоматически. Файлы никуда не "
        "отправляются."
    ): (
        "The log records error types and code locations. Calendar contents, passwords and error "
        "messages are excluded. Up to four 1 MB files are kept locally. Older entries are replaced "
        "automatically."
    ),
    "Открыть папку журнала": "Open log folder",
    "Скопировать путь": "Copy path",
    "Журнал доступен.": "Log available.",
    "Журнал недоступен. Проверь доступ и свободное место в папке данных.": (
        "Log unavailable. Check permissions and free space in the data folder."
    ),
    "Не удалось открыть папку. Скопируй путь и открой её через Проводник.": (
        "Could not open the folder. Copy the path and open it in File Explorer."
    ),
    "Путь к журналу скопирован.": "Log path copied.",
    (
        "Если факт не указан, при сохранении он заполнится по текущему времени события. Его можно "
        "изменить. События на весь день — без автозаполнения."
    ): (
        "Saving will fill empty actual times from the current schedule. You can edit them afterwards. "
        "All-day events are excluded."
    ),
    (
        "Укажи фактическое время. Пока оно не заполнено, событие будет ожидать его в аналитике (кроме "
        "событий на весь день)."
    ): (
        "Enter the actual times. Analytics will show the event as awaiting times until you do. All-day "
        "events are excluded."
    ),
    (
        "Событие не состоялось из-за указанного участника. Оно учитывается отдельно от отмен и не "
        "добавляет часы работы. Причину можно записать в примечании."
    ): (
        "This event did not take place because of the selected person. It is counted separately from "
        "cancellations and adds no working hours. You can record the reason in the notes."
    ),
    "Фактическое время учитывается в аналитике для статусов «Выполнено» и «Частично».": (
        "Analytics counts actual time for completed and partial events."
    ),
    "Создано событие": "Event created",
    "Создано локальное событие": "Local event created",
    "Удалено локальное событие": "Local event deleted",
    "Изменены данные события": "Event details changed",
    "Загружено из Mail.ru": "Imported from Mail.ru",
    "Обновлено из Mail.ru": "Updated from Mail.ru",
    "Нужна проверка в Mail.ru": "Check in Mail.ru",
    "Отмена согласована с источником": "Cancellation confirmed with source",
    "Зафиксирован исходный план": "Original plan fixed",
    "Добавлена категория": "Category added",
    "Изменён контроль категории": "Category tracking changed",
    "Изменён допуск времени": "Time tolerance changed",
    "Изменены настройки копий": "Backup settings changed",
    "Восстановлена база данных": "Database restored",
    "Удалены старые примеры": "Old samples removed",
    "Название": "Title",
    "Комментарий": "Notes",
    "Начало актуального плана": "Current plan start",
    "Окончание актуального плана": "Current plan end",
    "Начало исходного плана": "Original plan start",
    "Окончание исходного плана": "Original plan end",
    "Фактическое начало": "Actual start",
    "Фактическое окончание": "Actual end",
    "Начало расписания": "Schedule start",
    "Окончание расписания": "Schedule end",
    "Дата плана": "Plan date",
    "Источник": "Source",
    "Отсутствует в ответе Mail.ru": "Missing from Mail.ru response",
    "Отменено в Mail.ru": "Cancelled in Mail.ru",
    "Событие на весь день": "All-day event",
    "Исходный план на весь день": "All day in original plan",
    "Ежедневные резервные копии": "Daily backups",
    "Допустимое отклонение": "Allowed deviation",
    "Участие категории в контроле": "Category tracking",
    "Удалено старых примеров": "Old samples removed",
    "Использованная копия": "Backup used",
    "Страховая копия перед восстановлением": "Safety backup before restore",
    "Локально в приложении": "Local to this application",
    "Архив приложения": "Application archive",
    "включено": "on",
    "выключено": "off",
    "папка по умолчанию": "default folder",
    "да": "yes",
    "нет": "no",
    "нет данных": "no data",
    "Состояние в Mail.ru:": "Mail.ru status:",
    "Дополнительные данные": "Additional details",
    "Описание прежнего формата:\n": "Legacy description:\n",
    "Подробности не сохранены": "No details recorded",
    (
        "Событие не найдено в загруженном периоде Mail.ru. Проверь источник: это не подтверждает "
        "удаление события."
    ): (
        "The event was missing from the synced period in Mail.ru. Check the source to confirm its status."
    ),
    (
        "Событие отменено и отсутствует в полностью загруженном периоде Mail.ru. План, локальные данные"
        " и история сохранены. Дополнительная проверка не требуется."
    ): (
        "The cancelled event is absent from a fully synced Mail.ru period. Its plan, local data and "
        "history were kept. No further check is needed."
    ),
    "Запись истории": "History entry",
    "Закрыть": "Close",
    "Открыть событие": "Open event",
    "Событие удалено, находится в архиве или запись относится к настройкам": (
        "The event has been deleted or archived, or the entry is about settings"
    ),
    "Поиск по названию, действию и описанию изменений": "Search titles, actions and change details",
    "Сбросить фильтры": "Reset filters",
    "Обновить": "Refresh",
    "Все события или часть названия": "All events or part of a title",
    "Все события и настройки": "All events and settings",
    "Только настройки и обслуживание": "Settings and maintenance only",
    "По выбранной записи": "Selected entry",
    "Отфильтровать историю по событию из выбранной строки": "Filter history by the event in the selected row",
    "Дата изменения": "Change date",
    "Фильтр по дате записи в истории, включая обе границы": "Filter by history date, including both endpoints",
    "Когда изменено": "Changed",
    "Событие / объект": "Event / item",
    "Действие": "Action",
    "Что изменилось": "Changes",
    "Двойной щелчок или Enter — полное описание записи": "Double-click or press Enter for full details",
    "К началу": "First page",
    "← Новее": "← Newer",
    "Старее →": "Older →",
    "История ещё не загружена": "History has not loaded yet",
    "По {0}": "Show {0}",
    " · удалено": " · deleted",
    " · архив": " · archived",
    "{0}–{1} из {2}": "{0}–{1} of {2}",
    "Новых записей по фильтру: {0}. Нажми «Обновить», чтобы перейти к ним.": (
        "{0} new entries match the filter. Click Refresh to view them."
    ),
    "Двойной щелчок или Enter — полное описание записи.": "Double-click or press Enter for full details.",
    "По выбранным условиям записей нет. Измени или сбрось фильтры.": "No entries match. Change or reset the filters.",
    "Записи не показаны": "No entries shown",
    "В ФОКУСЕ": "IN FOCUS",
    "Выбери событие": "Select an event",
    "Нажми на встречу в календаре": "Click an event in the calendar",
    "ИСХОДНЫЙ ПЛАН": "ORIGINAL PLAN",
    "АКТУАЛЬНОЕ ВРЕМЯ": "CURRENT SCHEDULE",
    "ФАКТ": "ACTUAL",
    "Открыть карточку": "Open event",
    "Отметить выполненным": "Mark as completed",
    "Нажми на встречу, чтобы увидеть план и факт": "Click an event to see planned and actual times",
    "Не планировалось": "Unplanned",
    "Не зафиксирован": "Not fixed",
    "Не заполнен": "Not entered",
    "{0:%d.%m} – {1:%d.%m} · весь день": "{0:%d.%m} – {1:%d.%m} · all day",
    "{0:%d.%m.%Y} · весь день": "{0:%d.%m.%Y} · all day",
    "Ожидается фактическое время.": "Awaiting actual times.",
    "Распределение времени · минуты": "Time breakdown · minutes",
    "Здесь появится сравнение плана и подтверждённого факта": "Planned and confirmed actual times will appear here",
    "Не удалось получить доступ к папке данных приложения.": "Could not access the application data folder.",
    "Не удалось запустить подготовленное обновление. Открываем текущую версию.": (
        "Could not launch the prepared update. Opening the current version."
    ),
    "Не удалось открыть Director Calendar.": "Could not open Director Calendar.",
    "\n\nПодробности ошибки сохранены в:\n{0}": "\n\nError details were saved to:\n{0}",
    "\n\nНе удалось сохранить подробности ошибки. Проверь доступ к папке данных приложения.": (
        "\n\nCould not save error details. Check access to the application data folder."
    ),
    "Эта форма предназначена для локальных событий.": "This form is for local events.",
    "Локальное событие": "Local event",
    "Добавить событие": "Add event",
    "Сохраняется в приложении и не отправляется в Mail.ru.": "Saved locally on this computer.",
    "Что произошло или что нужно запланировать": "What happened or what needs to be scheduled",
    "Постфактум — вне плана": "Record past work as unplanned",
    "Запланировать локально": "Schedule locally",
    "Тип записи": "Entry type",
    "Указать фактическое время": "Enter actual times",
    "Факт: начало": "Actual start",
    "Факт: конец": "Actual end",
    "Результат, причина появления вне плана или другие подробности": "Outcome, reason for unplanned work or other details",
    "Исходный план зафиксирован и останется без изменений.": "The original plan is fixed.",
    "Удалить событие": "Delete event",
    "Событие зафиксированного плана можно отменить, сохранив исходный план.": (
        "Cancel a fixed-plan event to preserve its original plan."
    ),
    "Удалить эту локальную запись с сохранением истории": "Delete this local entry and keep its history",
    "Сохранить": "Save",
    "Создать": "Create",
    "Отмена": "Cancel",
    "План: начало": "Planned start",
    "План: конец": "Planned end",
    "Попадёт в исходный план только при его фиксации.": "This event will join the original plan when you fix the day.",
    "Будет учтено вне плана. Даже последующая фиксация дня не добавит его в исходный план.": (
        "This work will count as unplanned even if you fix the day later."
    ),
    "Удалить локальное событие?": "Delete local event?",
    "Удалить «{0}»? Запись об удалении останется в истории.": "Delete “{0}”? The deletion will remain in the history.",
    "Укажи HTTPS-ссылку CalDAV с calendar.mail.ru, без параметров и с / в конце.": (
        "Enter an HTTPS CalDAV URL on calendar.mail.ru with no query and a trailing slash."
    ),
    "Укажи полный адрес почты для входа.": "Enter your full email address to sign in.",
    "Неизвестный часовой пояс.": "Unknown time zone.",
    "Ответ календаря слишком большой. Данные не изменены.": "The calendar response is too large. Your data was preserved.",
    "Превышено время загрузки календаря. Данные не изменены.": "Calendar download timed out. Your data was preserved.",
    "адрес записи отсутствует или вне выбранного календаря": "record URL missing or outside the selected calendar",
    "достигнут лимит отдельных запросов": "individual request limit reached",
    "пустой ответ GET": "empty GET response",
    "Диапазон синхронизации должен быть от 1 до 366 дней.": "Choose a sync range between 1 and 366 days.",
    "Слишком много событий календаря. Данные не изменены.": "Too many calendar events. Your data was preserved.",
    "Повторы каждую секунду или минуту пока не поддерживаются. Данные не изменены.": (
        "Recurrences every second or minute are currently unsupported. Your data was preserved."
    ),
    "Слишком много повторов календаря. Данные не изменены.": "Too many calendar recurrences. Your data was preserved.",
    "Не удалось разобрать события календаря. Данные не изменены; проверь формат и часовые пояса.": (
        "Could not read calendar events. Check the format and time zones. Your data was preserved."
    ),
    "Введи пароль внешнего приложения.": "Enter an app password.",
    "Недопустимый диапазон синхронизации.": "Invalid sync range.",
    "Mail.ru отклонил доступ. Проверь логин, пароль приложения и права на календарь.": (
        "Mail.ru denied access. Check your sign-in email, app password and calendar permissions."
    ),
    "Mail.ru вернул код {0}. Проверь ссылку и повтори позже.": (
        "Mail.ru returned code {0}. Check the URL and try again later."
    ),
    "Mail.ru вернул неожиданный формат. Данные не изменены.": (
        "Mail.ru returned an unexpected format. Your data was preserved."
    ),
    "CalDAV: ресурс {0}, HTTP {1}. Данные не изменены.": "CalDAV resource {0} returned HTTP {1}. Your data was preserved.",
    "неизвестен": "unknown",
    "ресурс {0} из {1}: calendar-data 404; {2}": "resource {0} of {1}: calendar-data 404; {2}",
    "нет свойства; статусы: ": "property missing; statuses: ",
    "CalDAV: ресурс {0} из {1}, calendar-data: {2}. Данные не изменены.": (
        "CalDAV resource {0} of {1}, calendar-data: {2}. Your data was preserved."
    ),
    "нет статуса": "no status",
    "CalDAV вернул противоречивые данные одного события. Данные не изменены.": (
        "CalDAV returned conflicting data for one event. Your data was preserved."
    ),
    "Не удалось прочитать ни одной записи. ": "Could not read any records. ",
    ". Данные не изменены.": ". Your data was preserved.",
    "Не удалось подключиться к Mail.ru. Проверь интернет; локальные данные сохранены.": (
        "Could not connect to Mail.ru. Check your internet connection. Local data was preserved."
    ),
    "Не удалось прочитать ответ Mail.ru. Локальные данные не изменены.": (
        "Could not read the Mail.ru response. Your local data was preserved."
    ),
    "Не удалось обновить календарь. Локальные данные сохранены.": (
        "Could not sync the calendar. Your local data was preserved."
    ),
    "Календарь Mail.ru": "Mail.ru calendar",
    "Ссылка CalDAV": "CalDAV URL",
    "Полный адрес почты": "Full email address",
    "Логин": "Sign-in email",
    "Пароль внешнего приложения; пусто — использовать сохранённый": "App password; leave blank to use the saved password",
    "Пароль приложения": "App password",
    "Часовой пояс расписания": "Schedule time zone",
    "Сохранить пароль в хранилище Windows": "Save password in Windows Credential Manager",
    "Обновлять при запуске приложения": "Sync when the application starts",
    "Сохранить подключение и обновить": "Save connection and sync",
    "Обновить из Mail.ru": "Sync with Mail.ru",
    "Отменить обновление": "Cancel sync",
    "Последнее успешное обновление: ": "Last successful sync: ",
    "ещё не было": "none yet",
    (
        "Загружаем 30 дней до и 90 дней после выбранной даты. Время отображается в выбранном часовом "
        "поясе. Название и плановое время меняй в Mail.ru; категорию, факт и итоги — здесь. Исчезнувшие"
        " будущие события без фиксации и локальных отметок убираются из плана; остальные требуют "
        "проверки. Пароль не хранится в базе или GitHub."
    ): (
        "Sync covers the 30 days before and 90 days after the selected date. Times use the selected "
        "time zone. Edit titles and planned times in Mail.ru. Record categories, actual times and "
        "outcomes here. Future events missing from Mail.ru are removed from the current plan if their "
        "day is not fixed and they have no local changes. Other missing events are flagged for review. "
        "Passwords are kept outside the database and GitHub."
    ),
    " Не удалось сохранить результат попытки обновления.": " Could not save the sync attempt result.",
    "После появления событий часовой пояс менять нельзя: это изменит смысл сохранённого плана и факта.": (
        "Changing time zones after adding events would change the meaning of their times. The current "
        "time zone must be kept."
    ),
    "Замена календаря после импорта пока не поддерживается. Сначала сохрани резервную копию.": (
        "Changing calendars after import is currently unsupported. Save a backup first."
    ),
    "Введи созданный пароль внешнего приложения.": "Enter the app password you created.",
    "Не удалось сохранить подключение. Проверь настройки и повтори.": (
        "Could not save the connection. Check the settings and try again."
    ),
    "Сначала настрой подключение в разделе «Настройки → Mail.ru».": "Set up the connection in Settings → Mail.ru first.",
    "Введи пароль приложения в разделе «Настройки → Mail.ru» и сохрани подключение.": (
        "Enter your app password in Settings → Mail.ru and save the connection."
    ),
    "Обновляем календарь Mail.ru…": "Syncing the Mail.ru calendar…",
    "Не удалось начать обновление. Проверь настройки подключения.": (
        "Could not start the sync. Check your connection settings."
    ),
    "Mail.ru обновлён {0}: новых {1}, изменено {2}, убрано из плана {3}, требуют проверки {4}.": (
        "Mail.ru synced {0}: {1} new, {2} changed, {3} removed from the plan, {4} to review."
    ),
    (
        "Mail.ru загружен частично: новых {0}, изменено {1}; недоступных записей {2}. Прежние записи "
        "сохранены, исчезновения не проверялись. "
    ): (
        "Mail.ru partially synced: {0} new, {1} changed, {2} unavailable. Earlier entries were "
        "preserved. Missing events were not checked. "
    ),
    "Не удалось сохранить обновление. Предыдущие данные сохранены.": (
        "Could not save the sync. Your previous data was preserved."
    ),
    "Отменяем обновление Mail.ru…": "Cancelling Mail.ru sync…",
    "Предыдущий месяц": "Previous month",
    "Следующий месяц": "Next month",
    "Выбрать месяц или год": "Choose month or year",
    "Выбор месяца и года": "Choose month and year",
    "Выбрать год…": "Choose year…",
    "Год календаря": "Calendar year",
    "Выбери год": "Choose a year",
    "Выбрать": "Select",
    "В базе некорректные записи приложения. Выбери другую резервную копию.": (
        "The database contains invalid application records. Choose a different backup."
    ),
    "Выбери резервную копию, а не рабочую базу.": "Select a backup file instead of the active database.",
    "Не удалось открыть базу": "Could not open database",
    "Рабочая база недоступна или не прошла проверку.\n": "The working database is unavailable or failed validation.\n",
    "\n\nВосстановить из резервной копии? Исходные файлы будут сохранены отдельно.": (
        "\n\nRestore from a backup? The original files will be saved separately."
    ),
    "Выбрать исправную копию": "Select a valid backup",
    "База данных (*.db *.sqlite)": "Database (*.db *.sqlite)",
    "Подтвердить восстановление": "Confirm restore",
    (
        "Рабочие события, история и настройки будут заменены выбранной копией. Автоматические копии "
        "будут сохраняться ежедневно в стандартную папку рядом с базой; хранится 30 копий. Другую папку"
        " можно выбрать в настройках после восстановления. Продолжить?"
    ): (
        "This replaces your events, history and settings with the selected backup. Daily backups will "
        "use the default folder next to the database with 30 copies retained. You can choose another "
        "folder in Settings after restoring. Continue?"
    ),
    "Восстановление не выполнено": "Restore failed",
    "Открой приложение снова. Исходные файлы сохранены:\n": "Reopen the application. The original files were saved here:\n",
    "В базе некорректные настройки приложения. Выбери другую резервную копию.": (
        "The database contains invalid application settings. Choose a different backup."
    ),
    "нет в Mail.ru": "missing from Mail.ru",
    "проверить Mail.ru": "check Mail.ru",
    "Не найдено в Mail.ru": "Not found in Mail.ru",
    "отменено в Mail.ru": "cancelled in Mail.ru",
    "есть в Mail.ru": "present in Mail.ru",
    "Совещания": "Meetings",
    "Встречи": "Appointments",
    "Спорт": "Sport",
    "Личное": "Personal",
    "Дорога": "Travel",
    "Отдых": "Rest",
    "Резерв": "Buffer",
    "Интервал": "Interval",
    "{0}: неверный формат даты/времени": "{0}: invalid date or time",
    "{0}: время окончания должно быть позже начала": "{0}: end time must be later than start time",
    "Локально": "Local",
    "База создана более новой версией программы. Обнови приложение.": (
        "This database was created by a newer version. Update the application."
    ),
    "Не удалось обновить формат базы: нарушены связи записей.": (
        "Could not update the database format due to broken record links."
    ),
    "Не удалось обновить формат временных полей. Исходная база сохранена.": (
        "Could not update the time field format. The original database was preserved."
    ),
    "Недопустимое название категории": "Invalid category name",
    "Название категории должно содержать 1–60 символов": "Category names must contain 1–60 characters",
    "Укажи, контролировать ли категорию": "Choose whether to track this category",
    "Категория не найдена": "Category not found",
    "Допустимое отклонение: от 0 до 180 минут": "Allowed deviation must be between 0 and 180 minutes",
    "Мероприятие #{0} не найдено": "Event #{0} not found",
    "Название мероприятия должно содержать 1–200 символов": "Event titles must contain 1–200 characters",
    "Неизвестный статус": "Unknown status",
    "Выбери существующую категорию": "Choose an existing category",
    "Актуальный план": "Current plan",
    "Фактическое время": "Actual times",
    "{0}: укажи оба времени либо оставь оба пустыми": "{0}: enter both times or leave both empty",
    "{0}: укажи местное время без часового пояса": "{0}: enter local times without a time zone",
    "Укажи фактическое время внепланового события или интервал плана": (
        "Enter actual times for the unplanned event or specify a planned interval"
    ),
    "Некорректные данные события. Проверь название, примечание и время.": (
        "Invalid event details. Check the title, notes and times."
    ),
    "Событие уже удалено. Закрой карточку и обнови календарь.": (
        "The event was deleted. Close the event and refresh the calendar."
    ),
    "Событие не найдено": "Event not found",
    "Событие изменилось после открытия карточки. Изменения не сохранены. Закрой карточку и открой её снова.": (
        "The event was changed after you opened it. Close and reopen it before saving your changes."
    ),
    "Учёт доступен для событий Mail.ru и новых локальных событий.": (
        "Tracking is available for Mail.ru events and new local events."
    ),
    "Название и плановое время события меняются только в Mail.ru.": "Edit the title and scheduled times in Mail.ru.",
    "Недопустимые поля изменения": "Invalid fields to change",
    "Тип существующего локального события менять нельзя: сохрани план и факт раздельно.": (
        "The type of an existing local event cannot be changed. Keep planned and actual times separate."
    ),
    "Удалять можно только локальные события. События Mail.ru меняются в Mail.ru.": (
        "Only local events can be deleted here. Edit Mail.ru events in Mail.ru."
    ),
    "Событие входит в зафиксированный план. Вместо удаления выбери статус «Отменено».": (
        "This event belongs to a fixed plan. Set the status to Cancelled to keep its original plan."
    ),
    "Первоначальный план на эту дату уже зафиксирован": "The original plan for this date is already fixed",
    "Размер страницы: от 1 до 500 записей.": "Page size must be between 1 and 500 entries.",
    "Некорректная граница страницы истории.": "Invalid history page boundary.",
    "Дата «С» должна быть не позже даты «По».": "The From date must be on or before the To date.",
    "Выбери событие из истории.": "Choose an event from the history.",
    "Мероприятие": "Event",
    "Первоначально с": "Originally from",
    "Первоначально до": "Originally to",
    "Актуально с": "Currently from",
    "Актуально до": "Currently to",
    "Факт с": "Actual from",
    "Факт до": "Actual to",
    "Нет подтверждённого полного обновления Mail.ru за выбранный день.": (
        "There is no confirmed complete Mail.ru sync for the selected day."
    ),
    "Последнее обновление Mail.ru за этот день было частичным.": "The latest Mail.ru sync for this day was partial.",
    "Последняя попытка обновить Mail.ru за этот день завершилась ошибкой.": (
        "The last attempt to sync Mail.ru for this day failed."
    ),
    "Данные Mail.ru за этот день обновлялись более 30 минут назад. Расписание могло измениться.": (
        "Mail.ru was last synced for this day more than 30 minutes ago. The schedule may have changed."
    ),
    "Некорректные данные календаря. Данные не изменены.": "Invalid calendar data. Your data was preserved.",
    "Повторный идентификатор события в ответе календаря": "Duplicate event identifier in the calendar response",
    "Весь день (Mail.ru)": "All day (Mail.ru)",
    "Конфликт источника календаря": "Calendar source conflict",
    "Убрано из актуального плана Mail.ru": "Removed from the current Mail.ru plan",
    "Проваленное событие отсутствует в Mail.ru": "Failed event missing from Mail.ru",
    "требует проверки": "needs review",
    "Обновление отменено. Данные не изменены.": "Sync cancelled. Your data was preserved.",
    "Превышено время обработки календаря. Данные не изменены.": "Calendar processing timed out. Your data was preserved.",
    "Обработка календаря остановлена: превышен лимит ресурсов или ошибка процесса. Данные не изменены.": (
        "Calendar processing stopped due to a resource limit or process error. Your data was preserved."
    ),
    "Не удалось получить результат обработки календаря. Данные не изменены.": (
        "Could not retrieve the calendar processing result. Your data was preserved."
    ),
    "Не удалось выполнить действие": "Could not complete the action",
    "Учёт доступен только для событий Mail.ru.": "Tracking here is only available for Mail.ru events.",
    "Учёт события Mail.ru": "Mail.ru event details",
    "Карточка события": "Event details",
    (
        "Событие убрано из актуального расписания: его нет в загруженном периоде Mail.ru. Прежнее время"
        " и изменения сохранены в Истории."
    ): (
        "This event is absent from the synced Mail.ru period and has been removed from the current "
        "schedule. Its earlier times and changes are in History."
    ),
    "Актуальный план: начало": "Current plan start",
    "Актуальный план: конец": "Current plan end",
    "Название и актуальное время обновляются из Mail.ru. Категория, факт и комментарий сохраняются локально.": (
        "Mail.ru supplies the title and current times. The category, actual times and notes are saved locally."
    ),
    "Причина переноса, итог встречи и т. д.": "Reason for rescheduling, meeting outcome or other details",
    "🔒 Исходный план: {0} — не изменяется": "🔒 Original plan: {0} — fixed",
    "Director Calendar — расписание руководителя": "Director Calendar — Executive schedule",
    "Календарь": "Calendar",
    "Аналитика": "Analytics",
    "История": "History",
    "Настройки": "Settings",
    "Открыть обновление календаря": "Open calendar update",
    "Версия ": "Version ",
    "Рабочий ритм руководителя — в одном месте": "Your schedule at a glance",
    "Поиск в открытом периоде": "Search this period",
    "Обновить Mail.ru": "Sync Mail.ru",
    "Светлая тема": "Light theme",
    "Тёмная тема": "Dark theme",
    "Переключить на светлую тему": "Switch to light theme",
    "Переключить на тёмную тему": "Switch to dark theme",
    "История изменений": "Change history",
    "План, факт и качество учёта за выбранный период": (
        "Planned work, actual time and tracking quality for the selected period"
    ),
    "Добавить": "Add",
    "Добавить локальное событие · Ctrl+N": "Add a local event · Ctrl+N",
    "Список": "Agenda",
    "Расписание": "Schedule",
    "Зафиксировать план": "Fix plan",
    "Актуально": "Current",
    "Без подтверждения": "Unconfirmed",
    "Окна 07–19": "Gaps 07–19",
    "Статус события": "Event status",
    "Контроль времени": "Time tracking",
    "Допустимое отклонение от плана": "Allowed deviation from plan",
    "Сохранить настройки": "Save settings",
    "Новые настройки применяются при следующей фиксации плана. Правила уже зафиксированных дней сохраняются.": (
        "New settings apply the next time you fix a plan. Previously fixed days keep their original rules."
    ),
    "Категории и контроль выполнения": "Categories and completion tracking",
    "Отслеживать выполнение": "Track completion",
    "Название новой категории": "New category name",
    "Добавить категорию": "Add category",
    "Запуск приложения": "Application startup",
    "Создать ярлык на рабочем столе": "Create desktop shortcut",
    "Ярлык открывает календарь двойным щелчком, без окна командной строки.": (
        "Double-click the shortcut to open the calendar."
    ),
    "Подтверждённо вне плана. Без фиксации плана: ": "Confirmed unplanned work. On days without a fixed plan: ",
    ". Переносы исходного плана остаются плановыми.": ". Rescheduled events from the original plan still count as planned.",
    "Исходный план зафиксирован": "Original plan fixed",
    "Исходный план на выбранный день ещё не зафиксирован": "Original plan for this day has not been fixed yet",
    "  ·  Окна: ": "  ·  Gaps: ",
    "  ·  Пересечений: {0}": "  ·  Overlaps: {0}",
    " · отклонение": " · deviation",
    " · вне плана": " · unplanned",
    " · весь день": " · all day",
    "Двойной щелчок — открыть карточку": "Double-click to open the event",
    "Выбери мероприятие": "Select an event",
    "Выбери событие в календаре или списке.": "Choose an event in the calendar or agenda.",
    "Обновление календаря": "Calendar sync",
    "Дождись завершения обновления Mail.ru перед фиксацией плана.": (
        "Wait for Mail.ru sync to finish before fixing the plan."
    ),
    "Зафиксировать исходное расписание на {0}? Отменить фиксацию нельзя.": (
        "Fix the original schedule for {0}? This cannot be undone."
    ),
    " Рекомендуется сначала обновить календарь. Зафиксировать имеющиеся данные?": (
        " Sync the calendar first for the latest schedule. Fix the current data now?"
    ),
    "\n\nВ расписании с 07:00 до 19:00 есть свободные окна: ": "\n\nThere are gaps between 07:00 and 19:00: ",
    "\nОбнаружено пересечений: {0}": "\nOverlaps found: {0}",
    "Фиксация первоначального плана": "Fix original plan",
    "Началось обновление Mail.ru. Дождись его завершения и повтори фиксацию.": (
        "Mail.ru sync has started. Wait for it to finish and try fixing the plan again."
    ),
    "План сохранён": "Plan saved",
    "Зафиксировано мероприятий: {0}": "Events fixed: {0}",
    "Экспорт плана и факта": "Export plan and actual times",
    "Готово": "Done",
    "Отчёт сохранён:\n{0}": "Report saved:\n{0}",
    "Настройки сохранены": "Settings saved",
    "Ярлык создан": "Shortcut created",
    "На рабочем столе создан ярлык «Director Calendar».\nОткрывай календарь двойным щелчком по нему.": (
        "A Director Calendar shortcut was created on the desktop.\nDouble-click it to open the calendar."
    ),
    "Перезапустить": "Restart",
    "Позже": "Later",
    "Версия {0} скачана. Для установки нужен перезапуск.": "Version {0} has been downloaded. Restart to install it.",
    "Заверши открытую операцию и подтверди перезапуск ещё раз.": (
        "Finish the current operation and confirm the restart again."
    ),
    "Не удалось активировать обновление. Проверь обновления в настройках и попробуй снова.": (
        "Could not activate the update. Check for updates in Settings and try again."
    ),
    "Дождись завершения копирования или восстановления базы.": "Wait for the database backup or restore to finish.",
    "Приложение уже запущено или открывается. Дождись появления его окна.": (
        "The application is already running or starting. Wait for its window to appear."
    ),
    "Не удалось открыть обновление. Запусти календарь обычным ярлыком.": (
        "Could not open the update. Start the calendar from its regular shortcut."
    ),
    "Не удалось проверить обновления. Проверь соединение с интернетом и попробуй снова.": (
        "Could not check for updates. Check your internet connection and try again."
    ),
    "Не удалось проверить обновления: получен некорректный ответ.": "Could not check for updates. The response was invalid.",
    "Описание изменений пока не опубликовано.": "Release notes are not available yet.",
    "Проверка заняла слишком много времени. Попробуй снова.": "The check timed out. Try again.",
    "GitHub временно ограничил проверки. Попробуй позже.": "GitHub temporarily limited update checks. Try again later.",
    "Сведения об обновлениях пока недоступны. Попробуй позже.": (
        "Update information is currently unavailable. Try again later."
    ),
    "Пакет обновления не прошёл проверку. Попробуй проверить обновления ещё раз.": (
        "The update package failed verification. Check for updates again."
    ),
    "Загрузка прервалась. Проверь подключение и попробуй снова.": (
        "Download interrupted. Check your connection and try again."
    ),
    "Не удалось сохранить обновление. Проверь свободное место и права на папку приложения.": (
        "Could not save the update. Check free space and access to the application folder."
    ),
    "Не удалось подготовить обновление. Попробуй снова.": "Could not prepare the update. Try again.",
    "Не удалось запустить загрузку. Попробуй снова.": "Could not start the download. Try again.",
    "Истекло время подготовки обновления. Попробуй снова.": "Preparing the update timed out. Try again.",
    "Описание изменений": "Release notes",
    "Обновления приложения": "Application updates",
    "Обновление приложения": "Application update",
    "Установленная версия: {0}": "Installed version: {0}",
    "Проверять обновления при запуске и раз в сутки": "Check for updates at startup and once a day",
    "Скачивание и перезапуск требуют подтверждения.": "Downloads and restarts require confirmation.",
    "Установка обновлений доступна в сборке для Windows.": "Updates can be installed in the Windows build.",
    "Загрузка обновления": "Downloading update",
    "Проверить обновления": "Check for updates",
    "Об обновлении": "Update details",
    "Отменить загрузку": "Cancel download",
    "Загружается версия {0}": "Downloading version {0}",
    "Версия {0} готова к установке": "Version {0} is ready to install",
    "Доступна версия {0}": "Version {0} is available",
    "Загрузка завершена. Для установки перезапусти календарь.": (
        "Download complete. Restart the calendar to install the update."
    ),
    "Загрузка идёт в фоне. Календарём можно пользоваться.": "Download in progress. You can keep using the calendar.",
    "Размер загрузки: {0:.0f} МБ.": "Download size: {0:.0f} MB.",
    "Повторить загрузку": "Retry download",
    "Скачать обновление": "Download update",
    "Перезапустить и установить": "Restart and install",
    "Версия {0} скачана и ждёт установки.": "Version {0} has been downloaded and is ready to install.",
    "Проверяем последнюю опубликованную версию…": "Checking the latest published version…",
    "Доступна версия {0}.": "Version {0} is available.",
    "Установлена последняя опубликованная версия {0}.": "You have the latest published version, {0}.",
    "Установленная версия {0} новее последнего опубликованного выпуска {1}.": (
        "Your version {0} is newer than the latest published release, {1}."
    ),
    "Загружаем и проверяем версию {0}…": "Downloading and verifying version {0}…",
    "Загрузка отменена. Можно попробовать снова.": "Download cancelled. You can try again.",
    "Не удалось открыть подготовленное обновление. Попробуй снова.": "Could not open the prepared update. Try again.",
    "Язык приложения": "Application language",
    "Язык": "Language",
    "Автоматически": "Automatic",
    "Версия {0}": "Version {0}",
    "Последнее успешное обновление: {0}": "Last successful sync: {0}",
    "База данных: {0}": "Database: {0}",
    "Последняя автоматическая копия: {0}": "Last automatic backup: {0}",
    "Копия создана: {0}": "Backup created: {0}",
    "Операция не завершена: {0}": "Operation incomplete: {0}",
    "{0} Не удалось сохранить результат попытки обновления.": "{0} Could not save the sync attempt result.",
    "{0}. Открыть список событий": "{0}. Open event list",
    "Обслуживание базы": "Database maintenance",
}
