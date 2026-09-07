import json
import random
from copy import deepcopy
from string import ascii_letters
from typing import Any

import pytest
from jsonschema import Draft7Validator, FormatChecker

import pystac
from pystac import ExtensionTypeError, Item, ItemAssetDefinition
from pystac.collection import Collection
from pystac.errors import RequiredPropertyMissing
from pystac.extensions.storage import (
    StorageExtension,
    StorageLifecycle,
    StorageLifecycleAction,
    StorageLifecycleAgeTrigger,
    StorageLifecycleDatetimeTrigger,
    StorageLifecycleExpireAction,
    StorageLifecycleManagedBy,
    StorageLifecycleRule,
    StorageLifecycleTransitionAction,
    StorageLifecycleTrigger,
    StorageScheme,
    StorageSchemeType,
)
from tests.utils import TestCases, assert_to_from_dict

NAIP_EXAMPLE_URI = TestCases.get_path("data-files/storage/item-naip.json")
NAIP_COLLECTION_URI = TestCases.get_path("data-files/storage/collection-naip.json")
V1_MIGRATION_ITEM_URI = TestCases.get_path("data-files/storage/item-v1.0.0.json")


@pytest.fixture
def naip_item() -> Item:
    return Item.from_file(NAIP_EXAMPLE_URI)


@pytest.fixture
def naip_collection() -> Collection:
    return Collection.from_file(NAIP_COLLECTION_URI)


@pytest.fixture
def v1_item() -> Item:
    with open(V1_MIGRATION_ITEM_URI) as f:
        item_dict = json.load(f)
    return Item.from_dict(item_dict, migrate=False)


@pytest.fixture
def sample_scheme() -> StorageScheme:
    return StorageScheme.create(
        type=StorageSchemeType.AWS_S3,
        platform="https://{bucket}.s3.{region}.amazonaws.com",
        region="us-west-2",
        requester_pays=True,
    )


@pytest.fixture
def naip_asset(naip_item: Item) -> pystac.Asset:
    # Grab a random asset with the platform property
    return random.choice(
        [
            _asset
            for _asset in naip_item.assets.values()
            if "storage:refs" in _asset.to_dict()
        ]
    )


def test_to_from_dict() -> None:
    with open(NAIP_EXAMPLE_URI) as f:
        item_dict = json.load(f)
    assert_to_from_dict(Item, item_dict)


def test_add_to(sample_item: Item) -> None:
    assert StorageExtension.get_schema_uri() not in sample_item.stac_extensions
    # Check that the URI gets added to stac_extensions
    StorageExtension.add_to(sample_item)
    assert StorageExtension.get_schema_uri() in sample_item.stac_extensions

    # Check that the URI only gets added once, regardless of how many times add_to
    # is called.
    StorageExtension.add_to(sample_item)
    StorageExtension.add_to(sample_item)

    uris = [
        uri
        for uri in sample_item.stac_extensions
        if uri == StorageExtension.get_schema_uri()
    ]
    assert len(uris) == 1


@pytest.mark.vcr()
def test_validate_storage(naip_item: Item) -> None:
    naip_item.validate()


def test_extension_not_implemented(sample_item: Item) -> None:
    # Should raise exception if Item does not include extension URI
    with pytest.raises(pystac.ExtensionNotImplemented):
        _ = StorageExtension.ext(sample_item)

    # Should raise exception if owning Item does not include extension URI
    asset = sample_item.assets["thumbnail"]

    with pytest.raises(pystac.ExtensionNotImplemented):
        _ = StorageExtension.ext(asset)

    # Should succeed if Asset has no owner
    ownerless_asset = pystac.Asset.from_dict(asset.to_dict())
    _ = StorageExtension.ext(ownerless_asset)


def test_collection_ext_add_to(naip_collection: Collection) -> None:
    naip_collection.stac_extensions = []
    assert StorageExtension.get_schema_uri() not in naip_collection.stac_extensions

    _ = StorageExtension.ext(naip_collection, add_if_missing=True)

    assert StorageExtension.get_schema_uri() in naip_collection.stac_extensions


