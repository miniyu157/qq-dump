import pkgutil
import importlib


def load_features():
    """
    扫描 features 包下的所有模块，返回一个字典。
    格式: { '按键': { 'meta': META, 'func': run_func } }
    """
    features = {}

    import mods.features as feature_pkg

    package_path = feature_pkg.__path__
    prefix = feature_pkg.__name__ + "."

    for _, name, _ in pkgutil.iter_modules(package_path, prefix):
        try:
            module = importlib.import_module(name)

            # 检查是否符合协议 (必须有 META 和 run)
            if hasattr(module, "META") and hasattr(module, "run"):
                meta = module.META
                key = str(meta.get("key", "")).upper()

                if key:
                    features[key] = {"meta": meta, "func": module.run}
        except Exception:
            pass

    return features
