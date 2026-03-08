"""
Webhook resource — endpoints for managing webhooks and handling
inbound notifications from external sources (e.g. AWS SNS).

The invoke endpoint is *public* (no app-level auth) — authentication
is handled per source_type (e.g. SNS message signature verification).
"""
import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from api.database import get_db, get_db_session
from api.db_models import ChatModel
from api.models.webhook_models import (
    WebhookResponse,
    WebhookCreateRequest,
    WebhookUpdateRequest,
    WebhookInvocationResponse,
    WebhookInvokeResponse,
)
from api.services.webhook_service import WebhookService
from api.services.chat_service import ChatService
from core.agent_executor import AgentExecutor
from core.event_bus import event_bus
from core.sns_validator import (
    verify_sns_message,
    confirm_subscription,
    parse_sns_notification,
    format_alarm_prompt,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


# ------------------------------------------------------------------
# CRUD endpoints
# ------------------------------------------------------------------

@router.get("", response_model=List[WebhookResponse])
async def list_webhooks(request: Request, db: AsyncSession = Depends(get_db)):
    return await WebhookService.get_all(db, base_url=_base_url(request))


@router.post("", response_model=WebhookResponse, status_code=201)
async def create_webhook(
    request: Request,
    data: WebhookCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await WebhookService.create(db, data, base_url=_base_url(request))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Webhook name already exists")
        raise HTTPException(status_code=500, detail=f"Failed to create webhook: {e}")


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    webhook = await WebhookService.get_by_id(db, webhook_id, base_url=_base_url(request))
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook


@router.put("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: uuid.UUID,
    data: WebhookUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        webhook = await WebhookService.update(db, webhook_id, data, base_url=_base_url(request))
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")
        return webhook
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Webhook name already exists")
        raise HTTPException(status_code=500, detail=f"Failed to update webhook: {e}")


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    success = await WebhookService.delete(db, webhook_id)
    if not success:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"message": f"Webhook {webhook_id} deleted successfully"}


@router.get("/{webhook_id}/invocations", response_model=List[WebhookInvocationResponse])
async def list_invocations(
    webhook_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    webhook = await WebhookService.get_by_id(db, webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return await WebhookService.get_invocations(db, webhook_id, limit=limit, offset=offset)


# ------------------------------------------------------------------
# Invoke endpoint (public — SNS-authenticated)
# ------------------------------------------------------------------

@router.post("/{webhook_id}/invoke", response_model=WebhookInvokeResponse, status_code=202)
async def invoke_webhook(
    webhook_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle an inbound notification (e.g. from AWS SNS).

    1. Validate the webhook exists and is active.
    2. Record the invocation.
    3. For AWS_SNS: verify signature, handle SubscriptionConfirmation,
       or process the Notification by creating a chat and invoking the agent.
    """
    webhook = await WebhookService.get_model_by_id(db, webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if not webhook.is_active:
        raise HTTPException(status_code=403, detail="Webhook is inactive")

    body = await request.body()
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    source_ip = request.client.host if request.client else None
    invocation = await WebhookService.create_invocation(
        db, webhook_id, raw_payload=payload, source_ip=source_ip,
    )

    if webhook.source_type == "AWS_SNS":
        return await _handle_sns(db, webhook, invocation, payload, request)

    raise HTTPException(status_code=400, detail=f"Unsupported source type: {webhook.source_type}")


async def _handle_sns(
    db: AsyncSession,
    webhook,
    invocation,
    payload: dict,
    request: Request,
):
    """Process an AWS SNS message."""
    sns_type = (
        request.headers.get("x-amz-sns-message-type")
        or payload.get("Type", "")
    )

    is_valid = await verify_sns_message(payload)
    if not is_valid:
        await WebhookService.update_invocation_status(
            db, invocation.id, "failed", error_message="SNS signature verification failed",
        )
        raise HTTPException(status_code=403, detail="Invalid SNS signature")

    if sns_type == "SubscriptionConfirmation":
        confirmed = await confirm_subscription(payload)
        status = "completed" if confirmed else "failed"
        error = None if confirmed else "Failed to confirm subscription"
        await WebhookService.update_invocation_status(
            db, invocation.id, status, error_message=error,
        )
        return WebhookInvokeResponse(
            invocation_id=invocation.id,
            status=status,
        )

    if sns_type == "UnsubscribeConfirmation":
        await WebhookService.update_invocation_status(db, invocation.id, "completed")
        return WebhookInvokeResponse(invocation_id=invocation.id, status="completed")

    if sns_type != "Notification":
        await WebhookService.update_invocation_status(
            db, invocation.id, "failed",
            error_message=f"Unknown SNS message type: {sns_type}",
        )
        raise HTTPException(status_code=400, detail=f"Unknown SNS message type: {sns_type}")

    # --- Process the actual notification ---
    parsed = parse_sns_notification(payload)
    prompt = format_alarm_prompt(parsed)
    subject = parsed.get("subject") or "Webhook notification"

    chat = await ChatService.create_chat(db, webhook.agent_id, title=subject[:100])

    # Set webhook_id on the chat
    from sqlalchemy import update as sa_update
    stmt = sa_update(ChatModel).where(ChatModel.id == chat.id).values(webhook_id=webhook.id)
    await db.execute(stmt)
    await db.commit()

    await ChatService.create_delegation(db, chat.id, webhook.agent_id)
    user_msg = [{"role": "user", "content": [{"text": prompt}]}]
    await ChatService.add_messages(db, chat.id, user_msg, agent_id=webhook.agent_id)

    await WebhookService.update_invocation_status(
        db, invocation.id, "processing", chat_id=chat.id,
    )

    asyncio.create_task(
        _background_webhook_invoke(chat.id, webhook.agent_id, invocation.id)
    )

    return WebhookInvokeResponse(
        invocation_id=invocation.id,
        chat_id=chat.id,
        status="processing",
    )


async def _background_webhook_invoke(
    chat_id: uuid.UUID,
    agent_id: uuid.UUID,
    invocation_id: uuid.UUID,
):
    """Background task: invoke the agent for a webhook-triggered chat.

    Very similar to the chat resource's _background_invoke, but also
    updates the invocation status on completion/failure.
    """
    from api.services import TaskService
    from core.task_runner import task_runner
    from api.resources.chat import _split_task_calls, _auto_process_create_tasks, _serialize_messages

    await event_bus.publish(chat_id, {"type": "thinking"})

    async with get_db_session() as db:
        try:
            history = await ChatService.get_messages_as_dicts(db, chat_id, agent_id=agent_id)

            result = await AgentExecutor.invoke(
                db, agent_id, None, history=history, chat_id=chat_id,
            )

            if result.messages:
                await ChatService.add_messages(
                    db, chat_id, result.messages,
                    tools_requiring_approval=result.tools_requiring_approval,
                    agent_id=agent_id,
                )

            await TaskService.resolve_message_ids(db, chat_id)
            await db.commit()

            pending = await ChatService.get_pending_tool_calls(db, chat_id, agent_id=agent_id)
            task_calls, remaining_pending = _split_task_calls(pending)

            if task_calls:
                await _auto_process_create_tasks(db, chat_id, agent_id, task_calls, task_runner)

            await ChatService.touch_updated_at(db, chat_id)
            all_messages = await ChatService.get_messages(db, chat_id)
            tasks = await TaskService.get_tasks_for_chat(db, chat_id)

            event_payload = {
                "type": "complete",
                "response": result.response,
                "messages": _serialize_messages(all_messages),
            }
            if tasks:
                event_payload["tasks"] = [
                    TaskService.to_response(t).model_dump(mode="json")
                    for t in tasks
                ]

            await event_bus.publish(chat_id, event_payload)

            await WebhookService.update_invocation_status(db, invocation_id, "completed")

        except Exception as exc:
            logger.exception("Webhook background invoke failed for chat %s", chat_id)
            await event_bus.publish(chat_id, {
                "type": "error",
                "message": str(exc),
            })
            try:
                await WebhookService.update_invocation_status(
                    db, invocation_id, "failed", error_message=str(exc),
                )
            except Exception:
                logger.exception("Failed to update invocation status")
