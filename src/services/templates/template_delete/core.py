import os


def _get_template_store():
    from services.runtime.template_store import TemplateStore
    return TemplateStore(
        table_name=os.environ.get("IF_TEMPLATES_TABLE_NAME", "if-health-templates"),
        pk=os.environ.get("IF_TEMPLATES_LIBRARY_PK", "template_library"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )


async def template_delete(sk, actor_pk):
    if not actor_pk:
        raise ValueError("Verified acting Person required")
    return await _get_template_store().delete_template(sk, actor_pk=str(actor_pk))
