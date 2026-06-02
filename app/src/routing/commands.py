















from dataclasses import dataclass
from enum import Enum

class CommandAction(Enum):

    RESET_CACHE = "reset_cache"
    PIN_PRESET = "pin_preset"
    NOOP = "noop"
    INVOKE_SPECIALIST = "invoke_specialist"
    INVOKE_TOOL = "invoke_tool"
    REFLECT = "reflect"
    GAPS = "gaps"
    PATTERNS = "patterns"
    OPINIONS = "opinions"
    GROWTH = "growth"
    META = "meta"
    TOOLS = "tools"
    CLEAR_CHAT = "clear_chat"

@dataclass
class CommandResult:









    action: CommandAction
    preset: str | None = None
    target: str | None = None
    response_text: str = ""
    command_args: str = ""

def parse_command(
    content: str,
    available_presets: list[str],
    available_tools: list[str] | None = None,
    specialist_commands: dict[str, str] | None = None,
) -> CommandResult | None:


























    stripped = content.strip()
    if not stripped.startswith("/"):
        return None

    parts = stripped.lstrip("/").split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd == "reflect":
        return CommandResult(
            action=CommandAction.REFLECT,
            response_text="",
            command_args=args,
        )
    
    if cmd == "gaps":
        return CommandResult(
            action=CommandAction.GAPS,
            response_text="",
            command_args=args,
        )
    
    if cmd == "patterns":
        return CommandResult(
            action=CommandAction.PATTERNS,
            response_text="",
            command_args=args,
        )
    
    if cmd == "opinions":
        return CommandResult(
            action=CommandAction.OPINIONS,
            response_text="",
            command_args=args,
        )
    
    if cmd == "growth":
        return CommandResult(
            action=CommandAction.GROWTH,
            response_text="",
            command_args=args,
        )
    
    if cmd == "meta":
        return CommandResult(
            action=CommandAction.META,
            response_text="",
            command_args=args,
        )
    
    if cmd == "tools":
        return CommandResult(
            action=CommandAction.TOOLS,
            response_text="",
            command_args=args,
        )

    if cmd == "end_convo":
        return CommandResult(
            action=CommandAction.RESET_CACHE,
            response_text="Acknowledged. Categorisation state cleared. Next message will be re-evaluated."
        )

    if cmd in available_presets:
        return CommandResult(
            action=CommandAction.PIN_PRESET,
            preset=cmd,
            response_text=f"Acknowledged. Routing pinned to preset: {cmd}. Send /end_convo to release."
        )

    if specialist_commands and cmd in specialist_commands:
        return CommandResult(
            action=CommandAction.INVOKE_SPECIALIST,
            target=specialist_commands[cmd],
            command_args=args,
        )

    if available_tools and cmd in available_tools:
        return CommandResult(
            action=CommandAction.INVOKE_TOOL,
            target=cmd,
            command_args=args,
        )

    return CommandResult(
        action=CommandAction.NOOP,
        response_text=(
            f"Negative. Command \"{cmd}\" not recognized.\n"
            "Available: end_convo, reflect, gaps, patterns, opinions, growth, meta, tools, "
            "a preset name, a registered specialist slash command, or a registered tool slash command."
        )
    )
