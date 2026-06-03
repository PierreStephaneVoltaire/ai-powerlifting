import os

APP_SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'src')


class TestGlobalDirectiveInclusion:
    def test_get_for_subagent_has_global_directive_check(self):
        """Verify that get_for_subagent has the global_directive check."""
        store_path = os.path.join(APP_SRC, 'storage', 'directive_store.py')
        source = open(store_path).read()

        assert 'd.global_directive' in source, "Must check d.global_directive in get_for_subagent"

        lines = source.split('\n')
        global_line = None
        main_agent_line = None
        for i, line in enumerate(lines):
            if 'd.global_directive' in line and 'if' in line:
                global_line = i
            if 'MAIN_AGENT_ONLY_TYPES' in line:
                main_agent_line = i
        if global_line is not None and main_agent_line is not None:
            assert global_line < main_agent_line, "global_directive check must come before MAIN_AGENT_ONLY_TYPES exclusion"


class TestPromptTemplatesUsed:
    def test_all_prompt_templates_exist(self):
        from pathlib import Path
        prompts_dir = Path(__file__).parent.parent / 'app' / 'src' / 'agent' / 'prompts'
        expected = [
            'planner_prompt.j2',
            'batch_classifier_prompt.j2',
            'domain_prompt.j2',
            'social_system_prompt.j2',
            'technical_prompt.j2',
            'technical_review_prompt.j2',
            'technical_retry_prompt.j2',
            'synthesis_prompt.j2',
            'tool_protocol.j2',
            'runtime_compatibility.md',
            'discord_delivery_contract.md',
            'runtime_memory_tools.j2',
        ]
        for name in expected:
            assert (prompts_dir / name).exists(), f'Template {name} must exist'

    def test_runner_uses_templates(self):
        content = open(os.path.join(APP_SRC, 'flow', 'runner.py')).read()
        templates = [
            'planner_prompt',
            'domain_prompt',
            'social_system_prompt',
            'technical_prompt',
            'technical_review_prompt',
            'technical_retry_prompt',
            'synthesis_prompt',
            'tool_protocol',
        ]
        for t in templates:
            assert f'"{t}"' in content, f'runner.py should use template {t}'

    def test_batch_classifier_uses_template(self):
        content = open(os.path.join(APP_SRC, 'flow', 'batch_classifier.py')).read()
        assert '"batch_classifier_prompt"' in content

    def test_technical_prompt_includes_directives(self):
        content = open(os.path.join(APP_SRC, 'flow', 'runner.py')).read()
        assert '"technical_prompt"' in content
        idx = content.index('"technical_prompt"')
        nearby = content[idx:idx+200]
        assert 'core_directives' in nearby

    def test_synthesis_prompt_includes_directives(self):
        content = open(os.path.join(APP_SRC, 'flow', 'runner.py')).read()
        assert '"synthesis_prompt"' in content
        idx = content.index('"synthesis_prompt"')
        nearby = content[idx:idx+200]
        assert 'core_directives' in nearby

    def test_context_uses_templates(self):
        content = open(os.path.join(APP_SRC, 'flow', 'context.py')).read()
        assert '"runtime_compatibility"' in content
        assert '"discord_delivery_contract"' in content
        assert '"runtime_memory_tools"' in content

    def test_no_inline_planner_prompt_in_runner(self):
        content = open(os.path.join(APP_SRC, 'flow', 'runner.py')).read()
        assert 'f"""You are IF' not in content, 'Inline planner f-string should be removed'

    def test_no_inline_batch_classifier_prompt(self):
        content = open(os.path.join(APP_SRC, 'flow', 'batch_classifier.py')).read()
        assert 'f"""You are IF' not in content, 'Inline batch classifier f-string should be removed'
