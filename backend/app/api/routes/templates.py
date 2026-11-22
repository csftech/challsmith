from fastapi import APIRouter

from app.services import template_service

router = APIRouter()


@router.get("/templates")
def get_templates() -> list[template_service.TemplateInfo]:
    return template_service.list_templates()
