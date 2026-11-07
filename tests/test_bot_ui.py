from handlers.start import main_keyboard
from handlers.files import InlineKeyboardButton as styled_file_button


def test_main_menu_buttons_use_telegram_primary_style():
    keyboard = main_keyboard()
    assert keyboard.inline_keyboard
    assert all(button.style == "primary" for row in keyboard.inline_keyboard for button in row)


def test_file_actions_use_safe_button_colors():
    assert styled_file_button("Cancel", callback_data="cancel:current").style == "danger"
    assert styled_file_button("Create ZIP", callback_data="archive:create_finish:zip").style == "success"
    assert styled_file_button("PNG", callback_data="convert:png").style == "primary"
