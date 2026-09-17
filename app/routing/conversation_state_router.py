from collections.abc import Callable, Mapping

from app.conversation import ConversationSession, ConversationState
from app.models import IncomingMessage

ConversationStateHandler = Callable[
    [IncomingMessage, ConversationSession],
    None,
]


class ConversationStateRouter:
    """Dispatch a normalized message according to conversation state."""

    def __init__(
        self,
        handlers: Mapping[
            ConversationState,
            ConversationStateHandler,
        ]
        | None = None,
        default_handler: ConversationStateHandler | None = None,
    ) -> None:
        self._handlers = dict(handlers or {})
        self._default_handler = default_handler

    @property
    def registered_states(self) -> tuple[ConversationState, ...]:
        return tuple(self._handlers)

    def register(
        self,
        state: ConversationState,
        handler: ConversationStateHandler,
    ) -> None:
        self._handlers[state] = handler

    def dispatch(
        self,
        message: IncomingMessage,
        session: ConversationSession,
    ) -> bool:
        handler = self._handlers.get(session.state)

        if handler is not None:
            handler(message, session)
            return True

        if self._default_handler is not None:
            self._default_handler(message, session)

        return False
