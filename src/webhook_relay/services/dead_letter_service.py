import uuid

from arq import ArqRedis

from webhook_relay.exceptions import DeadLetterNotFoundError
from webhook_relay.models.delivery import DeadLetter, Delivery
from webhook_relay.repositories.dead_letter_repo import DeadLetterRepo
from webhook_relay.repositories.delivery_repo import DeliveryRepo


class DeadLetterService:
    def __init__(
        self,
        arq_redis: ArqRedis,
        delivery_repo: DeliveryRepo,
        dead_letter_repo: DeadLetterRepo,
    ):
        self.arq_redis = arq_redis
        self.delivery_repo = delivery_repo
        self.dead_letter_repo = dead_letter_repo

    async def get_all(self, limit: int, offset: int) -> list[DeadLetter]:
        return await self.dead_letter_repo.get_all(limit=limit, offset=offset)

    async def retry(self, dead_letter_id: uuid.UUID) -> Delivery:
        dead_letter = await self.dead_letter_repo.get_by_id(dead_letter_id)
        if dead_letter is None:
            raise DeadLetterNotFoundError(dead_letter_id)

        delivery = await self.delivery_repo.reset_for_retry(dead_letter.delivery_id)
        await self.dead_letter_repo.delete(dead_letter_id)

        await self.arq_redis.enqueue_job(
            "deliver_webhook",
            str(delivery.id),
            _job_id=f"{delivery.id}:manual:{uuid.uuid4().hex[:8]}",
        )

        await self.delivery_repo.commit()
        return delivery
