import pytest
from netscan.scanner.cidr import (
    expand_cidr_hosts,
    get_subnet_metadata,
    is_ip_in_cidr,
    validate_and_normalize_cidr,
)


def test_validate_and_normalize_cidr():
    assert validate_and_normalize_cidr("192.168.1.5/24") == "192.168.1.0/24"
    assert validate_and_normalize_cidr("10.0.0.1/30") == "10.0.0.0/30"
    assert validate_and_normalize_cidr("192.168.1.0/25") == "192.168.1.0/25"

    with pytest.raises(ValueError):
        validate_and_normalize_cidr("invalid-cidr")

    with pytest.raises(ValueError):
        validate_and_normalize_cidr("999.999.999.999/24")


def test_validate_and_normalize_cidr_rejects_large_subnets():
    with pytest.raises(ValueError, match="too large"):
        validate_and_normalize_cidr("10.0.0.0/8")

    with pytest.raises(ValueError, match="too large"):
        validate_and_normalize_cidr("192.168.0.0/16")

    with pytest.raises(ValueError, match="too large"):
        validate_and_normalize_cidr("172.16.0.0/12")

    with pytest.raises(ValueError, match="too large"):
        validate_and_normalize_cidr("10.0.0.0/23")


def test_expand_cidr_hosts_24():
    hosts = expand_cidr_hosts("192.168.1.0/24")
    assert len(hosts) == 254
    assert hosts[0] == "192.168.1.1"
    assert hosts[-1] == "192.168.1.254"
    assert "192.168.1.0" not in hosts
    assert "192.168.1.255" not in hosts


def test_expand_cidr_hosts_30():
    hosts = expand_cidr_hosts("10.0.0.0/30")
    assert len(hosts) == 2
    assert hosts == ["10.0.0.1", "10.0.0.2"]


def test_expand_cidr_hosts_32():
    hosts = expand_cidr_hosts("172.16.0.5/32")
    assert len(hosts) == 1
    assert hosts == ["172.16.0.5"]


def test_subnet_metadata():
    meta = get_subnet_metadata("192.168.10.0/24")
    assert meta["cidr"] == "192.168.10.0/24"
    assert meta["network_address"] == "192.168.10.0"
    assert meta["broadcast_address"] == "192.168.10.255"
    assert meta["netmask"] == "255.255.255.0"
    assert meta["usable_hosts"] == 254


def test_is_ip_in_cidr():
    assert is_ip_in_cidr("192.168.1.50", "192.168.1.0/24") is True
    assert is_ip_in_cidr("192.168.2.1", "192.168.1.0/24") is False
    assert is_ip_in_cidr("not-an-ip", "192.168.1.0/24") is False