def test_item_ext_add_to(sample_item: Item) -> None:
    assert StorageExtension.get_schema_uri() not in sample_item.stac_extensions

    _ = StorageExtension.ext(sample_item, add_if_missing=True)

    assert StorageExtension.get_schema_uri() in sample_item.stac_extensions


def test_catalog_ext_add_to() -> None:
    catalog = pystac.Catalog("stac", "a catalog")

    assert StorageExtension.get_schema_uri() not in catalog.stac_extensions

    _ = StorageExtension.ext(catalog, add_if_missing=True)

    assert StorageExtension.get_schema_uri() in catalog.stac_extensions


def test_asset_ext_add_to(sample_item: Item) -> None:
    assert StorageExtension.get_schema_uri() not in sample_item.stac_extensions
    asset = sample_item.assets["thumbnail"]

    _ = StorageExtension.ext(asset, add_if_missing=True)

    assert StorageExtension.get_schema_uri() in sample_item.stac_extensions


def test_link_ext_add_to(sample_item: Item) -> None:
    assert StorageExtension.get_schema_uri() not in sample_item.stac_extensions
    asset = sample_item.links[0]

    _ = StorageExtension.ext(asset, add_if_missing=True)

    assert StorageExtension.get_schema_uri() in sample_item.stac_extensions


def test_asset_ext_add_to_ownerless_asset(sample_item: Item) -> None:
    asset_dict = sample_item.assets["thumbnail"].to_dict()
    asset = pystac.Asset.from_dict(asset_dict)

    with pytest.raises(pystac.STACError):
        _ = StorageExtension.ext(asset, add_if_missing=True)


def test_should_raise_exception_when_passing_invalid_extension_object() -> None:
    with pytest.raises(
        ExtensionTypeError,
        match=r"^StorageExtension does not apply to type 'object'$",
    ):
        # calling it wrong purposely so ---------v
        StorageExtension.ext(object())  # type: ignore


def test_summaries_schemes(naip_collection: Collection) -> None:
    col_dict = naip_collection.to_dict()
    storage_summaries = StorageExtension.summaries(naip_collection)
    # Get
    assert (
        list(
            map(
                lambda x: {k: c.to_dict() for k, c in x.items()},
                storage_summaries.schemes or [],
            )
        )
        == col_dict["summaries"]["storage:schemes"]
    )
    # Set
    new_schemes_summary = [
        {"key": StorageScheme.create("aws-s3", "https://a.platform.example.com")}
    ]
    assert storage_summaries.schemes != new_schemes_summary
    storage_summaries.schemes = new_schemes_summary
    assert storage_summaries.schemes == new_schemes_summary

    col_dict = naip_collection.to_dict()
    assert col_dict["summaries"]["storage:schemes"] == [
        {k: c.to_dict() for k, c in x.items()} for x in new_schemes_summary
    ]


def test_summaries_adds_uri(naip_collection: Collection) -> None:
    naip_collection.stac_extensions = []
    with pytest.raises(
        pystac.ExtensionNotImplemented,
        match="Extension 'storage' is not implemented",
    ):
        StorageExtension.summaries(naip_collection, add_if_missing=False)

    _ = StorageExtension.summaries(naip_collection, add_if_missing=True)

    assert StorageExtension.get_schema_uri() in naip_collection.stac_extensions

    StorageExtension.remove_from(naip_collection)
    assert StorageExtension.get_schema_uri() not in naip_collection.stac_extensions


def test_schemes_apply(naip_item: Item) -> None:
    storage_ext = StorageExtension.ext(naip_item)
    new_key = random.choice(ascii_letters)
    new_type = random.choice(ascii_letters)
    new_platform = random.choice(ascii_letters)
    new_region = random.choice(ascii_letters)
    new_requestor_pays = random.choice([v for v in {True, False}])

    storage_ext.apply(
        schemes={
            new_key: StorageScheme.create(
                new_type, new_platform, new_region, new_requestor_pays
            ),
        }
    )

    applied_schemes = storage_ext.schemes
    assert list(applied_schemes) == [new_key]
    assert applied_schemes[new_key].type == new_type
    assert applied_schemes[new_key].platform == new_platform
    assert applied_schemes[new_key].region == new_region
    assert applied_schemes[new_key].requester_pays == new_requestor_pays


