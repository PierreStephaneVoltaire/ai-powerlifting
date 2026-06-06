═══ DISCORD / DELIVERY CONTRACT ═══
- Discord messages are chunked and delivered by IF after the run.
- For domain/technical workspace runs, write the final user-facing answer to `response.md`.
- Generated deliverables must stay in this mounted session directory.
- Append progress updates to `.if/status.log`; IF forwards them to Discord status embeds.
- `history.md` is incremental and reflects Discord edits.

═══ CODE DELIVERY RULES ═══
IF delivers to Discord. Discord has a 4000-character message limit and displays
code blocks poorly on mobile. Follow these rules:

1. **Short code (≤10 lines):** Use an inline fenced code block in `response.md`.
   This is the only case where code appears directly in the message text.

2. **Long code (>10 lines):** Write the code to a FILE in this session directory
   using `write_file`. Then list it in a `FILES:` line at the end of `response.md`.
   IF will strip the `FILES:` line, upload the file as a Discord attachment, and
   deliver it alongside the response. Do NOT paste long code inline — it breaks
   chunking and is unreadable on Discord.

3. **When the user asks for a file:** Write or copy the file to this session
   directory, list it in a `FILES:` line. Do NOT read and dump the file contents
   into `response.md`. The user gets the file as a downloadable attachment.

4. **Multiple files:** List all files in a single `FILES:` line:
   ```
   FILES: src/parser.py (CSV parser module), tests/test_parser.py (unit tests), config.yaml (runtime config)
   ```

5. **Describe, don't dump:** In `response.md`, describe what you built or changed
   in one or two sentences. The attachment carries the full content.

