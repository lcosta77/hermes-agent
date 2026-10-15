"""GDJ Hub fork — RPCs the GDJ Agent's settings screen needs that upstream only
serves through the dashboard's REST routes (``hermes_cli/web_routers/oauth.py``):
the provider catalog with each provider's sign-in flow and state, device-code
OAuth (start / poll / cancel / disconnect) and toolset switches — plus the
sidebar's archived list and a delete that closes the live copy first. Contracts live
in ``contracts/gdj.py``; both are registered in ``server.py``.

Two flows stay off on purpose: Anthropic subscription OAuth (Anthropic's OAuth
policy — the dashboard leaves it out for the same reason; API keys only) and
Qwen OAuth (reads and rewrites ``~/.qwen``, outside GDJ's HERMES_HOME)."""

from __future__ import annotations

from .method_ctx import HandlerRegistry, bind_module

_registry = HandlerRegistry()
method = _registry.method

_GDJ_NO_LOGIN = frozenset({"anthropic", "qwen-oauth"})


def _gdj_oauth_rows() -> dict:
    """provider id -> (flow, status card) from the dashboard's own catalog."""
    from hermes_cli.web_routers import oauth as oauth_router

    rows = {}
    for entry in oauth_router._build_oauth_catalog():
        pid = entry["id"]
        if pid in _GDJ_NO_LOGIN:
            rows[pid] = ("external", {"logged_in": False})
            continue
        status = oauth_router._resolve_provider_status(pid, entry.get("status_fn"))
        rows[pid] = (entry.get("flow") or "", status if isinstance(status, dict) else {})
    return rows


@method("gdj.providers.catalog")
def _(rid, params: dict) -> dict:
    from hermes_cli.provider_catalog import provider_catalog

    try:
        oauth = _gdj_oauth_rows()
    except Exception:
        oauth = {}
    out = []
    for d in provider_catalog():
        flow, status = oauth.get(d.slug, ("", {}))
        out.append({
            "slug": d.slug, "name": d.label, "description": d.description or "",
            "auth_type": d.auth_type, "tab": d.tab, "key_env": list(d.api_key_env_vars),
            "base_url_env": d.base_url_env_var or "", "signup_url": d.signup_url or "",
            "flow": flow, "logged_in": bool(status.get("logged_in")),
            "status_label": str(status.get("source_label") or status.get("error") or ""),
        })
    return _ok(rid, {"providers": out})


@method("gdj.providers.oauth_start")
def _(rid, params: dict) -> dict:
    import asyncio

    provider = str(params.get("provider") or "")
    if provider in _GDJ_NO_LOGIN:
        return _err(rid, 4080, f"{provider}: login por assinatura não é oferecido no GDJ Hub")
    from hermes_cli.web_routers import oauth as oauth_router

    oauth_router._gc_oauth_sessions()
    entry = next((p for p in oauth_router._OAUTH_PROVIDER_CATALOG if p["id"] == provider), None)
    if entry is None or entry.get("flow") != "device_code":
        return _err(rid, 4081, f"{provider} não tem login por código de dispositivo")
    try:
        body = asyncio.run(oauth_router._start_device_code_flow(provider, profile=params.get("profile")))
    except Exception as e:  # HTTPException carries .detail
        return _err(rid, 5080, str(getattr(e, "detail", "") or e))
    return _ok(rid, dict(body))


@method("gdj.providers.oauth_poll")
def _(rid, params: dict) -> dict:
    from hermes_cli.web_routers import oauth as oauth_router

    sid = str(params.get("session_id") or "")
    with oauth_router._oauth_sessions_lock:
        sess = oauth_router._oauth_sessions.get(sid)
        sess = dict(sess) if sess else None
    if not sess:
        return _ok(rid, {"session_id": sid, "status": "expired", "error_message": "sessão expirou"})
    if sess.get("provider") != params.get("provider"):
        return _err(rid, 4082, "provider não confere com a sessão")
    keep = ("session_id", "status", "error_message", "expires_at", "reason", "account_email", "model")
    return _ok(rid, {k: sess.get(k) for k in keep})


@method("gdj.providers.oauth_cancel")
def _(rid, params: dict) -> dict:
    from hermes_cli.web_routers import oauth as oauth_router

    sid = str(params.get("session_id") or "")
    with oauth_router._oauth_sessions_lock:
        sess = oauth_router._oauth_sessions.get(sid)
        if sess is not None:
            sess["cancelled"] = True  # a worker holding the dict stops instead of saving
            oauth_router._oauth_sessions.pop(sid, None)
    return _ok(rid, {"ok": sess is not None})


