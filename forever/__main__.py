"""Run the Forever Guide: `python forever <command>` from the unzipped folder, or `python -m forever <command>`."""
import os
import sys

if not __package__:
    # Started as `python forever`: Python may have put this folder itself on the path, where a file here could
    # shadow a standard module. Take it off and put the folder that holds the package there instead.
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.curdir) != _here]
    sys.path.insert(0, os.path.dirname(_here))
    from forever.cli import main
else:
    from .cli import main

sys.exit(main())
