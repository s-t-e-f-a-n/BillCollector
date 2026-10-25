"""Candidate phased login recipe contract (upstream issue #20).

Validation is separate from execution so malformed opt-in recipes fail before
vault or browser access. Ordinary recipes retain their existing behavior.
"""

LOCATORS = frozenset({
    "locator", "get_by_role", "get_by_text", "get_by_label", "get_by_test_id",
    "get_by_placeholder", "get_by_alt_text", "get_by_title", "first", "last",
    "nth", "filter", "content_frame",
})
SUCCESS_KEYS = frozenset({"role", "test_id", "placeholder", "label", "text", "selector"})


def settle_attempt(db, task_id, run_id, *, dispatch=None):
    """Settle at most once and notify only on the transition to blocked."""
    from .notify import notify_login_locked

    settled = db.settle_login_attempt(task_id, run_id)
    task = db.get_task(task_id)
    if settled and task["login_locked"]:
        notify_login_locked(db, task, dispatch=dispatch)
    return bool(task["login_locked"])


def is_login(step):
    return any(m.get("method") == "login" for m in step.get("methods", []))


def _action(step, terminals):
    methods = step.get("methods", []) if isinstance(step, dict) else []
    nested_actions = bool(step.get("steps") or step.get("submit") or step.get("phases")) if isinstance(step, dict) else False
    if (not isinstance(methods, list) or not methods
            or any(not isinstance(m, dict) for m in methods)
            or nested_actions
            or step.get("graceful") or methods[-1].get("method") not in terminals
            or any(m.get("method") not in LOCATORS for m in methods[:-1])):
        raise ValueError(f'step {step.get("step", "?") if isinstance(step, dict) else "?"}: login requires locator chains with one explicit terminal action')
    if methods[-1]["method"] == "press":
        args = methods[-1].get("arguments", [])
        if args not in ([{"key": "Enter"}], ["Enter"]):
            raise ValueError(f'step {step.get("step", "?")}: login submit press must use Enter')


def login_options(step):
    methods = step.get("methods", [])
    if len(methods) != 1 or methods[0].get("method") != "login" or step.get("graceful"):
        raise ValueError("login must be a standalone non-graceful method")
    options = {}
    for arg in methods[0].get("arguments", []):
        if not isinstance(arg, dict) or options.keys() & arg.keys():
            raise ValueError("login arguments must have unique names")
        options.update(arg)
    if options.keys() - {"success", "max_failures", "timeout_ms", "session_timeout_ms"}:
        raise ValueError("unknown login argument")
    validate_success(options.get("success"))
    for key, default in (("max_failures", 2), ("timeout_ms", 10000),
                         ("session_timeout_ms", 1000)):
        value = options.setdefault(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"login {key} must be a positive integer")
    phases = step.get("phases")
    if phases is not None:
        if not isinstance(phases, list) or not phases or "steps" in step or "submit" in step:
            raise ValueError("login phases must be non-empty and cannot mix with steps/submit")
        for phase in phases:
            if not isinstance(phase, dict) or phase.keys() - {"steps", "submit", "success"}:
                raise ValueError("login phase accepts only steps, submit and success")
            validate_success(phase.get("success"))
        if phases[-1]["success"] != options["success"]:
            raise ValueError("last phase must prove the final login success locator")
    else:
        phases = [{"steps": step.get("steps", []), "submit": step.get("submit"),
                   "success": options["success"]}]
    for phase in phases:
        preparations = phase.get("steps", [])
        if not isinstance(preparations, list):
            raise ValueError("login preparation must be a list")
        for preparation in preparations:
            _action(preparation, {"fill"})
        _action(phase.get("submit"), {"click", "press"})
    options["phases"] = phases
    return options


def validate_success(success):
    if not isinstance(success, dict) or len(SUCCESS_KEYS & success.keys()) != 1:
        raise ValueError("login requires one explicit success locator")
    locator_keys = SUCCESS_KEYS & success.keys()
    locator_key = next(iter(locator_keys))
    allowed = {"exact"} if locator_key not in {"selector", "test_id"} else set()
    if locator_key == "role":
        allowed |= {"name", "checked", "disabled", "expanded", "include_hidden",
                    "level", "pressed", "selected"}
    if success.keys() - {locator_key} - allowed:
        raise ValueError("unsupported login success locator argument")
    if not isinstance(success[locator_key], str) or not success[locator_key].strip():
        raise ValueError("login success locator must be a non-empty string")


def validate_login_recipe(recipe):
    """One top-level login block per task recipe; no implicit nested execution."""
    count = 0

    def visit(step, service, nested=False):
        nonlocal count
        if is_login(step):
            if nested:
                raise ValueError(f'service {service}, step {step["step"]}, method login: login blocks cannot be nested')
            try:
                login_options(step)
            except ValueError as error:
                raise ValueError(f'service {service}, step {step["step"]}, method login: {error}') from None
            count += 1
        else:
            if "submit" in step or "phases" in step:
                raise ValueError(f'service {service}, step {step["step"]}: submit belongs to a login block')
            for child in step.get("steps", []):
                visit(child, service, True)

    for service in recipe.get("services", []):
        for step in service.get("steps", []):
            visit(step, service["serviceName"])
            if count > 1:
                raise ValueError(f'service {service["serviceName"]}, step {step["step"]}, method login: only one login block is supported per task recipe')
