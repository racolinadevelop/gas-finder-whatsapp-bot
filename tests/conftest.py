import pytest


@pytest.fixture(autouse=True)
def clear_webhook_message_deduplicator():
    from app.handlers import whatsapp as whatsapp_handler

    whatsapp_handler.message_deduplicator.clear()
    whatsapp_handler.search_rate_limiter.clear()
    yield
    whatsapp_handler.message_deduplicator.clear()
    whatsapp_handler.search_rate_limiter.clear()
