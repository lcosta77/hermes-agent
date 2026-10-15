"""GDJ Hub fork — wire contracts for ``methods_gdj.py`` (the GDJ Agent's
settings screen: provider catalog + login flows, toolset switches)."""

from __future__ import annotations

from .base import Params, Result
from .common import OkResult, OpenModel, ProfileParams
from .registry import method


class GdjProviderRow(Result):
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


class GdjProvidersCatalogResult(Result):
    providers: list[GdjProviderRow]


method("gdj.providers.catalog", params=ProfileParams, result=GdjProvidersCatalogResult,
       doc="GDJ fork: every provider with its auth flow and current login state.")


class GdjOAuthStartParams(ProfileParams):
    provider: str


method("gdj.providers.oauth_start", params=GdjOAuthStartParams, result=OpenModel,
       doc="GDJ fork: begin a device-code login (session_id, user_code, verification_url, expires_in).")


class GdjOAuthPollParams(ProfileParams):
    provider: str
    session_id: str


method("gdj.providers.oauth_poll", params=GdjOAuthPollParams, result=OpenModel,
       doc="GDJ fork: status of a device-code login (pending | approved | denied | expired | error).")


class GdjOAuthCancelParams(Params):
    session_id: str


method("gdj.providers.oauth_cancel", params=GdjOAuthCancelParams, result=OkResult,
       doc="GDJ fork: abandon a pending device-code login.")


class GdjOAuthDisconnectParams(ProfileParams):
    provider: str


method("gdj.providers.oauth_disconnect", params=GdjOAuthDisconnectParams, result=OkResult,
       doc="GDJ fork: sign out of an OAuth provider (clears its stored tokens).")


class GdjToolsetSetParams(ProfileParams):
    name: str
    enabled: bool


class GdjToolsetSetResult(Result):
    disabled: list[str]


method("gdj.toolsets.set", params=GdjToolsetSetParams, result=GdjToolsetSetResult,
       doc="GDJ fork: enable/disable a toolset for new sessions (agent.disabled_toolsets).")


class GdjSessionsArchivedParams(ProfileParams):
    limit: int = 100


method("gdj.sessions.archived", params=GdjSessionsArchivedParams, result=OpenModel,
       doc="GDJ fork: archived sessions (session.list rows), newest first.")


class GdjSessionsDeleteParams(ProfileParams):
    session_id: str


method("gdj.sessions.delete", params=GdjSessionsDeleteParams, result=OpenModel,
       doc="GDJ fork: close the idle live copies of a stored session, then session.delete it.")
