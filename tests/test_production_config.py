import pytest

from app.config import validate_production_configuration


VALID_PRODUCTION_SETTINGS = {
    "WHATSAPP_ACCESS_TOKEN": "test-access-token",
    "WHATSAPP_PHONE_NUMBER_ID": "123456789",
    "WHATSAPP_VERIFY_TOKEN": "test-verify-token",
    "META_APP_SECRET": "test-app-secret",
    "INTERNAL_API_TOKEN": "test-internal-token",
    "REDIS_URL": "redis://example",
    "DATABASE_URL": "postgresql://example",
}


def test_production_configuration_accepts_complete_settings():
    validate_production_configuration(
        VALID_PRODUCTION_SETTINGS,
        api_docs_enabled=False,
    )


@pytest.mark.parametrize(
    "missing_name",
    list(VALID_PRODUCTION_SETTINGS),
)
def test_production_configuration_rejects_missing_required_setting(
    missing_name,
):
    settings = VALID_PRODUCTION_SETTINGS.copy()
    settings[missing_name] = None

    with pytest.raises(
        RuntimeError,
        match=missing_name,
    ):
        validate_production_configuration(
            settings,
            api_docs_enabled=False,
        )


def test_production_configuration_requires_docs_disabled():
    with pytest.raises(
        RuntimeError,
        match="API_DOCS_ENABLED must be false",
    ):
        validate_production_configuration(
            VALID_PRODUCTION_SETTINGS,
            api_docs_enabled=True,
        )