@pytest.mark.vcr()
def test_refs_apply(naip_asset: pystac.Asset) -> None:
    test_refs = ["a_ref", "b_ref"]

    storage_ext = StorageExtension.ext(naip_asset)
    storage_ext.apply(refs=test_refs)

    # Get
    assert storage_ext.refs == test_refs

    # Set
    new_refs = [random.choice(ascii_letters)]
    storage_ext.refs = new_refs
    assert storage_ext.refs == new_refs


def test_schemes_apply_raises(naip_item: Item) -> None:
    storage_ext = StorageExtension.ext(naip_item)

    with pytest.raises(
        ValueError,
        match="'refs' cannot be applied with this STAC object type.",
    ):
        storage_ext.apply(
            schemes={
                "a_key": StorageScheme.create("a_type", "a_platform"),
            },
            refs=["a_ref"],
        )
    with pytest.raises(
        RequiredPropertyMissing,
        match="'schemes' property is required for this object type.",
    ):
        storage_ext.apply(refs=None)


def test_refs_apply_raises(naip_asset: Item) -> None:
    storage_ext = StorageExtension.ext(naip_asset)

    with pytest.raises(
        ValueError,
        match="'schemes' cannot be applied with this STAC object type.",
    ):
        storage_ext.apply(
            schemes={
                "a_key": StorageScheme.create("a_type", "a_platform"),
            },
            refs=["a_ref"],
        )

    with pytest.raises(
        RequiredPropertyMissing,
        match="'refs' property is required for this object type.",
    ):
        storage_ext.apply(schemes=None)


def test_add_storage_scheme(naip_item: Item) -> None:
    storage_ext = naip_item.ext.storage
    storage_ext.add_scheme("new_scheme", StorageScheme.create("type", "platform"))
    assert "new_scheme" in storage_ext.schemes

    storage_ext.properties.pop("storage:schemes")
    storage_ext.add_scheme("new_scheme", StorageScheme.create("type", "platform"))
    assert len(storage_ext.schemes) == 1
    assert "new_scheme" in storage_ext.schemes


def test_add_refs(naip_item: Item) -> None:
    scheme_name = random.choice(ascii_letters)
    asset = naip_item.assets["GEOTIFF_AZURE_RGBIR"]
    storage_ext = asset.ext.storage
    assert isinstance(storage_ext, StorageExtension)

    storage_ext.add_ref(scheme_name)
    assert scheme_name in storage_ext.refs

    storage_ext.properties.pop("storage:refs")
    scheme_name_2 = random.choice(ascii_letters)
    storage_ext.add_ref(scheme_name_2)
    assert len(storage_ext.refs) == 1
    assert scheme_name_2 in storage_ext.refs


def test_storage_scheme_create(sample_scheme: StorageScheme) -> None:
    assert sample_scheme.type == StorageSchemeType.AWS_S3
    assert sample_scheme.platform == "https://{bucket}.s3.{region}.amazonaws.com"
    assert sample_scheme.region == "us-west-2"
    assert sample_scheme.requester_pays is True

    sample_scheme.type = StorageSchemeType.AZURE
    sample_scheme.platform = "https://{account}.blob.core.windows.net"
    sample_scheme.region = "eastus"
    sample_scheme.account = "account"
    sample_scheme.requester_pays = False

    assert sample_scheme.type == StorageSchemeType.AZURE
    assert sample_scheme.platform == "https://{account}.blob.core.windows.net"
    assert sample_scheme.region == "eastus"
    assert sample_scheme.account == "account"
    assert sample_scheme.requester_pays is False


