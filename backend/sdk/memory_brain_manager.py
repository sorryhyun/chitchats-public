"""
Memory Brain SDK Manager - Handles Claude SDK client for memory selection.

This module manages the Claude SDK client lifecycle and interactions for the
memory brain agent using Pydantic structured output for type-safe responses.
"""

import logging
from typing import List, Optional

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from config.config_loader import get_debug_config, get_memory_context_config
from config.constants import AGENT_TOOL_NAMES, BUILTIN_TOOLS, MEMORY_BRAIN_MAX_THINKING_TOKENS
from domain.memory import MemoryBrainOutput, MemoryEntry, MemoryPolicy
from utils.debug_utils import format_message_for_debug
from utils.korean_particles import format_with_particles

from sdk.brain_tools import create_character_config_mcp_server

logger = logging.getLogger("MemoryBrainSDKManager")


class MemoryBrainSDKManager:
    """
    Manages Claude SDK client for memory brain analysis.

    Handles client lifecycle, prompt building, tool creation, and SDK interactions
    for the memory brain agent.
    """

    def __init__(self, max_memories: int = 3):
        """
        Initialize memory brain SDK manager.

        Args:
            max_memories: Maximum number of memories to surface per turn (default: 3)
        """
        self.max_memories = max_memories
        self._client_cache: Optional[ClaudeSDKClient] = None

    def _get_policy_prompt(self, policy: MemoryPolicy) -> str:
        """Get the policy-specific prompt section from configuration."""
        from config.config_loader import get_memory_policy_prompt

        return get_memory_policy_prompt(policy.value)

    def _build_system_prompt(self, policy: MemoryPolicy, agent_name: str = "") -> str:
        """
        Build the system prompt for the memory-brain agent.

        Character configuration is provided via MCP tools, not in the system prompt.

        Args:
            policy: Memory selection policy
            agent_name: Name of the agent

        Returns:
            System prompt with template variables substituted
        """
        policy_section = self._get_policy_prompt(policy)

        # Load prompt from guidelines configuration
        from config.config_loader import get_memory_brain_prompt

        return get_memory_brain_prompt(
            agent_name=agent_name, max_memories=self.max_memories, policy_section=policy_section
        )

    def _build_analysis_prompt(
        self,
        conversation_context: str,
        available_memories: List[MemoryEntry],
        agent_name: str = "",
        agent_count: Optional[int] = None,
        user_name: Optional[str] = None,
        has_situation_builder: bool = False,
    ) -> str:
        """
        Build the analysis prompt with current context.

        Character identity is provided via MCP tool descriptions, not in this prompt.

        Args:
            conversation_context: Full conversation context that the agent sees
            available_memories: List of available long-term memory entries
            agent_name: Name of the agent
            agent_count: Number of agents in the room (for detecting 1-on-1 conversations)
            user_name: Name of the user/character participant (for 1-on-1 conversations)
            has_situation_builder: Whether conversation includes situation_builder messages

        Returns:
            Analysis prompt for memory-brain
        """
        # Load configuration
        config = get_memory_context_config()
        memory_context = config.get("memory_context", {})

        # Get settings from config
        no_memories_msg = memory_context.get("no_memories_message", "No long-term memories available.")

        # Format available memories with IDs, tags, and previews
        memories_list = []
        for mem in available_memories:
            memory_info = f"ID: {mem.id}"
            if mem.tags:
                memory_info += f" | Tags: {', '.join(mem.tags)}"
            if mem.content_preview:
                memory_info += f"\nPreview: {mem.content_preview}"
            memories_list.append(memory_info)

        memories_section = "\n\n".join(memories_list) if memories_list else no_memories_msg

        # Determine if this is a 1-on-1 conversation with user/character (not situation_builder)
        is_one_on_one = agent_count == 1 and user_name and not has_situation_builder

        # Select appropriate template based on conversation type
        if is_one_on_one and agent_name and user_name:
            # Use 1-on-1 template
            analysis_template = memory_context.get("analysis_prompt_with_user", "")
            return format_with_particles(
                analysis_template,
                conversation_context=conversation_context,
                memories_section=memories_section,
                agent_name=agent_name,
                user_name=user_name,
            )
        elif agent_name:
            # Use multi-agent or situation_builder template
            analysis_template = memory_context.get("analysis_prompt_with_agent", "")
            return format_with_particles(
                analysis_template,
                conversation_context=conversation_context,
                memories_section=memories_section,
                agent_name=agent_name,
            )
        else:
            # Use default template (no agent name)
            analysis_template = memory_context.get("analysis_prompt", "")
            return format_with_particles(
                analysis_template,
                conversation_context=conversation_context,
                memories_section=memories_section,
                agent_name=agent_name if agent_name else "",
            )

    async def analyze_memories(
        self,
        conversation_context: str,
        available_memories: List[MemoryEntry],
        policy: MemoryPolicy = MemoryPolicy.BALANCED,
        agent_name: str = "",
        in_a_nutshell: str = "",
        characteristics: str = "",
        agent_count: Optional[int] = None,
        user_name: Optional[str] = None,
        has_situation_builder: bool = False,
    ) -> MemoryBrainOutput:
        """
        Analyze context using Claude SDK with Pydantic structured output.

        Uses the claude-agent-sdk's structured output feature to get validated,
        type-safe responses directly as MemoryBrainOutput objects.

        Args:
            conversation_context: Full conversation context that the agent sees
            available_memories: List of available long-term memory entries
            policy: Memory selection policy to use
            agent_name: Name of the agent
            in_a_nutshell: Agent's brief identity summary
            characteristics: Agent's personality traits
            agent_count: Number of agents in the room (for detecting 1-on-1 conversations)
            user_name: Name of the user/character participant (for 1-on-1 conversations)
            has_situation_builder: Whether conversation includes situation_builder messages

        Returns:
            MemoryBrainOutput with selected memories and injection flag
        """
        logger.info(f"Memory Brain SDK analyzing for {agent_name} with policy: {policy}")
        logger.debug(f"Available memories: {len(available_memories)}")

        # Build prompts
        system_prompt = self._build_system_prompt(policy, agent_name)
        analysis_prompt = self._build_analysis_prompt(
            conversation_context,
            available_memories,
            agent_name=agent_name,
            agent_count=agent_count,
            user_name=user_name,
            has_situation_builder=has_situation_builder,
        )

        # Add structured output instructions to the analysis prompt
        structured_prompt = f"""{analysis_prompt}

After analyzing the context and selecting memories using the select_memory tool, provide a final summary as a JSON object with:
- should_inject_now: boolean (true if you selected any memories, false otherwise)
- activated_memories: array of the memories you selected (should match your tool calls)
- reasoning: string (brief overall reasoning for your memory selection decisions)"""

        # Convert MemoryEntry objects to dictionaries for memory tools
        memories_dict = [
            {"id": mem.id, "tags": mem.tags, "content_preview": mem.content_preview} for mem in available_memories
        ]

        # Create character MCP server with configuration tools
        character_mcp_server = create_character_config_mcp_server(
            agent_name=agent_name, in_a_nutshell=in_a_nutshell, characteristics=characteristics
        )

        # Create memory_brain MCP server with selection tools
        from sdk.brain_tools import create_memory_brain_mcp_server

        memory_brain_mcp_server, _ = create_memory_brain_mcp_server(
            available_memories=memories_dict, max_memories=self.max_memories
        )

        # Create or reuse client
        if self._client_cache is None:
            options = ClaudeAgentOptions(
                model="claude-opus-4-5-20250114",
                system_prompt=system_prompt,
                disallowed_tools=BUILTIN_TOOLS.copy(),
                allowed_tools=[
                    AGENT_TOOL_NAMES["memory_select"],
                    AGENT_TOOL_NAMES["memory_config"],
                ],
                setting_sources=[],
                cwd="/tmp/claude-empty",
                permission_mode="default",
                max_thinking_tokens=MEMORY_BRAIN_MAX_THINKING_TOKENS,
                mcp_servers={
                    "character": character_mcp_server,
                    "memory_brain": memory_brain_mcp_server,
                },
            )
            self._client_cache = ClaudeSDKClient(options=options)
            await self._client_cache.connect()
        else:
            # Update system prompt for new policy
            self._client_cache.options.system_prompt = system_prompt
            # Update MCP servers for new tools
            self._client_cache.options.mcp_servers = {
                "character": character_mcp_server,
                "memory_brain": memory_brain_mcp_server,
            }

        # Query with structured output format
        logger.debug("Sending query to memory brain with structured output...")
        await self._client_cache.query(
            structured_prompt,
            options={"output_format": {"type": "json_schema", "schema": MemoryBrainOutput.model_json_schema()}},
        )

        # Get debug config to check if detailed logging is enabled
        debug_config = get_debug_config()
        debug_enabled = debug_config.get("debug", {}).get("enabled", False)

        # Collect structured output from response
        output = None
        async for message in self._client_cache.receive_response():
            if debug_enabled:
                logger.debug(f"🧠 Memory brain message:\n{format_message_for_debug(message)}")
            else:
                logger.debug(f"Memory brain message received (type: {message.__class__.__name__})")

            # Check for structured output
            if hasattr(message, "structured_output") and message.structured_output:
                logger.debug(f"📊 Received structured output: {message.structured_output}")
                # Validate and parse with Pydantic
                output = MemoryBrainOutput.model_validate(message.structured_output)

        # Fallback if no structured output received
        if output is None:
            logger.warning("No structured output received from memory brain, returning empty result")
            output = MemoryBrainOutput(should_inject_now=False, activated_memories=[], reasoning="")

        # Enforce max_memories limit (should be validated by schema, but double-check)
        if len(output.activated_memories) > self.max_memories:
            logger.warning(
                f"Memory brain selected {len(output.activated_memories)} memories, limiting to {self.max_memories}"
            )
            # Sort by activation strength and take top N
            output.activated_memories = sorted(
                output.activated_memories, key=lambda x: x.activation_strength, reverse=True
            )[: self.max_memories]

        logger.info(
            f"Memory brain result: inject={output.should_inject_now}, memories={len(output.activated_memories)}"
        )
        for activation in output.activated_memories:
            logger.info(
                f"  - {activation.memory_id} (strength={activation.activation_strength:.2f}): {activation.reason}"
            )

        return output

    async def cleanup(self):
        """Clean up SDK client and disconnect."""
        if self._client_cache is not None:
            try:
                await self._client_cache.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting memory brain SDK client: {e}")
            finally:
                self._client_cache = None
