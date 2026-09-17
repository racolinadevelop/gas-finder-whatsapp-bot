from app.models import IncomingMessage
from app.routing import MessageRouter


def test_message_router_dispatches_registered_type():
    received_messages = []
    router = MessageRouter(
        handlers={
            "text": received_messages.append,
        }
    )
    message = IncomingMessage(
        sender="15551234567",
        message_type="text",
        text="hello",
    )

    handled = router.dispatch(message)

    assert handled is True
    assert received_messages == [message]


def test_message_router_uses_default_handler_for_unknown_type():
    unsupported_messages = []
    router = MessageRouter(default_handler=unsupported_messages.append)
    message = IncomingMessage(
        sender="15551234567",
        message_type="image",
        media_id="media.image",
    )

    handled = router.dispatch(message)

    assert handled is False
    assert unsupported_messages == [message]


def test_message_router_can_register_a_handler():
    received_messages = []
    router = MessageRouter()
    router.register("audio", received_messages.append)
    message = IncomingMessage(
        sender="15551234567",
        message_type="audio",
        media_id="media.audio",
    )

    handled = router.dispatch(message)

    assert handled is True
    assert router.registered_types == ("audio",)
    assert received_messages == [message]
