import ayon_api
import inspect

print("AYON_API Methods:")
for name, member in inspect.getmembers(ayon_api):
    if "update" in name or "status" in name or "task" in name or "product" in name:
        if callable(member):
            print(f"  {name}{inspect.signature(member)}")
