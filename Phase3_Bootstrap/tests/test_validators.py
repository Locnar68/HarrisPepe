"""Unit tests for installer.validators."""

from __future__ import annotations

import pytest

from installer.validators import (
    ValidationError,
    domain,
    email,
    gcp_project_id,
    gcs_bucket_name,
    non_empty,
    phone,
    region,
    sa_short_name,
    vertex_id,
)


class TestEmail:
    def test_accepts_valid(self):
        assert email("Alice@Example.com") == "alice@example.com"

    @pytest.mark.parametrize("bad", ["", "nope", "missing@dot", "@domain.com",
                                     "spaces in@email.com"])
    def test_rejects(self, bad):
        with pytest.raises(ValidationError):
            email(bad)


class TestPhone:
    @pytest.mark.parametrize("raw,expected", [
        ("+1 (631) 555-0100", "+16315550100"),
        ("6315550100", "6315550100"),
    ])
    def test_normalizes(self, raw, expected):
        assert phone(raw) == expected

    def test_empty_passes_through(self):
        assert phone("") == ""

    @pytest.mark.parametrize("bad", ["12", "123456789012345678"])  # too short / too long
    def test_rejects(self, bad):
        with pytest.raises(ValidationError):
            phone(bad)


class TestDomain:
    def test_valid(self):
        assert domain("Example.COM") == "example.com"

    @pytest.mark.parametrize("bad", ["", "nope", "has spaces.com", "bad/slash.com"])
    def test_rejects(self, bad):
        with pytest.raises(ValidationError):
            domain(bad)


class TestGcpProjectId:
    @pytest.mark.parametrize("good", [
        "madison-ave-rag",
        "commanding-way-380716",
        "a1234b",                    # exactly 6 chars
    ])
    def test_valid(self, good):
        assert gcp_project_id(good) == good

    @pytest.mark.parametrize("bad", [
        "",
        "too",                        # < 6 chars
        "1-leading-digit",
        "trailing-dash-",
        "has_underscore",
        "x" * 35,                     # too long
    ])
    def test_rejects(self, bad):
        with pytest.raises(ValidationError):
            gcp_project_id(bad)

    def test_lowercases(self):
        # Validators normalize to lowercase rather than rejecting
        assert gcp_project_id("UPPER-Case-123") == "upper-case-123"


class TestGcsBucketName:
    @pytest.mark.parametrize("good", [
        "madison-ave-rag-raw",
        "a-bucket_with.dots",
        "abc",                        # min length
    ])
    def test_valid(self, good):
        assert gcs_bucket_name(good) == good

    @pytest.mark.parametrize("bad", [
        "",
        "ab",                         # < 3
        "ends-with-dash-",
        "-starts-with-dash",
        "goog-reserved",              # reserved prefix
        "contains-google-word",
        "double..dots",
    ])
    def test_rejects(self, bad):
        with pytest.raises(ValidationError):
            gcs_bucket_name(bad)

    def test_lowercases(self):
        assert gcs_bucket_name("Has-Caps") == "has-caps"


class TestVertexId:
    def test_valid(self):
        assert vertex_id("madison-ds-v1") == "madison-ds-v1"
        assert vertex_id("my_data_store_v2") == "my_data_store_v2"

    @pytest.mark.parametrize("bad", ["", "ab", "has caps ID", "-leading-dash"])
    def test_rejects(self, bad):
        with pytest.raises(ValidationError):
            vertex_id(bad)


class TestRegion:
    @pytest.mark.parametrize("good", ["us-central1", "europe-west4", "global",
                                      "asia-southeast1"])
    def test_valid(self, good):
        assert region(good) == good

    @pytest.mark.parametrize("bad", ["", "nowhere"])
    def test_rejects(self, bad):
        with pytest.raises(ValidationError):
            region(bad)

    def test_lowercases(self):
        assert region("Us-Central1") == "us-central1"


class TestSaShortName:
    def test_valid(self):
        assert sa_short_name("madison-rag-sa") == "madison-rag-sa"

    @pytest.mark.parametrize("bad", [
        "",
        "short",                      # < 6
        "1-leading-digit",
        "x" * 40,                     # too long
    ])
    def test_rejects(self, bad):
        with pytest.raises(ValidationError):
            sa_short_name(bad)

    def test_lowercases(self):
        assert sa_short_name("UPPER-Case-sa") == "upper-case-sa"


class TestNonEmpty:
    def test_strips(self):
        assert non_empty("  hi  ") == "hi"

    def test_rejects_empty(self):
        with pytest.raises(ValidationError):
            non_empty("   ")
