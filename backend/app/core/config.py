import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    database_url: str
    web_admin_user: str
    web_admin_password: str
    ctfd_url: str
    ctfd_admin_name: str
    ctfd_admin_password: str
    chall_manager_url: str
    registry_prefix: str
    registry_url: str
    cleanup_keep_images: str
    scenario_single: str
    scenario_multi: str
    templates_dir: str
    data_dir: str
    upstream_http_proxy: str
    upstream_https_proxy: str
    upstream_no_proxy: str


@lru_cache
def get_settings() -> Settings:
    e = os.environ.get
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        web_admin_user=e("WEB_ADMIN_USER", "admin"),
        web_admin_password=e("WEB_ADMIN_PASSWORD", ""),
        ctfd_url=e("CTFD_URL", "http://ctfd:8000"),
        ctfd_admin_name=e("CTFD_ADMIN_NAME", ""),
        ctfd_admin_password=e("CTFD_ADMIN_PASSWORD", ""),
        chall_manager_url=e("CHALL_MANAGER_URL", "http://chall-manager:8080"),
        registry_prefix=e("REGISTRY_PREFIX", "localhost:5000/challsmith"),
        registry_url=e("REGISTRY_URL", "http://registry:5000"),
        cleanup_keep_images=e("CLEANUP_KEEP_IMAGES", "csftech/php-ext:*,golang:1.27-alpine"),
        scenario_single=e("SCENARIO_SINGLE", "registry:5000/challsmith/scenarios/single:v1"),
        scenario_multi=e("SCENARIO_MULTI", "registry:5000/challsmith/scenarios/multi:v1"),
        templates_dir=e("TEMPLATES_DIR", "/app/templates"),
        data_dir=e("DATA_DIR", "/var/lib/challsmith"),
        upstream_http_proxy=e("UPSTREAM_HTTP_PROXY", ""),
        upstream_https_proxy=e("UPSTREAM_HTTPS_PROXY", ""),
        upstream_no_proxy=e("UPSTREAM_NO_PROXY", ""),
    )
