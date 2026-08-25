import sys
from unittest.mock import patch

from netscan.models import Role


class TestMapGroupsToRole:
    def test_admin_group(self):
        from netscan.auth.ldap import map_groups_to_role

        assert map_groups_to_role(["netscan-admins"]) == Role.ADMIN

    def test_operator_group(self):
        from netscan.auth.ldap import map_groups_to_role

        assert map_groups_to_role(["netscan-operators"]) == Role.OPERATOR

    def test_unknown_group_defaults_read_only(self):
        from netscan.auth.ldap import map_groups_to_role

        assert map_groups_to_role(["some-other-group"]) == Role.READ_ONLY

    def test_empty_groups(self):
        from netscan.auth.ldap import map_groups_to_role

        assert map_groups_to_role([]) == Role.READ_ONLY

    def test_first_match_wins(self):
        from netscan.auth.ldap import map_groups_to_role

        assert map_groups_to_role(["netscan-operators", "netscan-admins"]) == Role.OPERATOR

    def test_case_insensitive(self):
        from netscan.auth.ldap import map_groups_to_role

        assert map_groups_to_role(["NETSCAN-ADMINS"]) == Role.ADMIN


class TestLdapAuthenticate:
    def test_returns_none_when_disabled(self):
        from netscan.auth.ldap import ldap_authenticate

        with patch("netscan.auth.ldap.settings") as mock_settings:
            mock_settings.LDAP_ENABLED = False
            assert ldap_authenticate("user", "pass") is None

    def test_returns_none_when_ldap_not_installed(self):
        from netscan.auth.ldap import ldap_authenticate as _auth  # noqa: F401

        with patch("netscan.auth.ldap.settings") as mock_settings:
            mock_settings.LDAP_ENABLED = True
            # Remove ldap from sys.modules to simulate it not being installed
            saved = sys.modules.pop("ldap", None)
            try:
                sys.modules["ldap"] = None  # Will cause ImportError on `import ldap`
                # Also remove the cached module to force re-import
                if "netscan.auth.ldap" in sys.modules:
                    del sys.modules["netscan.auth.ldap"]
                from netscan.auth.ldap import ldap_authenticate as auth_fn

                assert auth_fn("user", "pass") is None
            finally:
                if saved is not None:
                    sys.modules["ldap"] = saved
                elif "ldap" in sys.modules:
                    del sys.modules["ldap"]