def test_storage_scheme_equality(sample_scheme: StorageScheme) -> None:
    other = deepcopy(sample_scheme)
    assert sample_scheme == other

    other.requester_pays = False
    assert sample_scheme != other

    assert sample_scheme != object()


def test_storage_scheme_storage_class() -> None:
    scheme = StorageScheme.create(
        type=StorageSchemeType.AWS_S3,
        platform="https://{bucket}.s3.{region}.amazonaws.com",
        storage_class="STANDARD",
    )

    assert scheme.storage_class == "STANDARD"
    assert scheme.to_dict()["storage_class"] == "STANDARD"

    scheme.storage_class = "DEEP_ARCHIVE"
    assert scheme.storage_class == "DEEP_ARCHIVE"

    scheme.storage_class = None
    assert scheme.storage_class is None
    assert "storage_class" not in scheme.to_dict()


@pytest.mark.parametrize(
    "raw, model",
    [
        (
            {"type": "datetime", "at": "/properties/expires"},
            StorageLifecycleDatetimeTrigger,
        ),
        (
            {"type": "age", "from": "/properties/created", "after": "P30D"},
            StorageLifecycleAgeTrigger,
        ),
        ({"type": "transition", "target": "cold"}, StorageLifecycleTransitionAction),
        ({"type": "expire"}, StorageLifecycleExpireAction),
    ],
)
def test_storage_lifecycle_dispatch(raw: dict[str, Any], model: type) -> None:
    base = (
        StorageLifecycleTrigger
        if "at" in raw or "after" in raw
        else StorageLifecycleAction
    )
    parsed = base.from_dict(raw)
    assert isinstance(parsed, model)
    assert parsed.to_dict() is raw
    assert parsed.type == raw["type"]
    with pytest.raises(AttributeError):
        setattr(parsed, "type", "other")


@pytest.mark.parametrize("base", [StorageLifecycleTrigger, StorageLifecycleAction])
@pytest.mark.parametrize("type_", ["manual", "unknown"])
def test_storage_lifecycle_unknown_type(
    base: type[StorageLifecycleTrigger] | type[StorageLifecycleAction], type_: str
) -> None:
    with pytest.raises(ValueError, match="Unsupported lifecycle"):
        base.from_dict({"type": type_})


@pytest.mark.parametrize(
    "model, raw",
    [
        (StorageLifecycleDatetimeTrigger, {"type": "datetime"}),
        (StorageLifecycleAgeTrigger, {"type": "age", "from": "/properties/created"}),
        (StorageLifecycleAgeTrigger, {"type": "age", "after": "P30D"}),
        (StorageLifecycleTransitionAction, {"type": "transition"}),
    ],
)
def test_storage_lifecycle_missing_fields(model: type, raw: dict[str, Any]) -> None:
    with pytest.raises(RequiredPropertyMissing):
        model(raw)
    with pytest.raises(ValueError):
        model({"type": "wrong"})


def test_storage_lifecycle_trigger_factories() -> None:
    datetime = StorageLifecycleTrigger.create_datetime("/properties/expires")
    assert isinstance(datetime, StorageLifecycleDatetimeTrigger)
    assert datetime.type == "datetime"
    datetime.at = "/assets/result/expires"
    assert datetime.to_dict() == {"type": "datetime", "at": "/assets/result/expires"}

    age = StorageLifecycleTrigger.create_age("/properties/datetime", "P30D")
    assert isinstance(age, StorageLifecycleAgeTrigger)
    assert age.type == "age"
    age.from_ = "/properties/created"
    age.after = "P60D"
    assert age.to_dict() == {
        "type": "age",
        "from": "/properties/created",
        "after": "P60D",
    }


def test_storage_lifecycle_action_factories() -> None:
    transition = StorageLifecycleAction.create_transition("cold")
    assert isinstance(transition, StorageLifecycleTransitionAction)
    assert transition.type == "transition"
    transition.target = "hot"
    assert transition.to_dict() == {"type": "transition", "target": "hot"}
    expire = StorageLifecycleAction.create_expire()
    assert isinstance(expire, StorageLifecycleExpireAction)
    assert expire.type == "expire"
    assert not hasattr(expire, "target")
    assert expire.to_dict() == {"type": "expire"}


