from app.parsers import parse_incoming_message


def test_parser_extracts_whatsapp_profile_name():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [
                                {
                                    "profile": {"name": " Ramon "},
                                    "wa_id": "15551234567",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "15551234567",
                                    "id": "wamid.profile-name",
                                    "timestamp": "1770000000",
                                    "type": "text",
                                    "text": {"body": "hola"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    message = parse_incoming_message(payload)

    assert message is not None
    assert message.profile_name == "Ramon"
    assert message.text == "hola"


def test_parser_keeps_working_without_profile_name():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "15551234567",
                                    "type": "text",
                                    "text": {"body": "hello"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    message = parse_incoming_message(payload)

    assert message is not None
    assert message.profile_name is None
