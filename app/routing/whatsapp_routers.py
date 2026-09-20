"""Wire WhatsApp message-type and conversation-state routers.

The handlers are supplied by the entry point so this module does not import
the WhatsApp handler or construct shared runtime state.
"""

from collections.abc import Callable

from app.conversation import ConversationSession, ConversationState
from app.handlers.conversation_states import ConversationStateHandlers
from app.models import IncomingMessage
from app.routing.conversation_state_router import ConversationStateRouter
from app.routing.message_router import MessageRouter

MessageHandler = Callable[[IncomingMessage], None]
StateHandler = Callable[[IncomingMessage, ConversationSession], None]


def build_whatsapp_routers(
    *,
    state_handlers: ConversationStateHandlers,
    search_from_location: StateHandler,
    handle_text: MessageHandler,
    handle_interactive: MessageHandler,
    handle_location: MessageHandler,
    handle_unsupported: MessageHandler,
) -> tuple[
    ConversationStateRouter,
    ConversationStateRouter,
    ConversationStateRouter,
    MessageRouter,
]:
    """Return the four routers with the same registrations as the guided flow."""
    text_router = ConversationStateRouter(
        handlers={
            ConversationState.WAITING_DISTANCE: state_handlers.distance_text,
            ConversationState.WAITING_CUSTOM_DISTANCE: state_handlers.distance_text,
        },
    )
    interactive_router = ConversationStateRouter(
        handlers={
            ConversationState.MAIN_MENU: state_handlers.menu_interaction,
            ConversationState.WAITING_FUEL: state_handlers.fuel_interaction,
            ConversationState.WAITING_SORT: state_handlers.sort_interaction,
            ConversationState.WAITING_DISTANCE: state_handlers.distance_interaction,
        },
    )
    location_router = ConversationStateRouter(
        handlers={ConversationState.WAITING_LOCATION: search_from_location},
    )
    message_router = MessageRouter(
        handlers={
            "text": handle_text,
            "interactive": handle_interactive,
            "location": handle_location,
        },
        default_handler=handle_unsupported,
    )
    return text_router, interactive_router, location_router, message_router
