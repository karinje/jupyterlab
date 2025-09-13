#!/usr/bin/env python3
"""
Verification script to check if Jupyter Tools Bridge setup is correct.
"""

import sys
import subprocess
import importlib.util


def check_package(package_info):
    """Check if a package is installed."""
    if isinstance(package_info, tuple):
        package_name, import_name = package_info
    else:
        package_name = package_info
        import_name = package_info.replace("-", "_")

    spec = importlib.util.find_spec(import_name)
    if spec is None:
        print(f"❌ {package_name} is NOT installed")
        return False
    else:
        # Try to get version if available
        try:
            # Handle nested modules like pycrdt.websocket
            if "." in import_name:
                parts = import_name.split(".")
                module = __import__(import_name, fromlist=[parts[-1]])
            else:
                module = __import__(import_name)
            version = getattr(module, "__version__", "unknown")
            print(f"✅ {package_name} is installed (version: {version})")
        except:
            print(f"✅ {package_name} is installed")
        return True


def check_server_extension(name):
    """Check if a Jupyter server extension is enabled."""
    try:
        result = subprocess.run(
            ["jupyter", "server", "extension", "list"], capture_output=True, text=True
        )
        if name in result.stdout and "enabled" in result.stdout:
            print(f"✅ {name} server extension is enabled")
            return True
        else:
            print(f"❌ {name} server extension is NOT enabled")
            return False
    except Exception as e:
        print(f"⚠️  Could not check {name}: {e}")
        return False


def main():
    print("=" * 60)
    print("Jupyter Tools Bridge Setup Verification")
    print("=" * 60)

    print("\n1️⃣  Checking Python packages...")
    packages = [
        ("jupyter_server", "jupyter_server"),
        ("jupyter_server_ydoc", "jupyter_server_ydoc"),
        ("jupyter_ydoc", "jupyter_ydoc"),
        ("jupyter_collaboration", "jupyter_collaboration"),
        ("pycrdt", "pycrdt"),
        ("pycrdt-websocket", "pycrdt.websocket"),  # Package name vs import path
        ("jupyter_server_fileid", "jupyter_server_fileid"),
        ("jupyterlab", "jupyterlab"),
        ("aiohttp", "aiohttp"),
    ]

    all_installed = True
    for pkg in packages:
        if not check_package(pkg):
            all_installed = False

    if not all_installed:
        print("\n❌ Some packages are missing. Run:")
        print(
            "pip install jupyter-collaboration jupyter-server-ydoc jupyter_ydoc pycrdt pycrdt-websocket"
        )
        sys.exit(1)

    print("\n2️⃣  Checking Jupyter server extensions...")
    extensions = [
        "jupyter_server_fileid",
        "jupyter_server_ydoc",
        "jupyter_collaboration",
        "jupyter_tools_bridge",
    ]

    all_enabled = True
    for ext in extensions:
        if not check_server_extension(ext):
            all_enabled = False

    if not all_enabled:
        print("\n⚠️  Some extensions may not be enabled.")
        print("To enable jupyter_tools_bridge, run:")
        print("jupyter server extension enable jupyter_tools_bridge")

    print("\n3️⃣  Checking local module...")
    try:
        import jupyter_tools_bridge

        print("✅ jupyter_tools_bridge module can be imported")
    except ImportError as e:
        print(f"❌ Cannot import jupyter_tools_bridge: {e}")
        print("Make sure you're in the project root directory")
        sys.exit(1)

    print("\n" + "=" * 60)
    if all_installed:
        print("✅ Setup verification PASSED!")
        print("\nNext steps:")
        print("1. Start Jupyter with: jupyter lab --config=jupyter_server_config.py")
        print("2. Open/create test_tools.ipynb")
        print("3. Run: python test_scripts/test_ydoc_tools.py")
    else:
        print("❌ Setup verification FAILED - fix the issues above")
    print("=" * 60)


if __name__ == "__main__":
    main()
