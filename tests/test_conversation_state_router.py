from app.conversation import ConversationSession, ConversationState
from app.models import IncomingMessage
from app.routing import ConversationStateRouter


def test_state_router_dispatches_registered_state():
    received = []
    router = ConversationStateRouter(
        handlers={
            ConversationState.WAITING_FUEL: (
                lambda message, session: received.append((message, session))
            ),
        }
    )
    message = IncomingMessage(
        sender="15551234567",
        message_type="interactive",
        selection_id="fuel_regular",
    )
    session = ConversationSession(
        sender=message.sender,
        state=ConversationState.WAITING_FUEL,
    )

    handled = router.dispatch(message, session)

    assert handled is True
    assert received == [(message, session)]


def test_state_router_returns_false_for_unregistered_state():
    router = ConversationStateRouter()
    message = IncomingMessage(
        sender="15551234567",
        message_type="text",
        text="hello",
    )
    session = ConversationSession(
        sender=message.sender,
        state=ConversationState.WAITING_LANGUAGE,
    )

    assert router.dispatch(message, session) is False


def test_state_router_uses_default_handler_for_unregistered_state():
    received = []
    router = ConversationStateRouter(
        default_handler=(
            lambda message, session: received.append((message, session))
        )
    )
    message = IncomingMessage(
        sender="15551234567",
        message_type="location",
        latitude=38.2527,
        longitude=-85.7585,
    )
    session = ConversationSession(
        sender=message.sender,
        state=ConversationState.WAITING_SORT,
    )

    handled = router.dispatch(message, session)

    assert handled is False
    assert received == [(message, session)]


def test_state_router_can_register_a_handler():
    received = []
    router = ConversationStateRouter()
    router.register(
        ConversationState.WAITING_LOCATION,
        lambda message, session: received.append((message, session)),
    )
    message = IncomingMessage(
        sender="15551234567",
        message_type="location",
        latitude=38.2527,
        longitude=-85.7585,
    )
    session = ConversationSession(
        sender=message.sender,
        state=ConversationState.WAITING_LOCATION,
    )

    assert router.dispatch(message, session) is True
    assert router.registered_states == (ConversationState.WAITING_LOCATION,)
    assert received == [(message, session)]
