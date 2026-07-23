class AppError(Exception):
    pass


class NotFoundError(AppError):
    pass


class InUseError(AppError):
    pass


class SubscriptionNotFoundError(NotFoundError):
    def __init__(self, subscription_id):
        self.subscription_id = subscription_id
        super().__init__(f"Subscription {subscription_id} not found")


class SubscriptionInUseError(InUseError):
    def __init__(self, subscription_id):
        self.subscription_id = subscription_id
        super().__init__(f"Subscription {subscription_id} has related deliveries")
