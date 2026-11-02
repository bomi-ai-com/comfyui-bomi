"""comfy-bomi - ComfyUI nodes for the Bomi AI enterprise API.

Four nodes, one per task controller. Each runs the whole roundtrip internally:
/capability/check to gate on credit, /<feature>/create to submit, then
/task/search until the result images are ready.

Configuration lives in config.json (created from config.example.json on first
run); every string shown to the user lives in text.i18n.json.
"""

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

try:
    from .bomi import config, log
    from .bomi.nodes import NODES

    config.bootstrap()

    for _node in NODES:
        NODE_CLASS_MAPPINGS[_node.__name__] = _node
        NODE_DISPLAY_NAME_MAPPINGS[_node.__name__] = _node.title()

    log.info(
        "loaded %d node(s) [language=%s, api=%s]: %s",
        len(NODE_CLASS_MAPPINGS),
        config.get("language"),
        config.base_url(),
        ", ".join(NODE_DISPLAY_NAME_MAPPINGS.values()),
    )
    if not config.resolve_api_key():
        log.warn("no enterpriseApiKey configured yet - set it in config.json before running a "
                 "node; the file is re-read whenever it changes, so a browser refresh is "
                 "enough - no restart")

except Exception:
    # A custom node that fails to import should say so loudly - but only when it was
    # imported the way ComfyUI imports it, under a package name. With no package there is
    # no way `from .bomi import ...` could have worked, so this is not a load failure and
    # the traceback would be a lie. pytest reaches here on every run: the repo root is
    # itself the custom_node package, so pytest sees an `__init__.py` above `tests/`,
    # treats the root as a Package, and imports it bare (`_pytest/python.py`,
    # `Package.setup`). ComfyUI and release.py both pass a package name, so a real
    # failure - a missing dependency, say - still prints.
    if __package__:
        import traceback
        print("[Bomi] failed to load comfy-bomi:\n%s" % traceback.format_exc())

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
