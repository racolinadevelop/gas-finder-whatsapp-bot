from typing import Protocol

from app.subscriptions.models import (
    Feature,
    SubscriptionPlan,
    SubscriptionStatus,
    UserSubscription,
)
from app.subscriptions.store import (
    InMemorySubscriptionStore,
    SubscriptionStore,
)


class TestEntitlementStore(Protocol):
    def has_premium_access(self, whatsapp_id: str) -> bool: ...


FREE_FEATURES = frozenset(
    {
        Feature.GAS_SEARCH,
        Feature.DIRECTIONS,
        Feature.BASIC_COMPARISON,
    }
)

PREMIUM_FEATURES = frozenset(Feature)


class SubscriptionService:
    """Central policy for plans, subscription state, and feature access."""

    def __init__(
        self,
        store: SubscriptionStore | None = None,
        test_entitlements: TestEntitlementStore | None = None,
    ) -> None:
        self.store = store or InMemorySubscriptionStore()
        # Test entitlements only exist when Stripe test mode is explicitly enabled.
        self.test_entitlements = test_entitlements

    def ensure_user(self, whatsapp_id: str) -> UserSubscription:
        return self.store.get_or_create(whatsapp_id)

    def get_subscription(self, whatsapp_id: str) -> UserSubscription:
        return self.ensure_user(whatsapp_id)

    def can_use_feature(
        self,
        whatsapp_id: str,
        feature: Feature | str,
    ) -> bool:
        try:
            requested_feature = Feature(feature)
        except ValueError:
            return False

        subscription = self.ensure_user(whatsapp_id)
        allowed_features = (
            PREMIUM_FEATURES
            if (
                subscription.has_premium_access
                or (
                    self.test_entitlements is not None
                    and self.test_entitlements.has_premium_access(whatsapp_id)
                )
            )
            else FREE_FEATURES
        )
        return requested_feature in allowed_features

    def activate_premium(
        self,
        whatsapp_id: str,
        billing_customer_id: str | None = None,
        billing_subscription_id: str | None = None,
    ) -> UserSubscription:
        return self.store.update(
            whatsapp_id,
            plan=SubscriptionPlan.PREMIUM,
            status=SubscriptionStatus.ACTIVE,
            billing_customer_id=billing_customer_id,
            billing_subscription_id=billing_subscription_id,
        )

    def update_status(
        self,
        whatsapp_id: str,
        status: SubscriptionStatus,
    ) -> UserSubscription:
        return self.store.update(whatsapp_id, status=status)

    def downgrade_to_free(self, whatsapp_id: str) -> UserSubscription:
        return self.store.update(
            whatsapp_id,
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.INACTIVE,
            billing_customer_id=None,
            billing_subscription_id=None,
        )