def test_storage_scheme_lifecycle_round_trip(sample_scheme: StorageScheme) -> None:
    rule = StorageLifecycleRule.create(
        trigger=StorageLifecycleDatetimeTrigger.create("/properties/expires"),
        action=StorageLifecycleTransitionAction.create("cold"),
    )
    lifecycle = StorageLifecycle.create(
        managed_by=StorageLifecycleManagedBy.PROVIDER,
        rules={"archive": rule},
    )
    sample_scheme.lifecycle = lifecycle
    serialized = sample_scheme.to_dict()
    assert serialized["lifecycle"] == {
        "managed_by": "provider",
        "rules": {
            "archive": {
                "trigger": {"type": "datetime", "at": "/properties/expires"},
                "action": {"type": "transition", "target": "cold"},
            }
        },
    }
    parsed = sample_scheme.lifecycle
    assert parsed is not None
    assert parsed.managed_by == StorageLifecycleManagedBy.PROVIDER
    action = parsed.rules["archive"].action
    assert isinstance(action, StorageLifecycleTransitionAction)
    action.target = "hot"
    parsed.add_rule(
        "expire",
        StorageLifecycleRule.create(
            trigger=StorageLifecycleAgeTrigger.create("/properties/created", "P30D"),
            action=StorageLifecycleExpireAction.create(),
        ),
    )
    assert serialized["lifecycle"]["rules"]["archive"]["action"]["target"] == "hot"
    assert len(serialized["lifecycle"]["rules"]) == 2
    sample_scheme.lifecycle = None
    assert sample_scheme.lifecycle is None
    assert "lifecycle" not in sample_scheme.to_dict()


def test_storage_scheme_create_accepts_raw_lifecycle() -> None:
    raw = {
        "rules": {
            "expire": {
                "trigger": {
                    "type": "age",
                    "from": "/properties/created",
                    "after": "P30D",
                },
                "action": {"type": "expire"},
            }
        }
    }
    scheme = StorageScheme.create("custom-s3", "https://example.com", lifecycle=raw)
    assert scheme.lifecycle == StorageLifecycle(raw)
    assert scheme.lifecycle is not None
    assert isinstance(
        scheme.lifecycle.rules["expire"].action, StorageLifecycleExpireAction
    )


def test_storage_extension_lifecycle_round_trip(naip_item: Item) -> None:
    lifecycle = StorageLifecycle.create(
        rules={
            "archive": StorageLifecycleRule.create(
                trigger=StorageLifecycleAgeTrigger.create(
                    "/properties/datetime", "P30D"
                ),
                action=StorageLifecycleTransitionAction.create("cold"),
            )
        }
    )
    storage_ext = StorageExtension.ext(naip_item)
    storage_ext.add_scheme(
        "managed-s3",
        StorageScheme.create(
            "aws-s3",
            "s3://{bucket}/{key}",
            lifecycle=lifecycle,
        ),
    )
    item = Item.from_dict(naip_item.to_dict(), migrate=False)
    stored = StorageExtension.ext(item).schemes["managed-s3"].lifecycle
    assert stored is not None
    trigger = stored.rules["archive"].trigger
    assert isinstance(trigger, StorageLifecycleAgeTrigger)
    assert trigger.after == "P30D"
    trigger.after = "P60D"
    assert (
        item.properties["storage:schemes"]["managed-s3"]["lifecycle"]["rules"][
            "archive"
        ]["trigger"]["after"]
        == "P60D"
    )


