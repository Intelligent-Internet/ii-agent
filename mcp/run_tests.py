#!/usr/bin/env python3
"""Test runner script for FileEditTool tests."""

import sys
import os
import subprocess
from pathlib import Path

def main():
    """Run tests with proper configuration."""
    # Get the script directory
    script_dir = Path(__file__).parent
    
    # Add src to Python path
    src_dir = script_dir / "src"
    if src_dir.exists():
        sys.path.insert(0, str(src_dir))
    
    # Check if pytest is available
    try:
        import pytest
    except ImportError:
        print("❌ pytest not found. Installing test dependencies...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements-test.txt"])
            import pytest
        except subprocess.CalledProcessError:
            print("❌ Failed to install test dependencies.")
            print("💡 Try: pip install pytest pytest-mock")
            return 1
        except ImportError:
            print("❌ Still couldn't import pytest after installation.")
            return 1
    
    print("🧪 Running FileEditTool tests...")
    print("=" * 50)
    
    # Run pytest with configuration
    args = [
        "tests/test_file_edit_tool.py",
        "-v",
        "--tb=short",
        "--no-header",
        "--disable-warnings"
    ]
    
    # Add coverage if available
    try:
        import coverage
        args.extend(["--cov=src.tools.file_system.file_edit_tool", "--cov-report=term-missing"])
    except ImportError:
        pass
    
    try:
        exit_code = pytest.main(args)
        
        if exit_code == 0:
            print("\n✅ All tests passed!")
        else:
            print(f"\n❌ Tests failed with exit code {exit_code}")
            
        return exit_code
        
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return 1


"""
python -m pytest tests/test_multi_edit_tool.py -v
python -m pytest tests/test_file_edit_tool.py -v
"""
if __name__ == "__main__":
    sys.exit(main())