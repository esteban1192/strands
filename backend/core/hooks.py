"""
Custom Strands hooks for the agent execution pipeline.

Contains hooks that integrate with the Strands Agent SDK's lifecycle events
to implement domain-specific behaviours such as tool-call approval gating.
"""
import logging
from typing import Any, Set

from strands.hooks.registry import HookRegistry
from strands.hooks.events import BeforeToolCallEvent

logger = logging.getLogger(__name__)


class ToolApprovalHook:
    """Hook that prevents execution of tools requiring user approval.

    When registered on an Agent, this hook fires before every tool call.
    If the tool's name appears in ``tools_requiring_approval``, the hook
    cancels the call — the tool is **not** executed and the model receives
    an error-status ``toolResult`` with an explanatory message.

    After the agent finishes, ``cancelled_tool_use_ids`` contains the set
    of ``toolUseId`` values that were blocked so the caller can mark them
    as *pending approval* in the database.
    """

    def __init__(self, tools_requiring_approval: Set[str]):
        self._tools = tools_requiring_approval
        self.cancelled_tool_use_ids: Set[str] = set()

    # -- HookProvider protocol ------------------------------------------

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self._before_tool_call)

    # -- Callback -------------------------------------------------------

    def _before_tool_call(self, event: BeforeToolCallEvent) -> None:
        tool_name = event.tool_use.get("name", "")
        if tool_name in self._tools:
            tool_use_id = str(event.tool_use.get("toolUseId", ""))
            self.cancelled_tool_use_ids.add(tool_use_id)
            logger.info(
                "Cancelling tool call '%s' (toolUseId=%s) — requires user approval",
                tool_name,
                tool_use_id,
            )
            event.cancel_tool = (
                "This tool requires user approval before execution. "
                "The tool call is now pending — inform the user that their "
                "approval is needed before the tool can run."
            )
