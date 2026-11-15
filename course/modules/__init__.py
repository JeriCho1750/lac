import importlib, pkgutil
for _m in sorted(m.name for m in pkgutil.iter_modules(__path__)):
    importlib.import_module(f"{__name__}.{_m}")
