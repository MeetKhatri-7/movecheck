import os
import sys

# Resolve the processor dir relative to this script so the repo can live
# anywhere (it previously hardcoded a stale /Users/... path).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'processor'))
from analyzers.strength import back_squat
# call analyse with empty files
try:
    res = back_squat.analyse({'side': None})
    print(res)
except Exception as e:
    import traceback
    traceback.print_exc()
