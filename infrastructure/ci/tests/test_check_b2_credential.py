"""Tests for the B2 authorize-response parser.

The parser once read the v2 response shape against the v3 endpoint and reported
"all buckets, no capabilities" for every key in existence, which sent a correct
key back to the console to be recreated. These lock the v3 shape in, and lock in
the refusal to guess when the shape is unrecognisable.
"""

import pytest
from check_b2_credential import parse_authorization

V3_RESPONSE: dict[str, object] = {
    "accountId": "masked",
    "apiInfo": {
        "storageApi": {
            "bucketName": "valbackups",
            "capabilities": ["listFiles", "readFiles", "writeFiles", "deleteFiles"],
            "s3ApiUrl": "https://s3.us-east-005.backblazeb2.com",
        }
    },
}


def test_v3_shape_is_parsed() -> None:
    """Scope, capabilities, and endpoint come from apiInfo.storageApi."""
    scope, capabilities, s3_url = parse_authorization(V3_RESPONSE)
    assert scope == "valbackups"
    assert capabilities == {"listFiles", "readFiles", "writeFiles", "deleteFiles"}
    assert s3_url == "https://s3.us-east-005.backblazeb2.com"


def test_unscoped_key_reports_none() -> None:
    """A key valid for every bucket has no bucketName, not an empty one."""
    payload: dict[str, object] = {
        "apiInfo": {"storageApi": {"capabilities": ["listBuckets"], "s3ApiUrl": "x"}}
    }
    scope, capabilities, _ = parse_authorization(payload)
    assert scope is None
    assert capabilities == {"listBuckets"}


def test_v2_shape_is_refused_not_defaulted() -> None:
    """The original bug: a top-level `allowed` object must raise, never read as
    "no capabilities"."""
    payload: dict[str, object] = {
        "allowed": {"bucketName": "valbackups", "capabilities": ["readFiles"]}
    }
    with pytest.raises(ValueError, match="cannot read"):
        parse_authorization(payload)


def test_empty_response_is_refused() -> None:
    """No shape at all is an error, not an empty grant."""
    with pytest.raises(ValueError, match="cannot read"):
        parse_authorization({})
