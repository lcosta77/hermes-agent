"""gold.vault fork — wire contracts for ``methods_gold.py`` (the gold.agent's
settings screen: provider catalog + login flows, toolset switches)."""

from __future__ import annotations

from .base import Params, Result
from .common import OkResult, OpenModel, ProfileParams
from .registry import method


class GoldProviderRow(Result):
    """One provider of the ``hermes model`` universe, with how to sign in and whether it is."""

    slug: str
    name: str
    description: str = ""
    auth_type: str = "api_key"
    tab: str = "keys"
    key_env: list[str] = []
    base_url_env: str = ""
    signup_url: str = ""
    # "" (api key / none) | device_code | external
    flow: str = ""
    logged_in: bool = False
    status_label: str = ""


class GoldProvidersCatalogResult(Result):
    providers: list[GoldProviderRow]


method("gold.providers.catalog", params=ProfileParams, result=GoldProvidersCatalogResult,
       doc="gold.vault fork: every provider with its auth flow and current login state.")


class GoldOAuthStartParams(ProfileParams):
    provider: str


method("gold.providers.oauth_start", params=GoldOAuthStartParams, result=OpenModel,
       doc="gold.vault fork: begin a device-code login (session_id, user_code, verification_url, expires_in).")


class GoldOAuthPollParams(ProfileParams):
    provider: str
    session_id: str


method("gold.providers.oauth_poll", params=GoldOAuthPollParams, result=OpenModel,
       doc="gold.vault fork: status of a device-code login (pending | approved | denied | expired | error).")


class GoldOAuthCancelParams(Params):
    session_id: str


method("gold.providers.oauth_cancel", params=GoldOAuthCancelParams, result=OkResult,
       doc="gold.vault fork: abandon a pending device-code login.")


class GoldOAuthDisconnectParams(ProfileParams):
    provider: str


method("gold.providers.oauth_disconnect", params=GoldOAuthDisconnectParams, result=OkResult,
       doc="gold.vault fork: sign out of an OAuth provider (clears its stored tokens).")


class GoldToolsetSetParams(ProfileParams):
    name: str
    enabled: bool


class GoldToolsetSetResult(Result):
    disabled: list[str]


method("gold.toolsets.set", params=GoldToolsetSetParams, result=GoldToolsetSetResult,
       doc="gold.vault fork: enable/disable a toolset for new sessions (agent.disabled_toolsets).")


class GoldSessionsArchivedParams(ProfileParams):
    limit: int = 100


method("gold.sessions.archived", params=GoldSessionsArchivedParams, result=OpenModel,
       doc="gold.vault fork: archived sessions (session.list rows), newest first.")


class GoldSessionsDeleteParams(ProfileParams):
    session_id: str


method("gold.sessions.delete", params=GoldSessionsDeleteParams, result=OpenModel,
       doc="gold.vault fork: close the idle live copies of a stored session, then session.delete it.")
