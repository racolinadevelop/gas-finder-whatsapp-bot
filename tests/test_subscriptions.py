from app.handlers import whatsapp as whatsapp_handler
from app.subscriptions import (
    Feature,
    InMemorySubscriptionStore,
    SubscriptionPlan,
    SubscriptionService,
    SubscriptionStatus,
    UserSubscription,
)


def test_store_creates_free_subscription_by_default():
    store = InMemorySubscriptionStore()

    subscription = store.get_or_create("15551234567")

    assert subscription == UserSubscription(whatsapp_id="15551234567")
    assert subscription.plan == SubscriptionPlan.FREE
    assert subscription.status == SubscriptionStatus.INACTIVE
    assert subscription.has_premium_access is False


def test_free_user_can_use_existing_search_features():
    service = SubscriptionService()

    assert service.can_use_feature("15551234567", Feature.GAS_SEARCH) is True
    assert service.can_use_feature("15551234567", Feature.DIRECTIONS) is True
    assert (
        service.can_use_feature("15551234567", Feature.BASIC_COMPARISON)
        is True
    )
    assert service.can_use_feature("15551234567", Feature.FAVORITES) is False
    assert service.can_use_feature("15551234567", "unknown_feature") is False


def test_active_premium_user_can_use_every_feature():
    service = SubscriptionService()

    subscription = service.activate_premium(
        "15551234567",
        billing_customer_id="cus_test",
        billing_subscription_id="sub_test",
    )

    assert subscription.has_premium_access is True
    assert subscription.plan == SubscriptionPlan.PREMIUM
    assert subscription.status == SubscriptionStatus.ACTIVE
    assert all(
        service.can_use_feature("15551234567", feature)
        for feature in Feature
    )


def test_past_due_subscription_loses_premium_features_only():
    service = SubscriptionService()
    service.activate_premium("15551234567")

    subscription = service.update_status(
        "15551234567",
        SubscriptionStatus.PAST_DUE,
    )

    assert subscription.has_premium_access is False
    assert service.can_use_feature("15551234567", Feature.GAS_SEARCH) is True
    assert service.can_use_feature("15551234567", Feature.PRICE_ALERTS) is False


def test_downgrade_to_free_clears_billing_identifiers():
    service = SubscriptionService()
    service.activate_premium(
        "15551234567",
        billing_customer_id="cus_test",
        billing_subscription_id="sub_test",
    )

    subscription = service.downgrade_to_free("15551234567")

    assert subscription.plan == SubscriptionPlan.FREE
    assert subscription.status == SubscriptionStatus.INACTIVE
    assert subscription.billing_customer_id is None
    assert subscription.billing_subscription_id is None


def test_whatsapp_webhook_registers_user_before_dispatch(monkeypatch):
    sender = "15551234567"
    dispatched = []
    whatsapp_handler.subscription_service.store.clear()
    monkeypatch.setattr(
        whatsapp_handler.message_router,
        "dispatch",
        lambda message: dispatched.append(message),
    )
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.subscription",
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

    result = whatsapp_handler.handle_whatsapp_webhook(payload)

    subscription = whatsapp_handler.subscription_service.get_subscription(sender)
    assert result == {"status": "ok"}
    assert subscription.plan == SubscriptionPlan.FREE
    assert len(dispatched) == 1

    whatsapp_handler.subscription_service.store.clear()
