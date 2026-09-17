from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    """Normalized representation of one incoming WhatsApp message."""

    sender: str
    message_type: str
    message_id: str | None = None
    timestamp: str | None = None

    text: str | None = None

    latitude: float | None = None
    longitude: float | None = None
    location_name: str | None = None
    location_address: str | None = None

    interactive_type: str | None = None
    selection_id: str | None = None
    selection_title: str | None = None

    media_id: str | None = None
    mime_type: str | None = None
    sha256: str | None = None
    caption: str | None = None
    filename: str | None = None

    raw_message: dict = field(default_factory=dict, repr=False, compare=False)
