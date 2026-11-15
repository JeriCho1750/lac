#!/usr/bin/env python3
"""lac (Linux Admin Labs) - launcher.   sudo python3 -B run.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from course.core import main
import course.modules  # registers all modules and tasks
if __name__ == "__main__":
    main()
