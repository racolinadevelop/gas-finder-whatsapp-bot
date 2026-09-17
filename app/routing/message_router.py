from collections.abc import Callable, Mapping

from app.models import IncomingMessage

MessageHandler = Callable[[IncomingMessage], None]


class MessageRouter:
    """Dispatch normalized messages according to their message type."""

    def __init__(
        self,
        handlers: Mapping[str, MessageHandler] | None = None,
        default_handler: MessageHandler | None = None,
    ) -> None:
        self._handlers = dict(handlers or {})
        self._default_handler = default_handler

    @property
    def registered_types(self) -> tuple[str, ...]:
        return tuple(self._handlers)

    def register(self, message_type: str, handler: MessageHandler) -> None:
        self._handlers[message_type] = handler

    def dispatch(self, message: IncomingMessage) -> bool:
        handler = self._handlers.get(message.message_type)

        if handler is not None:
            handler(message)
            return True

        if self._default_handler is not None:
            self._default_handler(message)

        return False
