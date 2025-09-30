def load_functions_from(folder):
    for file in os.listdir(folder):
        if file.endswith(".py") and file != "__init__.py":
            module_name = file[:-3]
            module = importlib.import_module(f"{folder}.{module_name}")
            globals().update({k: v for k, v in module.__dict__.items() if callable(v)})
