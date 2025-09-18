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
    required_packages = [
        ("jupyter_server", "jupyter_server"),
        ("jupyter_server_ydoc", "jupyter_server_ydoc"),  # Auto-installs jupyter_ydoc, pycrdt, pycrdt-websocket
        ("jupyter_ydoc", "jupyter_ydoc"),
        ("pycrdt", "pycrdt"),  # Auto-dependency of jupyter_ydoc
        ("pycrdt-websocket", "pycrdt.websocket"),  # Auto-dependency of jupyter_server_ydoc
        ("jupyter_tools_bridge", "jupyter_tools_bridge"),
        ("aiohttp", "aiohttp"),
        ("nbformat", "nbformat"),
    ]

    all_installed = True
    for pkg in required_packages:
        if not check_package(pkg):
            all_installed = False

    if not all_installed:
        print(f"❌ Missing packages. Install with:")
        print("pip install jupyter-server-ydoc aiohttp nbformat")
        print("# Note: jupyter_ydoc, pycrdt, pycrdt-websocket are auto-installed as dependencies")
        sys.exit(1)

    print("\n2️⃣  Checking Jupyter server extensions...")
    expected_extensions = [
        "jupyter_server_fileid",
        "jupyter_server_ydoc", 
        "jupyter_tools_bridge",
    ]

    all_enabled = True
    for ext in expected_extensions:
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