def test_storage_lifecycle_proposal_schema() -> None:
    # Pinned upstream schema at 7927d9b835eb438e0ae9a27c23880d675eba3977.
    with open(TestCases.get_path("data-files/storage/schema-pr30.json")) as f:
        schema = json.load(f)
    validator = Draft7Validator(
        {"$ref": "#/definitions/lifecycle", "definitions": schema["definitions"]},
        format_checker=FormatChecker(),
    )
    lifecycle = StorageLifecycle.create(
        rules={
            "archive": StorageLifecycleRule.create(
                StorageLifecycleAgeTrigger.create("/properties/created", "P30D"),
                StorageLifecycleTransitionAction.create("cold"),
            ),
            "expire": StorageLifecycleRule.create(
                StorageLifecycleDatetimeTrigger.create("/assets/result/expires"),
                StorageLifecycleExpireAction.create(),
            ),
        }
    )
    validator.validate(lifecycle.to_dict())
    parsed = lifecycle.rules["archive"].trigger
    if parsed.type == "age":
        assert parsed.after == "P30D"
    else:
        pytest.fail("Expected an age trigger")


def test_storage_lifecycle_required_properties() -> None:
    with pytest.raises(RequiredPropertyMissing, match="rules"):
        _ = StorageLifecycle({}).rules
    with pytest.raises(RequiredPropertyMissing, match="trigger"):
        _ = StorageLifecycleRule({}).trigger
    with pytest.raises(RequiredPropertyMissing, match="action"):
        _ = StorageLifecycleRule({}).action
    for base in (StorageLifecycleTrigger, StorageLifecycleAction):
        with pytest.raises(RequiredPropertyMissing, match="type"):
            base.from_dict({})


def test_item_asset_accessor() -> None:
    item_asset = ItemAssetDefinition.create(
        title="title", description="desc", media_type="media", roles=["a_role"]
    )
    assert isinstance(item_asset.ext.storage, StorageExtension)


@pytest.mark.filterwarnings("ignore")
def test_migrate(v1_item: Item) -> None:
    item = Item.from_dict(
        v1_item.to_dict(include_self_link=False, transform_hrefs=False), migrate=True
    )

    # Check schemes were created at item level
    assert "storage:schemes" in item.properties
    schemes = item.properties["storage:schemes"]

    # AWS asset should be migrated
    assert "storage:refs" in item.assets["AWS"].to_dict()
    aws_refs = item.assets["AWS"].to_dict()["storage:refs"]
    assert len(aws_refs) == 1
    assert aws_refs[0] in schemes
    assert schemes[aws_refs[0]]["type"] == "aws-s3"
    assert schemes[aws_refs[0]]["region"] == "us-west-2"
    assert schemes[aws_refs[0]]["requester_pays"] is True
    assert schemes[aws_refs[0]]["bucket"] == "bucket"

    # AWS_2 should a different scheme than AWS (same region, no requester_pays)
    assert "storage:refs" in item.assets["AWS_2"].to_dict()
    aws2_refs = item.assets["AWS_2"].to_dict()["storage:refs"]
    assert aws2_refs != aws_refs
    assert schemes[aws2_refs[0]]["bucket"] == "bucket2"

    # AZURE asset should be migrated
    assert "storage:refs" in item.assets["AZURE"].to_dict()
    azure_refs = item.assets["AZURE"].to_dict()["storage:refs"]
    assert len(azure_refs) == 1
    assert azure_refs[0] in schemes
    assert schemes[azure_refs[0]]["type"] == "ms-azure"
    assert schemes[azure_refs[0]]["region"] == "westus2"
    assert schemes[azure_refs[0]]["account"] == "project"

    # GCP asset should NOT be migrated (unsupported platform)
    assert "storage:refs" not in item.assets["GCP"].to_dict()
    assert "storage:platform" in item.assets["GCP"].to_dict()

    # Old properties should be removed from migrated assets
    assert "storage:platform" not in item.assets["AWS"].to_dict()
    assert "storage:region" not in item.assets["AWS"].to_dict()
    assert "storage:platform" not in item.assets["AZURE"].to_dict()

    # storage:tier should be removed from migrated assets
    assert "storage:tier" not in item.assets["AWS"].to_dict()
    assert "storage:tier" not in item.assets["AZURE"].to_dict()
    # but preserved for unmigrated assets
    assert item.assets["GCP"].to_dict().get("storage:tier") == "STANDARD"
