"""
Setup Verification Script
=========================
Verifies that all required dependencies are installed correctly.
"""

import sys
from typing import List, Tuple

def check_import(module_name: str, package_name: str = None) -> Tuple[bool, str]:
    """
    Check if a module can be imported.

    Args:
        module_name: The module to import
        package_name: The package name (for display), defaults to module_name

    Returns:
        Tuple of (success, message)
    """
    if package_name is None:
        package_name = module_name

    try:
        __import__(module_name)
        return True, f"✅ {package_name}"
    except ImportError as e:
        return False, f"❌ {package_name}: {str(e)}"


def verify_setup() -> bool:
    """
    Verify all required packages are installed.

    Returns:
        True if all packages are available, False otherwise
    """
    print("=" * 60)
    print("AutoGen Multi-Agent Setup Verification")
    print("=" * 60)
    print()

    # Define required packages
    packages = [
        ("streamlit", "streamlit"),
        ("autogen_agentchat", "autogen-agentchat"),
        ("autogen_core", "autogen-core"),
        ("autogen_ext", "autogen-ext"),
        ("google.generativeai", "google-generativeai"),
        ("dotenv", "python-dotenv"),
    ]

    # Check each package
    results = []
    for module_name, package_name in packages:
        success, message = check_import(module_name, package_name)
        print(message)
        results.append(success)

    print()
    print("=" * 60)

    # Check Python version
    py_version = sys.version_info
    print(f"Python Version: {py_version.major}.{py_version.minor}.{py_version.micro}")

    if py_version.major == 3 and py_version.minor >= 11:
        print("✅ Python version is compatible (3.11+)")
        py_ok = True
    else:
        print("❌ Python version should be 3.11 or higher")
        py_ok = False

    print("=" * 60)
    print()

    # Final status
    all_ok = all(results) and py_ok

    if all_ok:
        print("🎉 All checks passed! You're ready to run the application.")
        print()
        print("Next steps:")
        print("  1. Set up your Google API key (see README.md)")
        print("  2. Run: streamlit run streamlit_app.py")
        print()
    else:
        print("⚠️  Some packages are missing. Please install them:")
        print("  pip install --user -r requirements.txt")
        print()

    return all_ok


if __name__ == "__main__":
    success = verify_setup()
    sys.exit(0 if success else 1)
