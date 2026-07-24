"""The product metadata file is the single source of truth for names and paths."""

from aegis.deploy.product import load_product_metadata


def test_metadata_loads_from_committed_file() -> None:
    product = load_product_metadata()
    assert product.display_name == "Aegis"
    assert product.cli_command == "ae"
    assert product.package_name


def test_image_ref_is_deterministic_and_digest_pinned() -> None:
    product = load_product_metadata()
    ref = product.image_ref("aegis-control", "sha256:" + "a" * 64)
    assert ref == product.image_ref("aegis-control", "sha256:" + "a" * 64)
    assert "@sha256:" in ref
    assert product.registry_namespace in ref


def test_labels_include_product_and_managed_marker() -> None:
    product = load_product_metadata()
    labels = product.labels()
    assert labels[f"{product.label_prefix}.product"] == product.package_name
    assert labels[f"{product.label_prefix}.managed"] == "true"


def test_directories_are_derived() -> None:
    product = load_product_metadata()
    dirs = product.directories()
    assert set(dirs) == {"config", "data", "backup", "secret"}
    assert all(value for value in dirs.values())


def test_rename_preserves_stable_id_and_creates_alias() -> None:
    product = load_product_metadata()
    renamed = product.rename("aegisctl")
    assert renamed.cli_command == "aegisctl"
    assert renamed.legacy_cli_command == product.cli_command
    # renaming must not orphan volumes: the persistent internal id is stable
    assert renamed.stable_instance_id == product.stable_instance_id
    assert renamed.compose_project == product.compose_project


def test_no_alias_before_a_rename() -> None:
    assert load_product_metadata().legacy_cli_command is None
