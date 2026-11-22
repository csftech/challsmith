from fastapi import APIRouter

from challsmith_api.services import templates

router = APIRouter()


@router.get("/templates")
def get_templates() -> list[templates.TemplateInfo]:
    return templates.list_templates()
