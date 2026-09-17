from dataclasses import dataclass
from enum import StrEnum


class SubscriptionPlan(StrEnum):
    FREE = "free"
    PREMIUM = "premium"


class SubscriptionStatus(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class Feature(StrEnum):
    GAS_SEARCH = "gas_search"
    DIRECTIONS = "directions"
    BASIC_COMPARISON = "basic_comparison"
    FAVORITES = "favorites"
    PRICE_ALERTS = "price_alerts"
    PRICE_HISTORY = "price_history"
    ADVANCED_COMPARISON = "advanced_comparison"
    PERSONALIZED_RECOMMENDATIONS = "personalized_recommendations"


@dataclass(frozen=True, slots=True)
class UserSubscription:
    """Subscription identity linked to one WhatsApp user."""

    whatsapp_id: str
    plan: SubscriptionPlan = SubscriptionPlan.FREE
    status: SubscriptionStatus = SubscriptionStatus.INACTIVE
    billing_customer_id: str | None = None
    billing_subscription_id: str | None = None

    @property
    def has_premium_access(self) -> bool:
        return (
            self.plan == SubscriptionPlan.PREMIUM
            and self.status == SubscriptionStatus.ACTIVE
        )