@method("gdj.providers.oauth_disconnect")
def _(rid, params: dict) -> dict:
    provider = str(params.get("provider") or "")
    try:
        from hermes_cli.auth import clear_provider_auth

        cleared = clear_provider_auth(provider)
        if provider == "nous":
            from hermes_cli.auth import invalidate_nous_auth_status_cache

            invalidate_nous_auth_status_cache()
    except Exception as e:
        return _err(rid, 5081, str(e))
    return _ok(rid, {"ok": bool(cleared)})


@method("gdj.toolsets.set")
def _(rid, params: dict) -> dict:
    # server.py's raw round-trip writer (never the CLI's set_config_value: it
    # prints to stdout — the RPC channel — and may sys.exit).
    name = str(params.get("name") or "").strip()
    if not name:
        return _err(rid, 4083, "toolset name required")
    cfg = _load_cfg_raw() or {}
    disabled = list(((cfg.get("agent") or {}).get("disabled_toolsets")) or [])
    if params.get("enabled"):
        disabled = [t for t in disabled if t != name]
    elif name not in disabled:
        disabled.append(name)
    try:
        _write_config_key("agent.disabled_toolsets", disabled)
    except Exception as e:
        return _err(rid, 5082, str(e))
    return _ok(rid, {"disabled": disabled})


@method("gdj.sessions.archived")
def _(rid, params: dict) -> dict:
    """Archived conversations, newest first — ``session.list`` leaves them out (the
    dashboard's ``?archived=only``)."""
    limit = int(params.get("limit") or 100)
    with _profile_db(params) as db:
        if db is None:
            return _db_unavailable_error(rid, code=5006)
        try:
            rows = _listing_rows(db, limit, archived_only=True)
            return _ok(rid, {"sessions": [_session_row_summary(s) for s in rows]})
        except Exception as e:
            return _err(rid, 5006, str(e))


@method("gdj.sessions.delete")
def _(rid, params: dict) -> dict:
    """``session.delete`` refuses a conversation still loaded in this gateway, and the
    sidebar keeps every conversation it opened loaded. Close the idle live copies of
    the stored key first (a running turn is refused, never cut), then delete."""
    target = str(params.get("session_id") or "")
    if not target:
        return _err(rid, 4006, "session_id required")
    snapshot, err = _snapshot_sessions(rid)
    if err:
        return err
    live = [sid for sid, s in snapshot if s.get("session_key") == target]
    if any(s.get("running") for sid, s in snapshot if sid in live):
        return _err(rid, 4023, "a conversa ainda está rodando — pare antes de apagar")
    for sid in live:
        with _session_resume_lock:
            popped = _pop_session_by_id(sid)
        _teardown_popped_session(popped, end_reason="tui_close")
    return _methods["session.delete"](rid, {**params, "session_id": target})


def _gdj_refuse_borrowed_logins() -> None:
    """GDJ fork: the agent never borrows the user's GitHub CLI login for
    Copilot (``gh auth token``). The app already points GH_CONFIG_DIR at an
    empty dir; this also suppresses the source and drops a row an earlier
    build seeded — under Hermes' own auth-store lock, so a concurrent writer
    can't lose it. A Copilot key saved on purpose (``env:*`` from GDJ's
    ``.env``) is untouched."""
    try:
        from hermes_cli import auth as auth_mod

        with auth_mod._auth_store_lock():
            store = auth_mod._load_auth_store()
            changed = False
            pool = store.get("credential_pool")
            rows = pool.get("copilot") if isinstance(pool, dict) else None
            if isinstance(rows, list):
                kept = [r for r in rows if not (isinstance(r, dict) and r.get("source") == "gh_cli")]
                if len(kept) != len(rows):
                    changed = True
                    if kept:
                        pool["copilot"] = kept
                    else:
                        pool.pop("copilot", None)
            suppressed = auth_mod._store_section(store, "suppressed_sources")
            sources = auth_mod._suppressed_source_list(suppressed, "copilot")
            if sources is None:
                sources = suppressed["copilot"] = []
            if "gh_cli" not in sources:
                sources.append("gh_cli")
                changed = True
            if changed:
                auth_mod._save_auth_store(store)
    except Exception:
        pass


def register(server) -> None:
    _gdj_refuse_borrowed_logins()
    bind_module(globals(), server, skip=("_",))
