from handlers.start import main_keyboard
from handlers.files import (
    InlineKeyboardButton as styled_file_button,
    InlineKeyboardMarkup as file_markup,
)
from utils.chat_ui import navigation_keyboard


def test_main_menu_buttons_use_telegram_primary_style():
    keyboard = main_keyboard()
    assert keyboard.inline_keyboard
    assert all(button.style == "primary" for row in keyboard.inline_keyboard for button in row)


def test_file_actions_use_safe_button_colors():
    assert styled_file_button("Cancel", callback_data="cancel:current").style == "danger"
    assert styled_file_button("Create ZIP", callback_data="archive:create_finish:zip").style == "success"
    assert styled_file_button("PNG", callback_data="convert:png").style == "primary"


def test_every_file_flow_keyboard_gets_back_and_home_buttons():
    keyboard = file_markup([[styled_file_button("PDF Info", callback_data="pdf:info")]])
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "nav:back" in callbacks
    assert "menu:home" in callbacks


def test_result_navigation_keyboard_has_back_and_home():
    keyboard = navigation_keyboard()
    assert [button.callback_data for button in keyboard.inline_keyboard[0]] == ["nav:back", "menu:home"]


def test_markup_does_not_duplicate_existing_navigation_controls():
    keyboard = file_markup([[styled_file_button("Back", callback_data="nav:back")]])
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert callbacks.count("nav:back") == 1
    assert callbacks.count("menu:home") == 1
