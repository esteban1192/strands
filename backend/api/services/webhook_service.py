"""
Webhook service for CRUD operations and invocation logic.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db_models import WebhookModel, WebhookInvocationModel, AgentModel
from ..models.webhook_models import (
    WebhookResponse,
    WebhookCreateRequest,
    WebhookUpdateRequest,
    WebhookInvocationResponse,
)


class WebhookService:
    """Service for Webhook CRUD operations."""

    @staticmethod
    def _to_response(webhook: WebhookModel, base_url: Optional[str] = None) -> WebhookResponse:
        agent_name = webhook.agent.name if webhook.agent else None
        invoke_url = f"{base_url}/webhooks/{webhook.id}/invoke" if base_url else None
        return WebhookResponse(
            id=webhook.id,
            name=webhook.name,
            description=webhook.description,
            agent_id=webhook.agent_id,
            agent_name=agent_name,
            source_type=webhook.source_type,
            is_active=webhook.is_active,
            prompt=webhook.prompt,
            invoke_url=invoke_url,
            created_at=webhook.created_at,
            updated_at=webhook.updated_at,
        )

    @staticmethod
    async def get_all(db: AsyncSession, base_url: Optional[str] = None) -> List[WebhookResponse]:
        stmt = (
            select(WebhookModel)
            .options(selectinload(WebhookModel.agent))
            .order_by(WebhookModel.created_at.desc())
        )
        result = await db.execute(stmt)
        webhooks = result.scalars().all()
        return [WebhookService._to_response(w, base_url) for w in webhooks]

    @staticmethod
    async def get_by_id(
        db: AsyncSession, webhook_id: uuid.UUID, base_url: Optional[str] = None,
    ) -> Optional[WebhookResponse]:
        stmt = (
            select(WebhookModel)
            .options(selectinload(WebhookModel.agent))
            .where(WebhookModel.id == webhook_id)
        )
        result = await db.execute(stmt)
        webhook = result.scalar_one_or_none()
        if not webhook:
            return None
        return WebhookService._to_response(webhook, base_url)

    @staticmethod
    async def get_model_by_id(db: AsyncSession, webhook_id: uuid.UUID) -> Optional[WebhookModel]:
        stmt = (
            select(WebhookModel)
            .options(selectinload(WebhookModel.agent))
            .where(WebhookModel.id == webhook_id)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession, data: WebhookCreateRequest, base_url: Optional[str] = None,
    ) -> WebhookResponse:
        agent_stmt = select(AgentModel).where(AgentModel.id == data.agent_id)
        agent_result = await db.execute(agent_stmt)
        if not agent_result.scalar_one_or_none():
            raise ValueError(f"Agent {data.agent_id} not found")

        webhook = WebhookModel(
            name=data.name,
            description=data.description,
            agent_id=data.agent_id,
            source_type=data.source_type.value,
            is_active=data.is_active,
            prompt=data.prompt,
        )
        db.add(webhook)
        await db.commit()
        await db.refresh(webhook)

        return await WebhookService.get_by_id(db, webhook.id, base_url)

    @staticmethod
    async def update(
        db: AsyncSession,
        webhook_id: uuid.UUID,
        data: WebhookUpdateRequest,
        base_url: Optional[str] = None,
    ) -> Optional[WebhookResponse]:
        update_data = {}
        if data.name is not None:
            update_data["name"] = data.name
        if data.description is not None:
            update_data["description"] = data.description
        if data.agent_id is not None:
            agent_stmt = select(AgentModel).where(AgentModel.id == data.agent_id)
            agent_result = await db.execute(agent_stmt)
            if not agent_result.scalar_one_or_none():
                raise ValueError(f"Agent {data.agent_id} not found")
            update_data["agent_id"] = data.agent_id
        if data.source_type is not None:
            update_data["source_type"] = data.source_type.value
        if data.is_active is not None:
            update_data["is_active"] = data.is_active
        if data.prompt is not None:
            update_data["prompt"] = data.prompt or None

        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            stmt = update(WebhookModel).where(WebhookModel.id == webhook_id).values(**update_data)
            result = await db.execute(stmt)
            if result.rowcount == 0:
                return None
            await db.commit()

        return await WebhookService.get_by_id(db, webhook_id, base_url)

    @staticmethod
    async def delete(db: AsyncSession, webhook_id: uuid.UUID) -> bool:
        stmt = delete(WebhookModel).where(WebhookModel.id == webhook_id)
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Invocation operations
    # ------------------------------------------------------------------

    @staticmethod
    async def create_invocation(
        db: AsyncSession,
        webhook_id: uuid.UUID,
        raw_payload: Optional[dict] = None,
        source_ip: Optional[str] = None,
    ) -> WebhookInvocationModel:
        invocation = WebhookInvocationModel(
            webhook_id=webhook_id,
            raw_payload=raw_payload,
            source_ip=source_ip,
            status="received",
        )
        db.add(invocation)
        await db.commit()
        await db.refresh(invocation)
        return invocation

    @staticmethod
    async def update_invocation_status(
        db: AsyncSession,
        invocation_id: uuid.UUID,
        status: str,
        chat_id: Optional[uuid.UUID] = None,
        error_message: Optional[str] = None,
    ) -> None:
        update_data: dict = {"status": status}
        if chat_id is not None:
            update_data["chat_id"] = chat_id
        if error_message is not None:
            update_data["error_message"] = error_message

        stmt = (
            update(WebhookInvocationModel)
            .where(WebhookInvocationModel.id == invocation_id)
            .values(**update_data)
        )
        await db.execute(stmt)
        await db.commit()

    @staticmethod
    async def get_invocations(
        db: AsyncSession,
        webhook_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[WebhookInvocationResponse]:
        stmt = (
            select(WebhookInvocationModel)
            .where(WebhookInvocationModel.webhook_id == webhook_id)
            .order_by(WebhookInvocationModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [WebhookService._to_invocation_response(r) for r in rows]

    @staticmethod
    def _to_invocation_response(inv: WebhookInvocationModel) -> WebhookInvocationResponse:
        return WebhookInvocationResponse(
            id=inv.id,
            webhook_id=inv.webhook_id,
            chat_id=inv.chat_id,
            source_ip=inv.source_ip,
            raw_payload=inv.raw_payload,
            status=inv.status,
            error_message=inv.error_message,
            created_at=inv.created_at,
        )
