"""Product metadata: the single source of truth for names, paths, and labels.

Every installer, Compose template, release workflow, and doc derives naming from one
`ProductMetadata` record. The persistent ``stable_instance_id`` and ``compose_project``
never change on a rename, so renaming the display name or CLI command cannot orphan
volumes or break upgrades; a rename instead records a legacy CLI alias.
"""

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

_PRODUCT_FILE = Path(__file__).resolve().parents[3] / "config" / "product.toml"


@dataclass(frozen=True)
class ProductMetadata:
    schema_version: int
    display_name: str
    cli_command: str
    package_name: str
    registry_namespace: str
    compose_project: str
    label_prefix: str
    stable_instance_id: str
    config_dir: str
    data_dir: str
    backup_dir: str
    secret_dir: str
    docs_base_url: str
    legacy_cli_command: str | None = None

    def image_ref(self, service: str, digest: str) -> str:
        """Return a fully digest-pinned image reference for ``service``."""
        if not digest.startswith("sha256:"):
            raise ValueError("images must be pinned by sha256 digest")
        return f"{self.registry_namespace}/{service}@{digest}"

    def labels(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        labels = {
            f"{self.label_prefix}.product": self.package_name,
            f"{self.label_prefix}.instance": self.stable_instance_id,
            f"{self.label_prefix}.managed": "true",
        }
        if extra:
            labels.update(extra)
        return labels

    def directories(self) -> dict[str, str]:
        return {
            "config": self.config_dir,
            "data": self.data_dir,
            "backup": self.backup_dir,
            "secret": self.secret_dir,
        }

    def rename(self, new_cli_command: str) -> "ProductMetadata":
        """Return metadata renamed to ``new_cli_command`` with a legacy alias.

        Stable internal identifiers are preserved so existing volumes and upgrades keep
        working; the previous CLI command is retained as a deprecation alias.
        """
        return replace(
            self, cli_command=new_cli_command, legacy_cli_command=self.cli_command
        )


def load_product_metadata(path: Path | None = None) -> ProductMetadata:
    source = Path(path) if path is not None else _PRODUCT_FILE
    data = tomllib.loads(source.read_text(encoding="utf-8"))
    return ProductMetadata(
        schema_version=int(data["schema_version"]),
        display_name=str(data["display_name"]),
        cli_command=str(data["cli_command"]),
        package_name=str(data["package_name"]),
        registry_namespace=str(data["registry_namespace"]),
        compose_project=str(data["compose_project"]),
        label_prefix=str(data["label_prefix"]),
        stable_instance_id=str(data["stable_instance_id"]),
        config_dir=str(data["config_dir"]),
        data_dir=str(data["data_dir"]),
        backup_dir=str(data["backup_dir"]),
        secret_dir=str(data["secret_dir"]),
        docs_base_url=str(data["docs_base_url"]),
    )
