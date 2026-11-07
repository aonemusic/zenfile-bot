import asyncio
import json
import socket
from dataclasses import replace

import tornado.web
from telegram import Bot
from tornado.testing import AsyncHTTPTestCase

import bot as bot_module
from config import settings
from bot import HealthHandler, RootHandler, TelegramWebhookHandler


class WebhookHandlerTests(AsyncHTTPTestCase):
    def get_app(self):
        self.ready_state = {"ready": False}
        self.update_queue = asyncio.Queue()
        self.bot = Bot("123456:TESTTOKEN")
        return tornado.web.Application([
            (r"/", RootHandler),
            (r"/healthz/?", HealthHandler, {"ready_state": self.ready_state}),
            (r"/test-webhook/?", TelegramWebhookHandler, {
                "bot": self.bot,
                "update_queue": self.update_queue,
                "secret_token": "test-secret",
            }),
        ])

    def test_health_check_reports_starting_then_ready(self):
        self.assertEqual(self.fetch("/healthz").code, 503)
        self.ready_state["ready"] = True
        self.assertEqual(self.fetch("/healthz").code, 200)

    def test_root_head_probe_returns_success(self):
        self.assertEqual(self.fetch("/", method="HEAD").code, 200)

    def test_webhook_rejects_wrong_secret(self):
        response = self.fetch(
            "/test-webhook",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Telegram-Bot-Api-Secret-Token": "wrong-secret",
            },
            body="{}",
        )
        self.assertEqual(response.code, 403)

    def test_webhook_queues_valid_update_with_correct_secret(self):
        response = self.fetch(
            "/test-webhook",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Telegram-Bot-Api-Secret-Token": "test-secret",
            },
            body=json.dumps({"update_id": 17}),
        )
        self.assertEqual(response.code, 200)
        update = self.update_queue.get_nowait()
        self.assertEqual(update.update_id, 17)


def test_listener_is_open_before_webhook_registration(monkeypatch, tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setattr(
        bot_module,
        "settings",
        replace(
            settings,
            webhook_url="https://example.test",
            webhook_path="test-webhook",
            webhook_secret="test-secret",
            webhook_port=port,
            temp_dir=tmp_path,
        ),
    )

    async def no_post_init(_application):
        return None

    monkeypatch.setattr(bot_module, "post_init", no_post_init)

    class FakeBot:
        async def set_webhook(self, **kwargs):
            self.webhook_kwargs = kwargs
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"HEAD / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
            await writer.drain()
            self.root_status = (await reader.readline()).decode().strip()
            writer.close()
            await writer.wait_closed()
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"GET /healthz HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
            await writer.drain()
            self.health_status = (await reader.readline()).decode().strip()
            writer.close()
            await writer.wait_closed()
            stop_event.set()

    class FakeApplication:
        def __init__(self):
            self.bot = FakeBot()
            self.update_queue = asyncio.Queue()

        async def initialize(self):
            return None

        async def start(self):
            return None

        async def stop(self):
            return None

        async def shutdown(self):
            return None

    async def run_test():
        nonlocal stop_event
        stop_event = asyncio.Event()
        app = FakeApplication()
        await bot_module.run_webhook_server(app, stop_event)
        return app.bot.root_status, app.bot.health_status, app.bot.webhook_kwargs

    stop_event = None
    root_status, health_status, webhook_kwargs = asyncio.run(run_test())
    assert root_status.startswith("HTTP/1.1 200")
    assert health_status.startswith("HTTP/1.1 503")
    assert webhook_kwargs["url"] == "https://example.test/test-webhook"
