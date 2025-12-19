import importlib
import pkgutil

def load_tools():
    """
    Auto-discover tool modules inside tools/ package.
    Each tool module must expose:
      - TOOL_NAME (str)
      - TOOL_SPEC (dict)  (MCP-style tool schema)
      - run(args: dict) -> dict
    """
    from . import ping  # ensures at least one tool exists (safety)

    tools = {}
    specs = {}

    package_name = __name__.split(".")[0]  # "tools"
    package = importlib.import_module(package_name)

    for mod in pkgutil.iter_modules(package.__path__):
        name = mod.name
        if name in ("loader", "__init__"):
            continue

        m = importlib.import_module(f"{package_name}.{name}")

        tool_name = getattr(m, "TOOL_NAME", None)
        tool_spec = getattr(m, "TOOL_SPEC", None)
        runner = getattr(m, "run", None)

        if not tool_name or not tool_spec or not callable(runner):
            continue

        tools[tool_name] = runner
        specs[tool_name] = tool_spec

    return tools, specs
