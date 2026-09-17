from app.models import IncomingMessage

MEDIA_MESSAGE_TYPES = {
    "audio",
    "document",
    "image",
    "sticker",
    "video",
}


def parse_incoming_message(payload: dict) -> IncomingMessage | None:
    """Convert a Meta webhook payload into one normalized message."""

    try:
        value = payload["entry"][0]["changes"][0]["value"]
        messages = value.get("messages", [])

        if not messages:
            return None

        raw_message = messages[0]
        sender = raw_message.get("from")
        message_type = raw_message.get("type")

        if not sender or not message_type:
            return None

        profile_name = None
        contacts = value.get("contacts", [])
        if contacts and isinstance(contacts[0], dict):
            profile = contacts[0].get("profile", {})
            if isinstance(profile, dict):
                raw_profile_name = profile.get("name")
                if isinstance(raw_profile_name, str):
                    profile_name = raw_profile_name.strip() or None

        fields = {
            "sender": sender,
            "message_type": message_type,
            "message_id": raw_message.get("id"),
            "timestamp": raw_message.get("timestamp"),
            "profile_name": profile_name,
            "raw_message": raw_message,
        }

        if message_type == "text":
            fields["text"] = raw_message.get("text", {}).get("body")

        elif message_type == "location":
            location = raw_message.get("location", {})
            fields.update(
                {
                    "latitude": location.get("latitude"),
                    "longitude": location.get("longitude"),
                    "location_name": location.get("name"),
                    "location_address": location.get("address"),
                }
            )

        elif message_type == "interactive":
            interactive = raw_message.get("interactive", {})
            interactive_type = interactive.get("type")
            selection = interactive.get(interactive_type, {})
            fields.update(
                {
                    "interactive_type": interactive_type,
                    "selection_id": selection.get("id"),
                    "selection_title": selection.get("title"),
                }
            )

        elif message_type in MEDIA_MESSAGE_TYPES:
            media = raw_message.get(message_type, {})
            fields.update(
                {
                    "media_id": media.get("id"),
                    "mime_type": media.get("mime_type"),
                    "sha256": media.get("sha256"),
                    "caption": media.get("caption"),
                    "filename": media.get("filename"),
                }
            )

        return IncomingMessage(**fields)

    except (KeyError, IndexError, TypeError):
        return None
